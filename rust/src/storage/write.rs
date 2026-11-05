//! Writes the PyTables-style HDF5 layout of ICOschema, like `icoschema/storage/python/hdf5.py`:
//! the lowest format version that can hold the data ("1.0" recording, "1.1" with a preprocessed
//! table, "1.2" with steps), every dataset of more than one element chunked and compressed with
//! gzip level 4 plus shuffle, computations under `/computations/` in their true N-D shape.
//!
//! Every generated struct is taken apart *without* `..`, so a field added to the LinkML schema
//! breaks the build here until the writer decides what to do with it.
//!
//! Where Python quietly does something lossy, this writer returns an error instead: a
//! compensation other than `NoConversion`/`LinearConversion` (the file format has no place for
//! it), a channel gap, a value that does not fit its column, a string longer than its field, an
//! unknown computation dtype. Files are written to `<path>.tmp` and renamed, so a failed write
//! never leaves a half-written file under the real name.

use std::collections::HashMap;
use std::path::Path;

use icoschema_gen as g;
use rust_hdf5::format::messages::datatype::{CompoundMember, DatatypeMessage};
use rust_hdf5::types::VarLenUnicode;
use rust_hdf5::{H5Dataset, H5File, H5Group};

use super::hdf5::{source_name, status_name};
use crate::{invalid, Error, Result};

const PRIMARY_TABLE: &str = "recording";
const PREPROCESSED_TABLE: &str = "preprocessed";
const GZIP_LEVEL: u32 = 4;
/// Target chunk size; chunks hold about this many bytes before compression.
const CHUNK_BYTES: usize = 64 * 1024;

/// What goes into a file besides the primary recording.
pub struct Parts<'a> {
    pub recording: &'a g::Recording,
    pub preprocessed: Option<&'a g::PreprocessedRecording>,
    pub computations: &'a HashMap<String, g::DerivedDataset>,
    pub steps: &'a [g::ComputationStep],
}

pub fn save_recording(recording: &g::Recording, path: &str) -> Result<()> {
    let empty = HashMap::new();
    save(Parts { recording, preprocessed: None, computations: &empty, steps: &[] }, path)
}

pub fn save(parts: Parts, path: &str) -> Result<()> {
    let target = Path::new(path);
    if let Some(parent) = target.parent().filter(|p| !p.as_os_str().is_empty()) {
        std::fs::create_dir_all(parent).map_err(|e| Error::Invalid(format!("{path}: {e}")))?;
    }
    let temporary = format!("{path}.tmp");
    let result = write_file(&parts, &temporary)
        .and_then(|()| std::fs::rename(&temporary, target).map_err(|e| Error::Invalid(format!("{path}: {e}"))));
    if result.is_err() {
        let _ = std::fs::remove_file(&temporary);
    }
    result
}

fn write_file(parts: &Parts, path: &str) -> Result<()> {
    let file = H5File::create(path)?;
    // Superblock 2 instead of the default 3: readable by every HDF5 since 1.8.
    file.set_libver_latest(false)?;

    let version = if !parts.steps.is_empty() {
        "1.2"
    } else if parts.preprocessed.is_some() {
        "1.1"
    } else {
        "1.0"
    };
    file.set_attr_string("icoschema_format_version", version)?;
    file.set_attr_string("primary_table", PRIMARY_TABLE)?;
    write_recording_table(&file, parts.recording)?;
    if let Some(preprocessed) = parts.preprocessed {
        file.set_attr_string("preprocessed_table", PREPROCESSED_TABLE)?;
        write_preprocessed_table(&file, preprocessed)?;
    }
    if !parts.steps.is_empty() {
        write_steps(&file, parts.steps)?;
    }
    if !parts.computations.is_empty() {
        write_computations(&file, parts.computations)?;
    }
    file.close()?;
    Ok(())
}

// ── tables ──────────────────────────────────────────────────────────────────

fn member(name: &str, offset: usize, datatype: DatatypeMessage) -> CompoundMember {
    CompoundMember { name: name.into(), offset: offset as u32, datatype }
}

fn fixed_string(size: usize) -> DatatypeMessage {
    // NUL padded ASCII, like numpy's `S<size>`.
    DatatypeMessage::FixedString { size: size as u32, padding: 1, charset: 0 }
}

/// Chunk shape of about `CHUNK_BYTES`, filling the last dimensions first.
fn chunk_dims(shape: &[usize], element_size: usize) -> Vec<usize> {
    let mut remaining = (CHUNK_BYTES / element_size.max(1)).max(1);
    let mut chunk = vec![1; shape.len()];
    for (i, dim) in shape.iter().enumerate().rev() {
        chunk[i] = (*dim).min(remaining).max(1);
        remaining = (remaining / chunk[i]).max(1);
    }
    chunk
}

fn table(file: &H5File, name: &str, row_size: usize, members: Vec<CompoundMember>, rows: usize, raw: &[u8]) -> Result<H5Dataset> {
    debug_assert_eq!(raw.len(), rows * row_size);
    let mut builder = file
        .new_dataset::<u8>()
        .datatype(DatatypeMessage::Compound { size: row_size as u32, members })
        .shape(&[rows]);
    if rows > 1 {
        builder = builder.chunk(&chunk_dims(&[rows], row_size)).shuffle_deflate(GZIP_LEVEL);
    }
    let dataset = builder.create(name)?;
    dataset.write_raw_bytes(raw)?;
    Ok(dataset)
}

fn string_attr(dataset: &H5Dataset, name: &str, value: &str) -> Result<()> {
    Ok(dataset.new_attr::<VarLenUnicode>().shape(()).create(name)?.write_string(value)?)
}

fn int_attr(dataset: &H5Dataset, name: &str, value: i64) -> Result<()> {
    Ok(dataset.new_attr::<i64>().shape(()).create(name)?.write_numeric(&value)?)
}

fn float_attr(dataset: &H5Dataset, name: &str, value: f64) -> Result<()> {
    Ok(dataset.new_attr::<f64>().shape(()).create(name)?.write_numeric(&value)?)
}

fn optional_string_attr(dataset: &H5Dataset, name: &str, value: &Option<String>) -> Result<()> {
    value.as_deref().map_or(Ok(()), |v| string_attr(dataset, name, v))
}

fn u8_value(name: &str, value: isize) -> Result<u8> {
    u8::try_from(value).or_else(|_| invalid(format!("{name} value {value} does not fit in 8 bits")))
}

fn u64_value(name: &str, value: isize) -> Result<u64> {
    u64::try_from(value).or_else(|_| invalid(format!("{name} value {value} is negative")))
}

/// The channels present, in order. A channel after a missing one cannot be stored: the file
/// format names the columns channel1.. by position.
fn present_channels<'a>(channels: [Option<&'a [f64]>; 3]) -> Result<Vec<&'a [f64]>> {
    let mut present = Vec::new();
    for (i, channel) in channels.into_iter().enumerate() {
        match channel.filter(|c| !c.is_empty()) {
            Some(values) if present.len() == i => present.push(values),
            Some(_) => return invalid(format!("channel{} has data but an earlier channel has none", i + 1)),
            None => {}
        }
    }
    if present.is_empty() {
        return invalid("a recording needs at least channel1");
    }
    Ok(present)
}

fn channel_members(count: usize, first_offset: usize) -> Vec<CompoundMember> {
    (0..count).map(|i| member(&format!("channel{}", i + 1), first_offset + 4 * i, DatatypeMessage::f32_type())).collect()
}

fn write_recording_table(file: &H5File, recording: &g::Recording) -> Result<()> {
    let g::RecordingData { timestamp, counter, channel1, channel2, channel3 } = &recording.recording_data;
    let g::HardwareMetadata {
        revision,
        adc_reference_voltage,
        adc_prescaler,
        adc_acquisition_time,
        adc_oversample_rate,
        channel1_metadata,
        channel2_metadata,
        channel3_metadata,
    } = &recording.hardware_metadata;
    let g::RecordingMetadata { start_time, pre_metadata, post_metadata } = &recording.recording_metadata;
    if revision.is_some() {
        return invalid("hardware_metadata.revision is not stored by the file format");
    }
    let rows = timestamp.len();
    if rows == 0 {
        return invalid("a recording needs at least one sample");
    }
    let channels = present_channels([Some(channel1), channel2.as_deref(), channel3.as_deref()])?;
    if counter.len() != rows || channels.iter().any(|c| c.len() != rows) {
        return invalid("timestamp, counter and channel columns must have the same length");
    }

    let metadata = [Some(channel1_metadata), channel2_metadata.as_ref(), channel3_metadata.as_ref()];
    let mut converted_states = Vec::new();
    let mut sensor_rows = Vec::new();
    for (i, _) in channels.iter().enumerate() {
        let meta = metadata[i].ok_or_else(|| Error::Invalid(format!("channel{} has data but no metadata", i + 1)))?;
        let (converted, scaling_factor, offset) = channel_conversion(i + 1, meta)?;
        converted_states.push(converted);
        sensor_rows.push((&meta.sensor, scaling_factor, offset));
    }
    if converted_states.windows(2).any(|w| w[0] != w[1]) {
        return invalid(
            "cannot write a recording whose channels have different already-converted states: \
             the file format has a single table-level `conversion` flag",
        );
    }
    let converted = converted_states[0];
    // Nothing to say about the sensors: write no table, so the file reads back the same way.
    if converted && sensor_rows.iter().all(|(s, _, _)| is_unspecified(s)) {
        sensor_rows.clear();
    }

    // counter u1, timestamp u8, channelN f4: 9 + 4 * channels bytes per row.
    let row_size = 9 + 4 * channels.len();
    let mut raw = Vec::with_capacity(rows * row_size);
    for row in 0..rows {
        raw.push(u8_value("counter", counter[row])?);
        raw.extend_from_slice(&u64_value("timestamp", timestamp[row])?.to_le_bytes());
        for channel in &channels {
            raw.extend_from_slice(&(channel[row] as f32).to_le_bytes());
        }
    }
    let mut members = vec![
        member("counter", 0, DatatypeMessage::u8_type()),
        member("timestamp", 1, DatatypeMessage::u64_type()),
    ];
    members.extend(channel_members(channels.len(), 9));
    let dataset = table(file, PRIMARY_TABLE, row_size, members, rows, &raw)?;

    string_attr(&dataset, "Start_Time", start_time.as_deref().unwrap_or(""))?;
    string_attr(&dataset, "adc_reference_voltage", adc_reference_voltage.as_deref().unwrap_or(""))?;
    string_attr(&dataset, "conversion", if converted { "true" } else { "false" })?;
    optional_string_attr(&dataset, "pre_metadata", pre_metadata)?;
    optional_string_attr(&dataset, "post_metadata", post_metadata)?;
    for (name, value) in [
        ("adc_prescaler", *adc_prescaler),
        ("adc_acquisition_time", *adc_acquisition_time),
        ("adc_oversample_rate", *adc_oversample_rate),
    ] {
        if let Some(value) = value {
            int_attr(&dataset, name, value as i64)?;
        }
    }
    if !sensor_rows.is_empty() {
        write_sensors(file, &sensor_rows)?;
    }
    Ok(())
}

/// `(already converted, scaling_factor, offset)`. Only `NoConversion` and `LinearConversion` have
/// a place in the file format (as the `conversion` flag and the sensor's `scaling_factor`/`offset`).
fn channel_conversion(channel: usize, meta: &g::ChannelMetadata) -> Result<(bool, f64, f64)> {
    match meta.compensations.as_slice() {
        [g::CompensationOrSubtype::NoConversion(_)] => Ok((true, 1.0, 0.0)),
        [g::CompensationOrSubtype::LinearConversion(l)] => Ok((false, l.gain, l.offset)),
        [other] => invalid(format!(
            "channel{channel}: {} is {}",
            compensation_name(other),
            crate::schema_support::NOT_IN_FILE_FORMAT
        )),
        many => invalid(format!(
            "channel{channel} has {} compensations; the file format holds exactly one (NoConversion or LinearConversion)",
            many.len()
        )),
    }
}

fn compensation_name(c: &g::CompensationOrSubtype) -> &'static str {
    match c {
        g::CompensationOrSubtype::Conversion(_) => "Conversion",
        g::CompensationOrSubtype::FrequencyCompensation(_) => "FrequencyCompensation",
        g::CompensationOrSubtype::NoConversion(_) => "NoConversion",
        g::CompensationOrSubtype::LinearConversion(_) => "LinearConversion",
        g::CompensationOrSubtype::PolynomialConversion(_) => "PolynomialConversion",
    }
}

fn is_unspecified(sensor: &g::Sensor) -> bool {
    let g::Sensor { sensor_id, sensor_type, name, unit, dimension, phys_min, phys_max, volt_min, volt_max } = sensor;
    [sensor_id, sensor_type, name, unit, dimension].iter().all(|v| v.is_none())
        && [phys_min, phys_max, volt_min, volt_max].iter().all(|v| v.is_none())
}

/// Row layout of the `sensors` table (434 bytes), field order as numpy sorts them in Python.
fn write_sensors(file: &H5File, rows: &[(&g::Sensor, f64, f64)]) -> Result<()> {
    let f4 = DatatypeMessage::f32_type;
    let members = vec![
        member("dimension", 0, fixed_string(100)),
        member("name", 100, fixed_string(100)),
        member("offset", 200, f4()),
        member("phys_max", 204, f4()),
        member("phys_min", 208, f4()),
        member("scaling_factor", 212, f4()),
        member("sensor_id", 216, fixed_string(100)),
        member("sensor_type", 316, fixed_string(100)),
        member("unit", 416, fixed_string(10)),
        member("volt_max", 426, f4()),
        member("volt_min", 430, f4()),
    ];
    let mut raw = Vec::with_capacity(rows.len() * 434);
    for (sensor, scaling_factor, offset) in rows {
        let g::Sensor { sensor_id, sensor_type, name, unit, dimension, phys_min, phys_max, volt_min, volt_max } = sensor;
        let text = |what: &str, value: &Option<String>, size: usize| -> Result<Vec<u8>> {
            let mut bytes = value.clone().unwrap_or_default().into_bytes();
            if bytes.len() > size {
                return invalid(format!("sensor {what} {value:?} does not fit in {size} bytes"));
            }
            bytes.resize(size, 0);
            Ok(bytes)
        };
        let float = |v: f64| (v as f32).to_le_bytes();
        raw.extend(text("dimension", dimension, 100)?);
        raw.extend(text("name", name, 100)?);
        raw.extend(float(*offset));
        raw.extend(float(phys_max.unwrap_or(0.0)));
        raw.extend(float(phys_min.unwrap_or(0.0)));
        raw.extend(float(*scaling_factor));
        raw.extend(text("sensor_id", sensor_id, 100)?);
        raw.extend(text("sensor_type", sensor_type, 100)?);
        raw.extend(text("unit", unit, 10)?);
        raw.extend(float(volt_max.unwrap_or(0.0)));
        raw.extend(float(volt_min.unwrap_or(0.0)));
    }
    table(file, "sensors", 434, members, rows.len(), &raw)?;
    Ok(())
}

fn write_preprocessed_table(file: &H5File, p: &g::PreprocessedRecording) -> Result<()> {
    let g::PreprocessedRecording {
        timestamp,
        channel1,
        channel2,
        channel3,
        channel_sampling_frequency,
        sampling_frequency_source,
        fill_method,
        producer,
    } = p;
    let channels = present_channels([Some(channel1), channel2.as_deref(), channel3.as_deref()])?;
    let rows = timestamp.len();
    if channels.iter().any(|c| c.len() != rows) {
        return invalid("preprocessed timestamp and channel columns must have the same length");
    }
    let row_size = 8 + 4 * channels.len();
    let mut raw = Vec::with_capacity(rows * row_size);
    for row in 0..rows {
        raw.extend_from_slice(&u64_value("preprocessed timestamp", timestamp[row])?.to_le_bytes());
        for channel in &channels {
            raw.extend_from_slice(&(channel[row] as f32).to_le_bytes());
        }
    }
    let mut members = vec![member("timestamp", 0, DatatypeMessage::u64_type())];
    members.extend(channel_members(channels.len(), 8));
    let dataset = table(file, PREPROCESSED_TABLE, row_size, members, rows, &raw)?;
    float_attr(&dataset, "channel_sampling_frequency", *channel_sampling_frequency)?;
    string_attr(&dataset, "sampling_frequency_source", source_name(sampling_frequency_source))?;
    string_attr(&dataset, "fill_method", fill_method)?;
    string_attr(&dataset, "producer", producer)?;
    Ok(())
}

// ── steps ───────────────────────────────────────────────────────────────────

fn write_steps(file: &H5File, steps: &[g::ComputationStep]) -> Result<()> {
    let group = file.create_group("steps")?;
    for step in steps {
        let g::ComputationStep {
            node: name,
            step_index,
            producer,
            params,
            resolved_params,
            inputs,
            status,
            error,
            summary,
            output_keys,
            started_at,
            duration_s,
            environment,
        } = step;
        let node = group.create_group(name)?;
        node.set_attr_numeric("step_index", &(*step_index as i64))?;
        node.set_attr_string("producer", producer)?;
        let status = status.as_ref().map(status_name);
        for (name, value) in [
            ("params", params.as_deref()),
            ("resolved_params", resolved_params.as_deref()),
            ("status", status),
            ("error", error.as_deref()),
            ("summary", summary.as_deref()),
            ("started_at", started_at.as_deref()),
            ("environment", environment.as_deref()),
        ] {
            if let Some(value) = value {
                node.set_attr_string(name, value)?;
            }
        }
        if let Some(seconds) = duration_s {
            node.set_attr_numeric("duration_s", seconds)?;
        }
        for (name, list) in [("inputs", inputs), ("output_keys", output_keys)] {
            if let Some(list) = list {
                let refs: Vec<&str> = list.iter().map(String::as_str).collect();
                node.set_attr_string_array(name, &refs)?;
            }
        }
    }
    Ok(())
}

// ── computations ────────────────────────────────────────────────────────────

fn write_computations(file: &H5File, computations: &HashMap<String, g::DerivedDataset>) -> Result<()> {
    let mut entries: Vec<Entry> = Vec::new();
    for (key, derived) in computations {
        let segments: Vec<&str> = key.split('/').collect();
        if segments.iter().any(|s| s.is_empty() || *s == "." || *s == "..") {
            return invalid(format!("computation key {key:?} must be path segments separated by '/'"));
        }
        entries.push((segments, key, derived));
    }
    entries.sort_by(|a, b| a.0.cmp(&b.0)); // a stable file, whatever the map order
    write_tree(&file.create_group("computations")?, &entries, 0)
}

/// A computation: its key split into segments, the key itself, the data.
type Entry<'a> = (Vec<&'a str>, &'a String, &'a g::DerivedDataset);

/// Writes `entries` (key segments, data) below `parent`; `depth` segments are already consumed.
fn write_tree(parent: &H5Group, entries: &[Entry], depth: usize) -> Result<()> {
    let mut i = 0;
    while i < entries.len() {
        let name = entries[i].0[depth];
        let end = i + entries[i..].iter().take_while(|e| e.0[depth] == name).count();
        let same = &entries[i..end];
        let leaf = same.iter().any(|e| e.0.len() == depth + 1);
        if leaf && same.len() > 1 {
            return invalid(format!("computation key {:?} is both a dataset and a group", same[0].1));
        }
        if leaf {
            write_derived(parent, name, same[0].1, same[0].2)?;
        } else {
            write_tree(&parent.create_group(name)?, same, depth + 1)?;
        }
        i = end;
    }
    Ok(())
}

fn write_derived(parent: &H5Group, name: &str, key: &str, derived: &g::DerivedDataset) -> Result<()> {
    // `key` is the map key; the identifier stored inside is what the reader fills from the path.
    let g::DerivedDataset { key: _, values, shape, dtype, unit, produced_by, produced_at, params, description } = derived;
    let shape: Vec<usize> = shape
        .iter()
        .map(|d| usize::try_from(*d).or_else(|_| invalid(format!("computation {key:?} has a negative dimension"))))
        .collect::<Result<_>>()?;
    let elements: usize = shape.iter().product();
    if elements != values.len() {
        return invalid(format!("computation {key:?}: shape {shape:?} needs {elements} values, got {}", values.len()));
    }
    if shape.is_empty() {
        return invalid(format!("computation {key:?} has no dimensions; use shape [1] for a single value"));
    }

    macro_rules! write_as {
        ($t:ty, $convert:expr) => {{
            let data: Vec<$t> = values.iter().map(|v| $convert(key, *v)).collect::<Result<_>>()?;
            let mut builder = parent.new_dataset::<$t>().shape(&shape);
            if elements > 1 {
                builder = builder.chunk(&chunk_dims(&shape, std::mem::size_of::<$t>())).shuffle_deflate(GZIP_LEVEL);
            }
            let dataset = builder.create(name)?;
            dataset.write_raw(&data)?;
            dataset
        }};
    }
    let dataset = match dtype.as_str() {
        "float64" => write_as!(f64, |_: &str, v: f64| Ok::<_, Error>(v)),
        "float32" => write_as!(f32, |_: &str, v: f64| Ok::<_, Error>(v as f32)),
        "int64" => write_as!(i64, int_value::<i64>),
        "int32" => write_as!(i32, int_value::<i32>),
        "int16" => write_as!(i16, int_value::<i16>),
        "int8" => write_as!(i8, int_value::<i8>),
        "uint64" => write_as!(u64, int_value::<u64>),
        "uint32" => write_as!(u32, int_value::<u32>),
        "uint16" => write_as!(u16, int_value::<u16>),
        "uint8" => write_as!(u8, int_value::<u8>),
        other => {
            return invalid(format!(
                "computation {key:?}: dtype {other:?} is not supported (float32, float64 and the (u)int8 to 64 types are)"
            ))
        }
    };
    for (attr, value) in [
        ("unit", unit),
        ("produced_by", produced_by),
        ("produced_at", produced_at),
        ("params", params),
        ("description", description),
    ] {
        optional_string_attr(&dataset, attr, value)?;
    }
    Ok(())
}

/// A value for an integer dtype: it must be integral and in range (numpy would truncate).
fn int_value<T: TryFrom<i128>>(key: &str, value: f64) -> Result<T> {
    if value.fract() != 0.0 || !value.is_finite() {
        return invalid(format!("computation {key:?}: {value} is not an integer"));
    }
    T::try_from(value as i128).or_else(|_| invalid(format!("computation {key:?}: {value} is out of range for its dtype")))
}
