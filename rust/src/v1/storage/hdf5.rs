//! Reads the PyTables-style HDF5 layout of ICOschema (`icoschema_format_version` absent = legacy
//! `acceleration` table, "1.0".."1.4" = versioned). Mirrors `icoschema/v1/storage/hdf5.py`:
//!
//! - "1.0".."1.2": one source, its table at the root (1.1 adds a preprocessed table, 1.2 steps);
//! - "1.3": several sources, one group per source under `/sources/` (the root attribute `sources`
//!   lists their names in order), each holding the table, its `sensors` table and, if it has one,
//!   its preprocessed table;
//! - "1.4": a superset for sources that are not packet recordings (TDMS): the primary table may
//!   have no `counter` column and the attributes `sampling_frequency` and `additional_data`, a
//!   dataset `quality` sits next to it, and a single source's name is always stored. Either
//!   layout, told apart by the `sources` attribute.
//!
//! The root attributes `source_format`, `source_format_version`, `reader` and `writer` (every
//! version) are the bundle's provenance. Legacy `Sensor_Range` files are read too.

use std::collections::HashMap;

use icoschema_gen_v1 as g;
use rust_hdf5::{DatatypeMessage, H5Dataset, H5File, H5Group};

use super::table::Table;
use super::vlen;
use crate::{invalid, Error, Result};

const LEGACY_PRIMARY_TABLE: &str = "acceleration";
const SUPPORTED: [&str; 5] = ["1.0", "1.1", "1.2", "1.3", "1.4"];
pub(super) const DEFAULT_SOURCE_NAME: &str = "source1";
pub(super) const SOURCES_GROUP: &str = "sources";
pub(super) const QUALITY_DATASET: &str = "quality";

// ── enums ───────────────────────────────────────────────────────────────────
//
// The `*_name` functions match exhaustively on purpose: when the LinkML schema gains an enum
// value, regenerating makes them (and so the build) fail until the new value is handled here,
// instead of the reader quietly rejecting or ignoring it.

const SOURCES: [g::SamplingFrequencySource; 3] =
    [g::SamplingFrequencySource::Override, g::SamplingFrequencySource::Hardware, g::SamplingFrequencySource::Default];

pub(super) fn source_name(value: &g::SamplingFrequencySource) -> &'static str {
    match value {
        g::SamplingFrequencySource::Override => "override",
        g::SamplingFrequencySource::Hardware => "hardware",
        g::SamplingFrequencySource::Default => "default",
    }
}

const STATUSES: [g::ComputationStatus; 2] = [g::ComputationStatus::Ok, g::ComputationStatus::Error];

pub(super) fn status_name(value: &g::ComputationStatus) -> &'static str {
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

fn has_attr<T: Attrs + ?Sized>(o: &T, name: &str) -> bool {
    o.attr_names_vec().iter().any(|n| n == name)
}

fn opt_str(o: &impl Attrs, name: &str) -> Result<Option<String>> {
    if !has_attr(o, name) {
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

fn opt_float(o: &impl Attrs, name: &str) -> Result<Option<f64>> {
    opt_str(o, name)?
        .map(|v| v.trim().parse::<f64>().or_else(|_| invalid(format!("attribute {name:?} must be a number, got {v:?}"))))
        .transpose()
}

fn req_str(o: &impl Attrs, name: &str) -> Result<String> {
    opt_str(o, name)?.ok_or_else(|| Error::Invalid(format!("missing attribute {name:?}")))
}

// ── layout ──────────────────────────────────────────────────────────────────

pub fn format_version(file: &H5File) -> Result<Option<String>> {
    let version = opt_str(file, "icoschema_format_version")?;
    if let Some(v) = &version {
        if !SUPPORTED.contains(&v.as_str()) {
            return invalid(format!("unsupported icoschema_format_version {v:?}; supported: {SUPPORTED:?}"));
        }
    }
    Ok(version)
}

/// Whether the sources are stored one group each under `/sources/` (1.3, or 1.4 with the
/// `sources` attribute) rather than as one table at the root.
fn has_sources_layout(file: &H5File, version: Option<&str>) -> bool {
    version == Some("1.3") || (version == Some("1.4") && has_attr(file, "sources"))
}

/// A list-of-strings attribute (`inputs`, `output_keys`, `sources`). rust-hdf5 0.7 can only read
/// the first element of a variable-length string array, so those go through the `vlen` shim.
fn string_list(o: &(impl Attrs + ?Sized), path: &str, name: &str) -> Result<Option<Vec<String>>> {
    if !has_attr(o, name) {
        return Ok(None);
    }
    let attr = o.attribute(name)?;
    match attr.datatype()? {
        DatatypeMessage::VarLenString { .. } => Ok(Some(vlen::strings(path, &attr.read_raw()?)?)),
        _ => Ok(Some(vec![attr.read_string()?])),
    }
}

/// The source names of a 1.3/1.4 file, in the order of the `sources` attribute.
fn source_names(file: &H5File, path: &str) -> Result<Vec<String>> {
    let group = file
        .root_group()
        .group(SOURCES_GROUP)
        .map_err(|_| Error::Invalid("a file with several sources needs a /sources/ group".into()))?;
    let names = string_list(file, path, "sources")?
        .ok_or_else(|| Error::Invalid("a file with several sources needs a `sources` attribute".into()))?;
    if names.is_empty() {
        return invalid("a file with sources must list at least one");
    }
    let mut seen = std::collections::HashSet::new();
    if let Some(duplicate) = names.iter().find(|n| !seen.insert(n.as_str())) {
        return invalid(format!("duplicate source name {duplicate:?} in the `sources` attribute"));
    }
    let present = group.group_names()?;
    let missing: Vec<&String> = names.iter().filter(|n| !present.contains(n)).collect();
    if !missing.is_empty() {
        return invalid(format!("sources {missing:?} are listed but have no group under /sources/"));
    }
    Ok(names)
}

// ── Sources ─────────────────────────────────────────────────────────────────

/// The sources of the file, in file order.
pub fn load_sources(path: &str) -> Result<Vec<g::Source>> {
    let file = H5File::open(path)?;
    sources_from(&file, path, super::budget(path)?)
}

fn sources_from(file: &H5File, path: &str, budget: u64) -> Result<Vec<g::Source>> {
    let version = format_version(file)?;
    let table_name = match &version {
        None => LEGACY_PRIMARY_TABLE.to_string(),
        Some(_) => req_str(file, "primary_table")?,
    };
    if !has_sources_layout(file, version.as_deref()) {
        return Ok(vec![source_from(file, budget, "", &table_name, None)?]);
    }
    source_names(file, path)?
        .iter()
        .map(|name| source_from(file, budget, &format!("{SOURCES_GROUP}/{name}/"), &table_name, Some(name)))
        .collect()
}

/// One source from the table `<prefix><table_name>` and its `sensors` table (`prefix` is empty at
/// the root, `sources/<name>/` in a source group). `name` overrides the stored `source_name`.
fn source_from(file: &H5File, budget: u64, prefix: &str, table_name: &str, name: Option<&str>) -> Result<g::Source> {
    let ds = file.dataset(&format!("{prefix}{table_name}"))?;
    let table = Table::read(&ds, budget)?;

    let sensors = match file.dataset(&format!("{prefix}sensors")) {
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
        // A 1.4 source without a packet counter has no column.
        counter: if table.has("counter") {
            Some(table.i64_column("counter")?.into_iter().map(|v| v as isize).collect())
        } else {
            None
        },
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
    Ok(g::Source {
        name: match name {
            Some(n) => n.to_string(),
            None => opt_str(&ds, "source_name")?.unwrap_or_else(|| DEFAULT_SOURCE_NAME.to_string()),
        },
        stu_id: opt_str(&ds, "stu_id")?,
        sth_id: opt_str(&ds, "sth_id")?,
        sampling_frequency: opt_float(&ds, "sampling_frequency")?,
        quality: quality_from(file, budget, prefix)?,
        additional_data: opt_str(&ds, "additional_data")?,
        hardware_metadata: hardware,
        recording_metadata: g::RecordingMetadata {
            start_time: Some(req_str(&ds, "Start_Time")?),
            pre_metadata: opt_str(&ds, "pre_metadata")?,
            post_metadata: opt_str(&ds, "post_metadata")?,
        },
        recording_data: data,
    })
}

/// The `quality` dataset next to a source's table (1.4), if there is one.
fn quality_from(file: &H5File, budget: u64, prefix: &str) -> Result<Option<g::QualityChannel>> {
    let Ok(ds) = file.dataset(&format!("{prefix}{QUALITY_DATASET}")) else { return Ok(None) };
    super::check_size(&ds, budget)?;
    let values = match ds.datatype()? {
        DatatypeMessage::FloatingPoint { .. } => ds.read_numeric_as::<f64>()?,
        DatatypeMessage::FixedPoint { .. } => ds.read_numeric_as::<i64>()?.into_iter().map(|v| v as f64).collect(),
        _ => return invalid("the quality dataset is not numeric"),
    };
    Ok(Some(g::QualityChannel { values, sampling_frequency: opt_float(&ds, "sampling_frequency")? }))
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

// ── PreprocessedRecording, computations, steps ──────────────────────────────

/// The preprocessed tables of the file (none for a file without any): the one at the root for a
/// 1.1/1.2 file (and a single-source 1.4 file), one per source group that has one for a sources
/// layout. Each gets its source's name.
fn preprocessed_from(file: &H5File, sources: &[g::Source], version: Option<&str>, budget: u64) -> Result<Vec<g::PreprocessedRecording>> {
    if matches!(version, None | Some("1.0")) {
        return Ok(vec![]);
    }
    let Some(table_name) = opt_str(file, "preprocessed_table")? else { return Ok(vec![]) };
    if !has_sources_layout(file, version) {
        return Ok(vec![read_preprocessed(file, "", &table_name, &sources[0].name, budget)?]);
    }
    let mut tables = Vec::new();
    for source in sources {
        let prefix = format!("{SOURCES_GROUP}/{}/", source.name);
        if file.dataset(&format!("{prefix}{table_name}")).is_ok() {
            tables.push(read_preprocessed(file, &prefix, &table_name, &source.name, budget)?);
        }
    }
    if tables.is_empty() {
        return invalid(format!("preprocessed table {table_name:?} does not exist"));
    }
    Ok(tables)
}

fn read_preprocessed(file: &H5File, prefix: &str, table_name: &str, source: &str, budget: u64) -> Result<g::PreprocessedRecording> {
    let ds = file
        .dataset(&format!("{prefix}{table_name}"))
        .map_err(|_| Error::Invalid(format!("preprocessed table {table_name:?} does not exist")))?;
    let table = Table::read(&ds, budget)?;
    let frequency_source = parse_enum(&req_str(&ds, "sampling_frequency_source")?, &SOURCES, source_name)?;
    let channel = |c: &str| table.has(c).then(|| table.f64_column(c)).transpose();
    Ok(g::PreprocessedRecording {
        timestamp: table.i64_column("timestamp")?.into_iter().map(|v| v as isize).collect(),
        channel1: table.f64_column("channel1")?,
        channel2: channel("channel2")?,
        channel3: channel("channel3")?,
        channel_sampling_frequency: req_str(&ds, "channel_sampling_frequency")?
            .parse()
            .or_else(|_| invalid("channel_sampling_frequency is not a number"))?,
        sampling_frequency_source: frequency_source,
        fill_method: req_str(&ds, "fill_method")?,
        producer: req_str(&ds, "producer")?,
        source: Some(source.to_string()),
    })
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

fn steps_from(file: &H5File, path: &str, version: Option<&str>) -> Result<Vec<g::ComputationStep>> {
    if !matches!(version, Some("1.2" | "1.3" | "1.4")) {
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
            source_node: opt_str(&step, "source_node")?,
        });
    }
    steps.sort_by(|a, b| (a.step_index, &a.node).cmp(&(b.step_index, &b.node)));
    for (i, s) in steps.iter_mut().enumerate() {
        s.step_index = i as isize;
    }
    Ok(steps)
}

/// What a file holds, with the sources in file order (the generated `Recording` is an unordered map).
pub struct Loaded {
    pub sources: Vec<g::Source>,
    pub preprocessed: Vec<g::PreprocessedRecording>,
    pub computations: HashMap<String, g::DerivedDataset>,
    pub steps: Vec<g::ComputationStep>,
    pub provenance: g::Provenance,
}

pub fn load_dataset_bundle(path: &str) -> Result<Loaded> {
    let file = H5File::open(path)?;
    let budget = super::budget(path)?;
    let version = format_version(&file)?;
    let sources = sources_from(&file, path, budget)?;
    let mut computations = HashMap::new();
    if let Ok(group) = file.root_group().group("computations") {
        collect_computations(&file, budget, &group, "", &mut computations)?;
    }
    Ok(Loaded {
        preprocessed: preprocessed_from(&file, &sources, version.as_deref(), budget)?,
        steps: steps_from(&file, path, version.as_deref())?,
        provenance: provenance_from(&file, version.as_deref())?,
        sources,
        computations,
    })
}

/// What the file says about where its data came from; a file that says nothing is data read from
/// HDF5 of its own format version.
fn provenance_from(file: &H5File, version: Option<&str>) -> Result<g::Provenance> {
    let (source_format, source_format_version, reader) = if has_attr(file, "source_format") {
        (opt_str(file, "source_format")?, opt_str(file, "source_format_version")?, opt_str(file, "reader")?)
    } else {
        (Some("hdf5".to_string()), Some(version.unwrap_or("legacy").to_string()), Some(super::software_id()))
    };
    Ok(g::Provenance { source_format, source_format_version, reader, writer: opt_str(file, "writer")? })
}

/// The `(scaling_factor, offset)` of each channel in the `sensors` table(s) of the file, by source name.
/// A file with one source at the root has the name `single_name`. Sources without such a table or
/// columns are left out. Used by the migration to schema version 2, which does not trust the
/// `conversion` attribute and takes the stored scaling whatever it says.
pub fn stored_scalings(path: &str, single_name: &str) -> Result<HashMap<String, Vec<(f64, f64)>>> {
    let file = H5File::open(path)?;
    let budget = super::budget(path)?;
    let mut result = HashMap::new();
    let mut read = |prefix: &str, name: &str| -> Result<()> {
        let Ok(ds) = file.dataset(&format!("{prefix}sensors")) else { return Ok(()) };
        let table = Table::read(&ds, budget)?;
        if table.has("scaling_factor") && table.has("offset") {
            let factors = table.f64_column("scaling_factor")?;
            let offsets = table.f64_column("offset")?;
            result.insert(name.to_string(), factors.into_iter().zip(offsets).collect());
        }
        Ok(())
    };
    if has_attr(&file, "sources") && file.root_group().group(SOURCES_GROUP).is_ok() {
        for name in source_names(&file, path)? {
            read(&format!("{SOURCES_GROUP}/{name}/"), &name)?;
        }
    } else {
        read("", single_name)?;
    }
    Ok(result)
}
