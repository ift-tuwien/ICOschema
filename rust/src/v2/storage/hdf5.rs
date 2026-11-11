//! Reads the PyTables-style HDF5 layout of ICOschema, format "2.0" (`icoschema_format_version`). Mirrors
//! `icoschema/v2/storage/hdf5.py`:
//!
//! - a primary table (named by the root attribute `primary_table`) with a `timestamp` column, an optional `counter`
//!   column and one column per channel (1 to 3), and a `sensors` table with one row per channel: the sensor
//!   (`sensor_id`, `sensor_type`, `name`, `unit`, `dimension`) and its conversion (`conversion` "none" or "linear",
//!   `gain`, `offset`);
//! - the source is at the root, or, with the root attribute `sources`, one group per source under `/sources/`
//!   (each with its table, `sensors` table, optional `quality` dataset and optional preprocessed table);
//! - optional `/steps/` and `/computations/`; the root attributes `source_format`, `source_format_version`,
//!   `reader` and `writer` are the bundle's provenance.
//!
//! A file without a version is of schema version 1, and another major version is another schema version:
//! both are refused here, with a message naming the module that reads them.

use std::collections::HashMap;

use icoschema_gen_v2 as g;
use rust_hdf5::{DatatypeMessage, H5Dataset, H5File, H5Group};

use super::table::Table;
use super::vlen;
use crate::{invalid, Error, Result};

pub(super) const FORMAT_VERSION: &str = "2.0";
const SUPPORTED: [&str; 1] = [FORMAT_VERSION];
pub(super) const CONVERSION_NONE: &str = "none";
pub(super) const CONVERSION_LINEAR: &str = "linear";
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

/// The format version of the file; an error for one this reader does not know.
pub fn format_version(file: &H5File, path: &str) -> Result<String> {
    let Some(version) = opt_str(file, "icoschema_format_version")? else {
        return invalid(format!(
            "{path:?} has no icoschema_format_version: it is a file of schema version 1, read with icoschema::v1"
        ));
    };
    if !SUPPORTED.contains(&version.as_str()) {
        let major = version.split('.').next().unwrap_or("");
        let hint = if !major.is_empty() && major.chars().all(|c| c.is_ascii_digit()) && major != "2" {
            format!(" (schema version {major}: read it with icoschema::v{major})")
        } else {
            String::new()
        };
        return invalid(format!(
            "unsupported icoschema_format_version {version:?} in {path:?}{hint}; supported: {SUPPORTED:?}"
        ));
    }
    Ok(version)
}

/// Whether the sources are stored one group each under `/sources/` rather than as one table at the root.
fn has_sources_layout(file: &H5File) -> bool {
    has_attr(file, "sources")
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
    format_version(file, path)?;
    let table_name = req_str(file, "primary_table")?;
    if !has_sources_layout(file) {
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
        Ok(s) => Table::read(&s, budget)?,
        Err(_) => return invalid(format!("table {table_name:?} has no `sensors` table")),
    };
    let channel_columns: Vec<&str> =
        table.column_names().filter(|n| !matches!(*n, "counter" | "timestamp")).collect();
    if channel_columns.len() != sensors.len() {
        return invalid(format!(
            "expected one sensor row per channel column, got {} channel column(s) and {} sensor row(s)",
            channel_columns.len(),
            sensors.len()
        ));
    }
    if channel_columns.len() > 3 {
        return invalid(format!("at most 3 channels supported, got {}", channel_columns.len()));
    }

    let channel = |i: usize| -> Result<g::ChannelMetadata> {
        Ok(g::ChannelMetadata { sensor: sensor_row(&sensors, i)?, conversion: conversion_row(&sensors, i)? })
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
        description: opt_str(&ds, "description")?,
        stu_mac: opt_str(&ds, "stu_mac")?,
        sth_mac: opt_str(&ds, "sth_mac")?,
        sampling_frequency: opt_float(&ds, "sampling_frequency")?,
        quality: quality_from(file, budget, prefix)?,
        additional_data: opt_str(&ds, "additional_data")?,
        hardware_metadata: hardware,
        recording_metadata: g::RecordingMetadata {
            start_time: opt_str(&ds, "Start_Time")?,
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

/// A text cell of the sensors table; an empty one is a value that was not set.
fn text_cell(t: &Table, column: &str, i: usize) -> Result<Option<String>> {
    let value = t.string_column(column)?.swap_remove(i);
    Ok(if value.is_empty() { None } else { Some(value) })
}

fn sensor_row(t: &Table, i: usize) -> Result<g::Sensor> {
    Ok(g::Sensor {
        sensor_id: text_cell(t, "sensor_id", i)?,
        sensor_type: text_cell(t, "sensor_type", i)?,
        name: text_cell(t, "name", i)?,
        unit: text_cell(t, "unit", i)?,
        dimension: text_cell(t, "dimension", i)?,
    })
}

fn conversion_row(t: &Table, i: usize) -> Result<g::ConversionOrSubtype> {
    let kind = t.string_column("conversion")?.swap_remove(i);
    match kind.as_str() {
        CONVERSION_NONE => Ok(g::ConversionOrSubtype::NoConversion(g::NoConversion { conversion_type: None })),
        CONVERSION_LINEAR => Ok(g::ConversionOrSubtype::LinearConversion(g::LinearConversion {
            gain: t.f64_column("gain")?[i],
            offset: t.f64_column("offset")?[i],
            conversion_type: None,
        })),
        other => invalid(format!("unknown conversion {other:?} in the sensors table (known: 'none', 'linear')")),
    }
}

// ── PreprocessedRecording, computations, steps ──────────────────────────────

/// The preprocessed tables of the file (none for a file without any): the one at the root for a single source at
/// the root, one per source group that has one for the sources layout. Each gets its source's name.
fn preprocessed_from(file: &H5File, sources: &[g::Source], budget: u64) -> Result<Vec<g::PreprocessedRecording>> {
    let Some(table_name) = opt_str(file, "preprocessed_table")? else { return Ok(vec![]) };
    if !has_sources_layout(file) {
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

fn steps_from(file: &H5File, path: &str) -> Result<Vec<g::ComputationStep>> {
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
    let version = format_version(&file, path)?;
    let sources = sources_from(&file, path, budget)?;
    let mut computations = HashMap::new();
    if let Ok(group) = file.root_group().group("computations") {
        collect_computations(&file, budget, &group, "", &mut computations)?;
    }
    Ok(Loaded {
        preprocessed: preprocessed_from(&file, &sources, budget)?,
        steps: steps_from(&file, path)?,
        provenance: provenance_from(&file, &version)?,
        sources,
        computations,
    })
}

/// What the file says about where its data came from; a file that says nothing is data read from
/// HDF5 of its own format version.
fn provenance_from(file: &H5File, version: &str) -> Result<g::Provenance> {
    let (source_format, source_format_version, reader) = if has_attr(file, "source_format") {
        (opt_str(file, "source_format")?, opt_str(file, "source_format_version")?, opt_str(file, "reader")?)
    } else {
        (Some("hdf5".to_string()), Some(version.to_string()), Some(super::software_id()))
    };
    Ok(g::Provenance { source_format, source_format_version, reader, writer: opt_str(file, "writer")? })
}
