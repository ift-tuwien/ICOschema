//! Reads the PyTables-style HDF5 layout of ICOschema (`icoschema_format_version` absent = legacy
//! `acceleration` table, "1.0".."1.2" = versioned). Mirrors `icoschema/storage/python/hdf5.py`;
//! reading only. Not ported yet: legacy `Sensor_Range`, writing.

use std::collections::HashMap;

use icoschema_gen as g;
use rust_hdf5::{DatatypeMessage, H5Dataset, H5File, H5Group};

use super::table::Table;
use super::vlen;
use crate::{invalid, Error, Result};

const LEGACY_PRIMARY_TABLE: &str = "acceleration";
const SUPPORTED: [&str; 3] = ["1.0", "1.1", "1.2"];
const CHANNELS: [&str; 3] = ["channel1", "channel2", "channel3"];

// ── enums ───────────────────────────────────────────────────────────────────
//
// The `*_name` functions match exhaustively on purpose: when the LinkML schema gains an enum
// value, regenerating makes them (and so the build) fail until the new value is handled here,
// instead of the reader quietly rejecting or ignoring it.

const SOURCES: [g::SamplingFrequencySource; 3] =
    [g::SamplingFrequencySource::Override, g::SamplingFrequencySource::Hardware, g::SamplingFrequencySource::Default];

fn source_name(value: &g::SamplingFrequencySource) -> &'static str {
    match value {
        g::SamplingFrequencySource::Override => "override",
        g::SamplingFrequencySource::Hardware => "hardware",
        g::SamplingFrequencySource::Default => "default",
    }
}

const STATUSES: [g::ComputationStatus; 2] = [g::ComputationStatus::Ok, g::ComputationStatus::Error];

fn status_name(value: &g::ComputationStatus) -> &'static str {
    match value {
        g::ComputationStatus::Ok => "ok",
        g::ComputationStatus::Error => "error",
    }
}

fn parse_enum<T: Clone>(text: &str, all: &[T], name: fn(&T) -> &'static str) -> Result<T> {
    match all.iter().find(|v| name(v) == text) {
        Some(value) => Ok(value.clone()),
        None => invalid(format!("unknown value {text:?}; expected one of {:?}", all.iter().map(name).collect::<Vec<_>>())),
    }
}

// ── attribute helpers ──────────────────────────────────────────────────────

trait Attrs {
    fn attr_names_vec(&self) -> Vec<String>;
    fn attribute(&self, name: &str) -> Result<rust_hdf5::H5Attribute>;
}
impl Attrs for H5Dataset {
    fn attr_names_vec(&self) -> Vec<String> { self.attr_names().unwrap_or_default() }
    fn attribute(&self, name: &str) -> Result<rust_hdf5::H5Attribute> { Ok(self.attr(name)?) }
}
impl Attrs for H5Group {
    fn attr_names_vec(&self) -> Vec<String> { self.attr_names().unwrap_or_default() }
    fn attribute(&self, name: &str) -> Result<rust_hdf5::H5Attribute> { Ok(self.attr(name)?) }
}
impl Attrs for H5File {
    fn attr_names_vec(&self) -> Vec<String> { self.attr_names().unwrap_or_default() }
    fn attribute(&self, name: &str) -> Result<rust_hdf5::H5Attribute> { Ok(self.attr(name)?) }
}

fn opt_str(o: &impl Attrs, name: &str) -> Result<Option<String>> {
    if !o.attr_names_vec().iter().any(|n| n == name) {
        return Ok(None);
    }
    let attr = o.attribute(name)?;
    Ok(Some(match attr.datatype()? {
        DatatypeMessage::FixedPoint { .. } => attr.read_numeric_as::<i64>()?[0].to_string(),
        DatatypeMessage::FloatingPoint { .. } => attr.read_numeric_as::<f64>()?[0].to_string(),
        _ => attr.read_string()?,
    }))
}

fn opt_int(o: &impl Attrs, name: &str) -> Result<Option<isize>> {
    opt_str(o, name)?
        .map(|v| v.trim().parse::<isize>().or_else(|_| invalid(format!("attribute {name:?} must be an integer, got {v:?}"))))
        .transpose()
}

fn req_str(o: &impl Attrs, name: &str) -> Result<String> {
    opt_str(o, name)?.ok_or_else(|| Error::Invalid(format!("missing attribute {name:?}")))
}

// ── Recording ───────────────────────────────────────────────────────────────

pub fn format_version(file: &H5File) -> Result<Option<String>> {
    let version = opt_str(file, "icoschema_format_version")?;
    if let Some(v) = &version {
        if !SUPPORTED.contains(&v.as_str()) {
            return invalid(format!("unsupported icoschema_format_version {v:?}; supported: {SUPPORTED:?}"));
        }
    }
    Ok(version)
}

pub fn load_recording(path: &str) -> Result<g::Recording> {
    let file = H5File::open(path)?;
    recording_from(&file, super::budget(path)?)
}

fn recording_from(file: &H5File, budget: u64) -> Result<g::Recording> {
    let table_name = match format_version(file)? {
        None => LEGACY_PRIMARY_TABLE.to_string(),
        Some(_) => req_str(file, "primary_table")?,
    };
    let ds = file.dataset(&table_name)?;
    let table = Table::read(&ds, budget)?;

    let sensors = match file.dataset("sensors") {
        Ok(s) => Some(Table::read(&s, budget)?),
        Err(_) => None,
    };
    let sensor_count = sensors.as_ref().map_or(0, Table::len);
    let channel_columns: Vec<&str> =
        table.column_names().filter(|n| !matches!(*n, "counter" | "timestamp")).collect();

    let already_converted = match opt_str(&ds, "conversion")? {
        Some(v) => v == "true",
        None if sensor_count == 0 => true,
        None => return invalid(format!("table {table_name:?} has sensor rows but no `conversion` attribute")),
    };
    if channel_columns.len() > 3 {
        return invalid(format!("at most 3 channels supported, got {}", channel_columns.len()));
    }
    if sensor_count == 0 && !already_converted {
        return invalid("table is not converted but the file has no sensor rows");
    }
    if sensor_count != 0 && sensor_count != channel_columns.len() {
        return invalid(format!(
            "expected one sensor row per channel column, got {} channel column(s) and {sensor_count} sensor row(s)",
            channel_columns.len()
        ));
    }

    // Files from the first acquisition tools: no sensor rows, only a `Sensor_Range` like "± 100.0 g₀".
    let fallback_sensor = if sensor_count == 0 {
        opt_str(&ds, "Sensor_Range")?.as_deref().and_then(sensor_from_range)
    } else {
        None
    };
    let channel = |i: usize| -> Result<g::ChannelMetadata> {
        let (sensor, compensations) = match &sensors {
            Some(t) if t.len() > 0 => {
                let sensor = sensor_row(t, i)?;
                let comp = if already_converted {
                    g::CompensationOrSubtype::NoConversion(g::NoConversion { order: 0 })
                } else {
                    g::CompensationOrSubtype::LinearConversion(g::LinearConversion {
                        order: 0,
                        gain: t.f64_column("scaling_factor")?[i],
                        offset: t.f64_column("offset")?[i],
                    })
                };
                (sensor, vec![comp])
            }
            _ => (
                fallback_sensor.clone().unwrap_or_else(empty_sensor),
                vec![g::CompensationOrSubtype::NoConversion(g::NoConversion { order: 0 })],
            ),
        };
        Ok(g::ChannelMetadata { sensor, compensations })
    };

    let columns = |i: usize| -> Result<Option<Vec<f64>>> {
        channel_columns.get(i).map(|c| table.f64_column(c)).transpose()
    };
    let data = g::RecordingData {
        timestamp: table.i64_column("timestamp")?.into_iter().map(|v| v as isize).collect(),
        counter: table.i64_column("counter")?.into_iter().map(|v| v as isize).collect(),
        channel1: columns(0)?.ok_or_else(|| Error::Invalid("recording has no channel columns".into()))?,
        channel2: columns(1)?,
        channel3: columns(2)?,
    };
    let hardware = g::HardwareMetadata {
        revision: None,
        adc_reference_voltage: opt_str(&ds, "adc_reference_voltage")?,
        adc_prescaler: opt_int(&ds, "adc_prescaler")?,
        adc_acquisition_time: opt_int(&ds, "adc_acquisition_time")?,
        adc_oversample_rate: opt_int(&ds, "adc_oversample_rate")?,
        channel1_metadata: channel(0)?,
        channel2_metadata: if channel_columns.len() > 1 { Some(channel(1)?) } else { None },
        channel3_metadata: if channel_columns.len() > 2 { Some(channel(2)?) } else { None },
    };
    Ok(g::Recording {
        hardware_metadata: hardware,
        recording_metadata: g::RecordingMetadata {
            start_time: Some(req_str(&ds, "Start_Time")?),
            pre_metadata: opt_str(&ds, "pre_metadata")?,
            post_metadata: opt_str(&ds, "post_metadata")?,
        },
        recording_data: data,
    })
}

/// `"± 100.0 g₀"` -> unit `g`, range -100..100 (nothing else about the sensor was recorded).
fn sensor_from_range(text: &str) -> Option<g::Sensor> {
    let text = text.trim().trim_start_matches(['±', '+', '-']).trim_start();
    let split = text.find(|c: char| !(c.is_ascii_digit() || c == '.'))?;
    let (number, unit) = text.split_at(split);
    let unit = unit.trim();
    if number.is_empty() || unit.is_empty() || unit.contains(char::is_whitespace) {
        return None;
    }
    let limit: f64 = number.parse().ok()?;
    Some(g::Sensor {
        unit: Some(unit.replace('₀', "")),
        phys_min: Some(-limit),
        phys_max: Some(limit),
        ..empty_sensor()
    })
}

fn empty_sensor() -> g::Sensor {
    g::Sensor {
        sensor_id: None, sensor_type: None, name: None, unit: None, dimension: None,
        phys_min: None, phys_max: None, volt_min: None, volt_max: None,
    }
}

/// Every column is optional: older tools wrote fewer.
fn sensor_row(t: &Table, i: usize) -> Result<g::Sensor> {
    let text = |c: &str| -> Result<Option<String>> {
        Ok(if t.has(c) { Some(t.string_column(c)?.swap_remove(i)) } else { None })
    };
    let num = |c: &str| -> Result<Option<f64>> {
        Ok(if t.has(c) { Some(t.f64_column(c)?[i]) } else { None })
    };
    Ok(g::Sensor {
        sensor_id: text("sensor_id")?,
        sensor_type: text("sensor_type")?,
        name: text("name")?,
        unit: text("unit")?,
        dimension: text("dimension")?,
        phys_min: num("phys_min")?,
        phys_max: num("phys_max")?,
        volt_min: num("volt_min")?,
        volt_max: num("volt_max")?,
    })
}

/// A list-of-strings attribute (`inputs`, `output_keys`). rust-hdf5 0.7 can only read the first
/// element of a variable-length string array, so those go through the `vlen` shim.
fn string_list(o: &(impl Attrs + ?Sized), path: &str, name: &str) -> Result<Option<Vec<String>>> {
    if !o.attr_names_vec().iter().any(|n| n == name) {
        return Ok(None);
    }
    let attr = o.attribute(name)?;
    match attr.datatype()? {
        DatatypeMessage::VarLenString { .. } => Ok(Some(vlen::strings(path, &attr.read_raw()?)?)),
        _ => Ok(Some(vec![attr.read_string()?])),
    }
}

// ── PreprocessedRecording, computations, steps ──────────────────────────────

fn preprocessed_from(file: &H5File, budget: u64) -> Result<Option<g::PreprocessedRecording>> {
    if matches!(format_version(file)?.as_deref(), None | Some("1.0")) {
        return Ok(None);
    }
    let Some(name) = opt_str(file, "preprocessed_table")? else { return Ok(None) };
    let ds = file.dataset(&name).map_err(|_| Error::Invalid(format!("preprocessed table {name:?} does not exist")))?;
    let table = Table::read(&ds, budget)?;
    let source = parse_enum(&req_str(&ds, "sampling_frequency_source")?, &SOURCES, source_name)?;
    let channel = |c: &str| table.has(c).then(|| table.f64_column(c)).transpose();
    Ok(Some(g::PreprocessedRecording {
        timestamp: table.i64_column("timestamp")?.into_iter().map(|v| v as isize).collect(),
        channel1: table.f64_column("channel1")?,
        channel2: channel("channel2")?,
        channel3: channel("channel3")?,
        channel_sampling_frequency: req_str(&ds, "channel_sampling_frequency")?
            .parse()
            .or_else(|_| invalid("channel_sampling_frequency is not a number"))?,
        sampling_frequency_source: source,
        fill_method: req_str(&ds, "fill_method")?,
        producer: req_str(&ds, "producer")?,
    }))
}

fn collect_computations(
    file: &H5File,
    budget: u64,
    group: &H5Group,
    prefix: &str,
    out: &mut HashMap<String, g::DerivedDataset>,
) -> Result<()> {
    for name in group.dataset_names()? {
        let key = format!("{prefix}{name}");
        let ds = file.dataset(&format!("computations/{key}"))?;
        super::check_size(&ds, budget)?;
        let shape = ds.shape();
        let values = match ds.datatype()? {
            DatatypeMessage::FloatingPoint { .. } => ds.read_numeric_as::<f64>()?,
            // rust-hdf5 refuses a silent integer -> f64 read, so convert explicitly.
            DatatypeMessage::FixedPoint { .. } => {
                ds.read_numeric_as::<i64>()?.into_iter().map(|v| v as f64).collect()
            }
            _ => return invalid(format!("computation {key:?} is not numeric")),
        };
        let dtype = match ds.datatype()? {
            DatatypeMessage::FloatingPoint { size, .. } => format!("float{}", size * 8),
            DatatypeMessage::FixedPoint { size, signed, .. } => format!("{}int{}", if signed { "" } else { "u" }, size * 8),
            _ => unreachable!(),
        };
        out.insert(
            key.clone(),
            g::DerivedDataset {
                key,
                values,
                shape: shape.into_iter().map(|d| d as isize).collect(),
                dtype,
                unit: opt_str(&ds, "unit")?,
                produced_by: opt_str(&ds, "produced_by")?,
                produced_at: opt_str(&ds, "produced_at")?,
                params: opt_str(&ds, "params")?,
                description: opt_str(&ds, "description")?,
            },
        );
    }
    for name in group.group_names()? {
        collect_computations(file, budget, &group.group(&name)?, &format!("{prefix}{name}/"), out)?;
    }
    Ok(())
}

fn steps_from(file: &H5File, path: &str) -> Result<Vec<g::ComputationStep>> {
    if format_version(file)?.as_deref() != Some("1.2") {
        return Ok(vec![]);
    }
    let Ok(group) = file.root_group().group("steps") else { return Ok(vec![]) };
    let mut steps = Vec::new();
    for node in group.group_names()? {
        let step = group.group(&node)?;
        let status = opt_str(&step, "status")?
            .map(|v| parse_enum(&v, &STATUSES, status_name))
            .transpose()?;
        steps.push(g::ComputationStep {
            node,
            step_index: opt_int(&step, "step_index")?.unwrap_or(0),
            producer: req_str(&step, "producer")?,
            params: opt_str(&step, "params")?,
            resolved_params: opt_str(&step, "resolved_params")?,
            inputs: string_list(&step, path, "inputs")?,
            status,
            error: opt_str(&step, "error")?,
            summary: opt_str(&step, "summary")?,
            output_keys: string_list(&step, path, "output_keys")?,
            started_at: opt_str(&step, "started_at")?,
            duration_s: opt_str(&step, "duration_s")?.and_then(|v| v.parse().ok()),
            environment: opt_str(&step, "environment")?,
        });
    }
    steps.sort_by(|a, b| (a.step_index, &a.node).cmp(&(b.step_index, &b.node)));
    for (i, s) in steps.iter_mut().enumerate() {
        s.step_index = i as isize;
    }
    Ok(steps)
}

pub fn load_dataset_bundle(path: &str) -> Result<g::DatasetBundle> {
    let file = H5File::open(path)?;
    let budget = super::budget(path)?;
    let mut computations = HashMap::new();
    if let Ok(group) = file.root_group().group("computations") {
        collect_computations(&file, budget, &group, "", &mut computations)?;
    }
    Ok(g::DatasetBundle {
        recording: recording_from(&file, budget)?,
        preprocessed: preprocessed_from(&file, budget)?,
        computations: Some(computations),
        steps: Some(steps_from(&file, path)?),
    })
}
