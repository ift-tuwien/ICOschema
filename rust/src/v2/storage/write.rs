//! Writes the PyTables-style HDF5 layout of ICOschema, format "2.0", like `icoschema/v2/storage/hdf5.py`:
//! a primary table and a `sensors` table (the sensor and the conversion of each channel) per source, at the
//! root for a single source or under `/sources/<name>/` for several, an optional preprocessed table, steps and
//! computations; every dataset of more than one element chunked and compressed with gzip level 4 plus shuffle,
//! computations under `/computations/` in their true N-D shape. Every file also gets the root attribute
//! `writer`, and the provenance's `source_format`, `source_format_version` and `reader` if the bundle has one.
//!
//! Every generated struct is taken apart *without* `..`, so a field added to the LinkML schema
//! breaks the build here until the writer decides what to do with it.
//!
//! Where Python quietly does something lossy, this writer returns an error instead: a channel gap, a value that
//! does not fit its column, a string longer than its field, an unknown computation dtype. Files are written to
//! `<path>.tmp` and renamed, so a failed write never leaves a half-written file under the real name.

use std::collections::HashMap;
use std::path::Path;

use icoschema_gen_v2 as g;
use rust_hdf5::format::messages::datatype::{CompoundMember, DatatypeMessage};
use rust_hdf5::types::VarLenUnicode;
use rust_hdf5::{H5Dataset, H5File, H5Group};

use super::hdf5::{
    source_name, status_name, CONVERSION_LINEAR, CONVERSION_NONE, FORMAT_VERSION, QUALITY_DATASET,
    SOURCES_GROUP,
};
use crate::{invalid, Error, Result};

const PRIMARY_TABLE: &str = "recording";
const PREPROCESSED_TABLE: &str = "preprocessed";
const GZIP_LEVEL: u32 = 4;
/// Target chunk size; chunks hold about this many bytes before compression.
const CHUNK_BYTES: usize = 64 * 1024;

/// What goes into a file.
pub struct Parts<'a> {
    /// In file order; at least one.
    pub sources: Vec<&'a g::Source>,
    /// Each with the name of the source it belongs to.
    pub preprocessed: Vec<(&'a str, &'a g::PreprocessedRecording)>,
    pub computations: &'a HashMap<String, g::DerivedDataset>,
    pub steps: &'a [g::ComputationStep],
    pub provenance: Option<&'a g::Provenance>,
    /// The format version to write: `None` or `FORMAT_VERSION` (the only one). Anything else is an error.
    pub format_version: Option<&'a str>,
}

/// Every format version the writer can write.
pub fn writable_versions() -> Vec<&'static str> {
    vec![FORMAT_VERSION]
}

pub fn save_sources(sources: Vec<&g::Source>, path: &str) -> Result<()> {
    save_sources_as(sources, path, None)
}

/// `save_sources` in the format version `format_version` (`None`: the oldest that fits).
pub fn save_sources_as(sources: Vec<&g::Source>, path: &str, format_version: Option<&str>) -> Result<()> {
    let empty = HashMap::new();
    save(
        Parts { sources, preprocessed: vec![], computations: &empty, steps: &[], provenance: None, format_version },
        path,
    )
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
    if parts.sources.is_empty() {
        return invalid("a recording needs at least one source");
    }
    let mut seen = std::collections::HashSet::new();
    for source in &parts.sources {
        let name = &source.name;
        if name.is_empty() || name.contains('/') || name.starts_with('.') {
            return invalid(format!("source name {name:?} must be non-empty, contain no '/' and not start with '.'"));
        }
        if !seen.insert(name.as_str()) {
            return invalid(format!("duplicate source name {name:?}"));
        }
    }

    if let Some(requested) = parts.format_version.filter(|v| *v != FORMAT_VERSION) {
        return invalid(format!("cannot write format_version {requested:?}; writable versions: {:?}", writable_versions()));
    }
    let file = H5File::create(path)?;
    // Superblock 2 instead of the default 3: readable by every HDF5 since 1.8.
    file.set_libver_latest(false)?;

    let multiple = parts.sources.len() > 1;
    file.set_attr_string("icoschema_format_version", FORMAT_VERSION)?;
    file.set_attr_string("primary_table", PRIMARY_TABLE)?;
    file.set_attr_string("writer", &super::software_id())?;
    if let Some(provenance) = parts.provenance {
        let g::Provenance { source_format, source_format_version, reader, writer: _ } = provenance;
        for (name, value) in
            [("source_format", source_format), ("source_format_version", source_format_version), ("reader", reader)]
        {
            if let Some(value) = value {
                file.set_attr_string(name, value)?;
            }
        }
    }

    let root = file.root_group();
    if multiple {
        let names: Vec<&str> = parts.sources.iter().map(|s| s.name.as_str()).collect();
        file.set_attr_string_array("sources", &names)?;
        let sources = file.create_group(SOURCES_GROUP)?;
        for source in &parts.sources {
            write_source_table(&sources.create_group(&source.name)?, source, false)?;
        }
    } else {
        write_source_table(&root, parts.sources[0], true)?;
    }

    if !parts.preprocessed.is_empty() {
        file.set_attr_string("preprocessed_table", PREPROCESSED_TABLE)?;
        for (name, table) in &parts.preprocessed {
            if !seen.contains(name) {
                return invalid(format!("preprocessed table for unknown source {name:?}"));
            }
            if multiple {
                write_preprocessed_table(&file.root_group().group(SOURCES_GROUP)?.group(name)?, table)?;
            } else {
                write_preprocessed_table(&root, table)?;
            }
        }
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

fn table(parent: &H5Group, name: &str, row_size: usize, members: Vec<CompoundMember>, rows: usize, raw: &[u8]) -> Result<H5Dataset> {
    debug_assert_eq!(raw.len(), rows * row_size);
    let mut builder = parent
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

/// A source's table, its `sensors` table and its `quality` dataset (if it has one) into `parent` (the root of the
/// file or a source group). A single source's name is always stored (`store_name`); a source in a group is named
/// by the group.
fn write_source_table(parent: &H5Group, source: &g::Source, store_name: bool) -> Result<()> {
    let g::Source {
        name,
        description,
        stu_mac,
        sth_mac,
        sampling_frequency,
        quality,
        additional_data,
        hardware_metadata,
        recording_metadata,
        recording_data,
    } = source;
    let g::RecordingData { timestamp, counter, channel1, channel2, channel3 } = recording_data;
    let g::HardwareMetadata {
        revision,
        adc_reference_voltage,
        adc_prescaler,
        adc_acquisition_time,
        adc_oversample_rate,
        channel1_metadata,
        channel2_metadata,
        channel3_metadata,
    } = hardware_metadata;
    let g::RecordingMetadata { start_time, pre_metadata, post_metadata } = recording_metadata;
    if revision.is_some() {
        return invalid("hardware_metadata.revision is not stored by the file format");
    }
    let rows = timestamp.len();
    if rows == 0 {
        return invalid("a recording needs at least one sample");
    }
    let counter = counter.as_deref().filter(|c| !c.is_empty());
    let channels = present_channels([Some(channel1), channel2.as_deref(), channel3.as_deref()])?;
    if counter.is_some_and(|c| c.len() != rows) || channels.iter().any(|c| c.len() != rows) {
        return invalid("timestamp, counter and channel columns must have the same length");
    }

    let metadata = [Some(channel1_metadata), channel2_metadata.as_ref(), channel3_metadata.as_ref()];
    let mut sensor_rows = Vec::new();
    for (i, _) in channels.iter().enumerate() {
        let meta = metadata[i].ok_or_else(|| Error::Invalid(format!("channel{} has data but no metadata", i + 1)))?;
        sensor_rows.push((&meta.sensor, conversion_row(&meta.conversion)));
    }

    // [counter u1,] timestamp u8, channelN f4 per row.
    let counter_size = usize::from(counter.is_some());
    let row_size = counter_size + 8 + 4 * channels.len();
    let mut raw = Vec::with_capacity(rows * row_size);
    for row in 0..rows {
        if let Some(counter) = counter {
            raw.push(u8_value("counter", counter[row])?);
        }
        raw.extend_from_slice(&u64_value("timestamp", timestamp[row])?.to_le_bytes());
        for channel in &channels {
            raw.extend_from_slice(&(channel[row] as f32).to_le_bytes());
        }
    }
    let mut members = Vec::new();
    if counter.is_some() {
        members.push(member("counter", 0, DatatypeMessage::u8_type()));
    }
    members.push(member("timestamp", counter_size, DatatypeMessage::u64_type()));
    members.extend(channel_members(channels.len(), counter_size + 8));
    let dataset = table(parent, PRIMARY_TABLE, row_size, members, rows, &raw)?;

    optional_string_attr(&dataset, "Start_Time", start_time)?;
    optional_string_attr(&dataset, "adc_reference_voltage", adc_reference_voltage)?;
    optional_string_attr(&dataset, "pre_metadata", pre_metadata)?;
    optional_string_attr(&dataset, "post_metadata", post_metadata)?;
    optional_string_attr(&dataset, "description", description)?;
    optional_string_attr(&dataset, "stu_mac", stu_mac)?;
    optional_string_attr(&dataset, "sth_mac", sth_mac)?;
    if store_name {
        string_attr(&dataset, "source_name", name)?;
    }
    if let Some(frequency) = sampling_frequency {
        float_attr(&dataset, "sampling_frequency", *frequency)?;
    }
    optional_string_attr(&dataset, "additional_data", additional_data)?;
    for (attr, value) in [
        ("adc_prescaler", *adc_prescaler),
        ("adc_acquisition_time", *adc_acquisition_time),
        ("adc_oversample_rate", *adc_oversample_rate),
    ] {
        if let Some(value) = value {
            int_attr(&dataset, attr, value as i64)?;
        }
    }
    if let Some(g::QualityChannel { values, sampling_frequency }) = quality {
        if !values.is_empty() {
            let data: Vec<f32> = values.iter().map(|v| *v as f32).collect();
            let mut builder = parent.new_dataset::<f32>().shape(&[data.len()]);
            if data.len() > 1 {
                builder = builder.chunk(&chunk_dims(&[data.len()], 4)).shuffle_deflate(GZIP_LEVEL);
            }
            let quality_ds = builder.create(QUALITY_DATASET)?;
            quality_ds.write_raw(&data)?;
            if let Some(frequency) = sampling_frequency {
                float_attr(&quality_ds, "sampling_frequency", *frequency)?;
            }
        }
    }
    write_sensors(parent, &sensor_rows)?;
    Ok(())
}

/// `(kind, gain, offset)` of a conversion as the `sensors` table stores it: "none" (gain 1, offset 0) or
/// "linear".
fn conversion_row(conversion: &g::ConversionOrSubtype) -> (&'static str, f64, f64) {
    match conversion {
        g::ConversionOrSubtype::NoConversion(_) => (CONVERSION_NONE, 1.0, 0.0),
        g::ConversionOrSubtype::LinearConversion(l) => (CONVERSION_LINEAR, l.gain, l.offset),
    }
}

/// Row layout of the `sensors` table (436 bytes), in the order of the Python dtype.
fn write_sensors(parent: &H5Group, rows: &[(&g::Sensor, (&'static str, f64, f64))]) -> Result<()> {
    let f8 = DatatypeMessage::f64_type;
    let members = vec![
        member("dimension", 0, fixed_string(100)),
        member("name", 100, fixed_string(100)),
        member("sensor_id", 200, fixed_string(100)),
        member("sensor_type", 300, fixed_string(100)),
        member("unit", 400, fixed_string(10)),
        member("conversion", 410, fixed_string(10)),
        member("gain", 420, f8()),
        member("offset", 428, f8()),
    ];
    let mut raw = Vec::with_capacity(rows.len() * 436);
    for (sensor, (kind, gain, offset)) in rows {
        let g::Sensor { sensor_id, sensor_type, name, unit, dimension } = sensor;
        let text = |what: &str, value: &Option<String>, size: usize| -> Result<Vec<u8>> {
            let mut bytes = value.clone().unwrap_or_default().into_bytes();
            if bytes.len() > size {
                return invalid(format!("sensor {what} {value:?} does not fit in {size} bytes"));
            }
            bytes.resize(size, 0);
            Ok(bytes)
        };
        raw.extend(text("dimension", dimension, 100)?);
        raw.extend(text("name", name, 100)?);
        raw.extend(text("sensor_id", sensor_id, 100)?);
        raw.extend(text("sensor_type", sensor_type, 100)?);
        raw.extend(text("unit", unit, 10)?);
        raw.extend(text("conversion", &Some((*kind).to_string()), 10)?);
        raw.extend(gain.to_le_bytes());
        raw.extend(offset.to_le_bytes());
    }
    table(parent, "sensors", 436, members, rows.len(), &raw)?;
    Ok(())
}

fn write_preprocessed_table(parent: &H5Group, p: &g::PreprocessedRecording) -> Result<()> {
    let g::PreprocessedRecording {
        timestamp,
        channel1,
        channel2,
        channel3,
        channel_sampling_frequency,
        sampling_frequency_source,
        fill_method,
        producer,
        source: _, // names the group it is written into
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
    let dataset = table(parent, PREPROCESSED_TABLE, row_size, members, rows, &raw)?;
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
            source_node,
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
            ("source_node", source_node.as_deref()),
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
