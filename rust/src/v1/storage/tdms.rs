//! Reads NI TDMS files (read-only), like `icoschema/v1/storage/tdms.py` -- the *legacy*
//! layout of the files written before TDMS files were versioned:
//!
//! - the `rawdata` group's channels (1 to 3, file order) become `channel1..3`, values scaled by
//!   the channel's NI scaling if it has one (linear and polynomial scales; other scale types are
//!   an error, as in `tdmspy`), so they are already in `unit_string`
//!   (`NoConversion`); the channels of a source must have the same length;
//! - the sampling frequency is `1 / wf_increment` (the channels must agree), the source has no
//!   packet counter and its timestamps are `round(i * 1e6 / fs)`;
//! - the `signalQuality` channels (100 = nothing lost) become the source's `quality`: a `system`
//!   group's channel applies to the whole file, otherwise every other group holding one is
//!   paired with a `rawdata` channel and the worst is kept;
//! - several STUs: with no `system` quality group, two or more other groups holding
//!   `signalQuality` and every `rawdata` channel named after exactly one of them (the longest
//!   match, `STU1_Channel1` belongs to `STU1`) make each such group a source of its own;
//! - `additional_data` (JSON) keeps the properties nothing else keeps: `file`, `group`,
//!   `channels` and `other_groups`.
//!
//! A root property `icoschema_format_version` selects a versioned layout; there is none yet, so a
//! file that has one is refused.
//!
//! The `tedium` crate reads the data and properties. It keeps groups and channels sorted by name,
//! not in file order, and the order matters here (it decides which channel is `channel1`, and
//! the order of the sources), so `scan_layout` reads the order from the segment headers itself.

use std::collections::{HashMap, HashSet};
use std::fs::File;
use std::io::{BufReader, Read, Seek, SeekFrom};
use std::path::Path;

use icoschema_gen_v1 as g;
use serde_json::{json, Map, Value};
use tedium::{ChannelPath, DataType, PropertyPath, PropertyValue, TdmsError, TdmsFile};

use crate::v1::model::format_micros;
use crate::{invalid, Error, Result};

const RAW_GROUP: &str = "rawdata";
const SYSTEM_GROUP: &str = "system";
const QUALITY_CHANNEL: &str = "signalQuality";
const MAX_CHANNELS: usize = 3;
const DEFAULT_SOURCE_NAME: &str = "source1";
const FORMAT_VERSION_PROPERTY: &str = "icoschema_format_version";
const LEGACY_VERSION: &str = "legacy";
/// Seconds between the TDMS epoch (1904-01-01) and the Unix epoch.
const UNIX_EPOCH_IN_TDMS_SECONDS: i64 = 2_082_844_800;
/// `NI_Scale[n]_*_Input_Source` of a scale that reads the raw data.
const RAW_DATA_INPUT_SOURCE: i64 = 0xFFFF_FFFF;

/// What a TDMS file holds, as the schema's sources.
pub struct Loaded {
    pub sources: Vec<g::Source>,
    /// The format version it was read as (`"legacy"` for a file without one).
    pub version: String,
    /// Things worth knowing that did not stop the read (Python raises a `UserWarning`).
    pub warnings: Vec<String>,
}

fn tdms_error(error: TdmsError) -> Error {
    let mut text = error.to_string();
    let mut source = std::error::Error::source(&error);
    while let Some(inner) = source {
        text.push_str(&format!(": {inner}"));
        source = inner.source();
    }
    Error::Invalid(text)
}

// ── the order of groups and channels in the file ────────────────────────────

/// Groups and their channels in the order they first appear in the file.
#[derive(Debug, Default)]
struct Layout {
    groups: Vec<(String, Vec<String>)>,
}

impl Layout {
    fn group_mut(&mut self, name: &str) -> &mut Vec<String> {
        if let Some(i) = self.groups.iter().position(|(n, _)| n == name) {
            return &mut self.groups[i].1;
        }
        self.groups.push((name.to_string(), Vec::new()));
        &mut self.groups.last_mut().unwrap().1
    }

    fn channels(&self, group: &str) -> &[String] {
        self.groups.iter().find(|(n, _)| n == group).map_or(&[], |(_, c)| c.as_slice())
    }

    fn has_group(&self, group: &str) -> bool {
        self.groups.iter().any(|(n, _)| n == group)
    }

    fn has_channel(&self, group: &str, channel: &str) -> bool {
        self.channels(group).iter().any(|c| c == channel)
    }
}

struct Bytes<R: Read> {
    inner: R,
    big_endian: bool,
}

impl<R: Read> Bytes<R> {
    fn array<const N: usize>(&mut self) -> Result<[u8; N]> {
        let mut buffer = [0u8; N];
        self.inner.read_exact(&mut buffer).map_err(|e| Error::Invalid(format!("truncated TDMS metadata: {e}")))?;
        Ok(buffer)
    }

    fn u32(&mut self) -> Result<u32> {
        let bytes = self.array::<4>()?;
        Ok(if self.big_endian { u32::from_be_bytes(bytes) } else { u32::from_le_bytes(bytes) })
    }

    fn u64(&mut self) -> Result<u64> {
        let bytes = self.array::<8>()?;
        Ok(if self.big_endian { u64::from_be_bytes(bytes) } else { u64::from_le_bytes(bytes) })
    }

    fn skip(&mut self, count: u64) -> Result<()> {
        let copied = std::io::copy(&mut (&mut self.inner).take(count), &mut std::io::sink())
            .map_err(|e| Error::Invalid(format!("truncated TDMS metadata: {e}")))?;
        if copied != count {
            return invalid("truncated TDMS metadata");
        }
        Ok(())
    }

    fn string(&mut self) -> Result<String> {
        let length = self.u32()? as usize;
        if length > (1 << 24) {
            return invalid(format!("implausible TDMS string length {length}"));
        }
        let mut bytes = vec![0u8; length];
        self.inner.read_exact(&mut bytes).map_err(|e| Error::Invalid(format!("truncated TDMS metadata: {e}")))?;
        String::from_utf8(bytes).map_err(|_| Error::Invalid("a TDMS name is not valid UTF-8".into()))
    }
}

/// `/'group'/'channel'` as its names; `''` inside a name is a quote.
fn path_components(path: &str) -> Result<Vec<String>> {
    let bad = || Error::Invalid(format!("invalid TDMS object path {path:?}"));
    let mut names = Vec::new();
    let mut chars = path.chars().peekable();
    while let Some(c) = chars.next() {
        if c != '/' {
            return Err(bad());
        }
        if chars.peek().is_none() {
            break; // the root is "/"
        }
        if chars.next() != Some('\'') {
            return Err(bad());
        }
        let mut name = String::new();
        loop {
            match chars.next() {
                None => return Err(bad()),
                Some('\'') if chars.peek() == Some(&'\'') => {
                    chars.next();
                    name.push('\'');
                }
                Some('\'') => break,
                Some(other) => name.push(other),
            }
        }
        names.push(name);
    }
    Ok(names)
}

/// The size in bytes of a property value of type `code`, or `None` for a string (length prefixed).
fn property_size(code: u32) -> Result<Option<u64>> {
    Ok(Some(match code {
        0 => 0,
        1 | 5 | 0x21 => 1,
        2 | 6 => 2,
        3 | 7 | 9 | 0x19 => 4,
        4 | 8 | 10 | 0x1A | 0x0800_000C => 8,
        0x0B | 0x1B | 0x44 | 0x1000_000D => 16,
        0x20 => return Ok(None),
        other => return invalid(format!("unknown TDMS property type {other:#x}")),
    }))
}

fn scan_layout(path: &str) -> Result<Layout> {
    let length = std::fs::metadata(path).map_err(|e| Error::Invalid(format!("{path}: {e}")))?.len();
    let mut file = BufReader::new(File::open(path).map_err(|e| Error::Invalid(format!("{path}: {e}")))?);
    let mut layout = Layout::default();
    let mut position = 0u64;
    while position + 28 <= length {
        file.seek(SeekFrom::Start(position)).map_err(|e| Error::Invalid(format!("{path}: {e}")))?;
        let mut lead_in = [0u8; 8];
        file.read_exact(&mut lead_in).map_err(|e| Error::Invalid(format!("{path}: {e}")))?;
        if &lead_in[..4] != b"TDSm" {
            return invalid(format!("{path}: no TDMS segment at byte {position}"));
        }
        let table_of_contents = u32::from_le_bytes(lead_in[4..8].try_into().unwrap());
        let mut bytes = Bytes { inner: file, big_endian: table_of_contents & (1 << 6) != 0 };
        let _version = bytes.u32()?;
        let next = bytes.u64()?;
        let _raw_data_offset = bytes.u64()?;

        if table_of_contents & (1 << 1) != 0 {
            let objects = bytes.u32()?;
            for _ in 0..objects {
                let components = path_components(&bytes.string()?)?;
                let index = bytes.u32()?;
                match index {
                    0xFFFF_FFFF | 0 => {}
                    0x1269 | 0x126A => return invalid(format!("{path}: DAQmx raw data is not supported")),
                    // the length counts its own four bytes (20 for a numeric channel)
                    length if length >= 4 => bytes.skip(u64::from(length) - 4)?,
                    _ => return invalid(format!("{path}: invalid TDMS raw data index length")),
                }
                for _ in 0..bytes.u32()? {
                    let _name = bytes.string()?;
                    let code = bytes.u32()?;
                    match property_size(code)? {
                        Some(size) => bytes.skip(size)?,
                        None => {
                            let length = bytes.u32()?;
                            bytes.skip(u64::from(length))?
                        }
                    }
                }
                match components.as_slice() {
                    [] => {}
                    [group] => {
                        layout.group_mut(group);
                    }
                    [group, channel] => {
                        let channels = layout.group_mut(group);
                        if !channels.contains(channel) {
                            channels.push(channel.clone());
                        }
                    }
                    _ => return invalid(format!("{path}: invalid TDMS object path with {} names", components.len())),
                }
            }
        }
        file = bytes.inner;
        if next == u64::MAX {
            break; // the last segment, still being written: it runs to the end of the file
        }
        position = match position.checked_add(28).and_then(|p| p.checked_add(next)) {
            Some(p) => p,
            None => return invalid(format!("{path}: the next segment address overflows")),
        };
    }
    Ok(layout)
}

// ── properties ──────────────────────────────────────────────────────────────

type Properties = HashMap<String, PropertyValue>;

fn numeric(value: &PropertyValue) -> Option<f64> {
    Some(match value {
        PropertyValue::I8(v) => f64::from(*v),
        PropertyValue::I16(v) => f64::from(*v),
        PropertyValue::I32(v) => f64::from(*v),
        PropertyValue::I64(v) => *v as f64,
        PropertyValue::U8(v) => f64::from(*v),
        PropertyValue::U16(v) => f64::from(*v),
        PropertyValue::U32(v) => f64::from(*v),
        PropertyValue::U64(v) => *v as f64,
        PropertyValue::SingleFloat(v) => f64::from(*v),
        PropertyValue::DoubleFloat(v) => *v,
        _ => return None,
    })
}

fn integer(value: &PropertyValue) -> Option<i64> {
    Some(match value {
        PropertyValue::I8(v) => i64::from(*v),
        PropertyValue::I16(v) => i64::from(*v),
        PropertyValue::I32(v) => i64::from(*v),
        PropertyValue::I64(v) => *v,
        PropertyValue::U8(v) => i64::from(*v),
        PropertyValue::U16(v) => i64::from(*v),
        PropertyValue::U32(v) => i64::from(*v),
        PropertyValue::U64(v) => i64::try_from(*v).ok()?,
        _ => return None,
    })
}

/// A TDMS timestamp as microseconds since the Unix epoch, like tdmspy's
/// `to_datetime64("us")`: the fraction (units of 2^-64 s) is truncated to whole microseconds.
fn timestamp_micros(seconds: i64, fractions: u64) -> i64 {
    let micros = (fractions as f64 / (18_446_744_073_709_551_616.0_f64 / 1e6)) as i64;
    (seconds - UNIX_EPOCH_IN_TDMS_SECONDS) * 1_000_000 + micros
}

fn timestamp_of(value: &PropertyValue) -> Option<i64> {
    match value {
        PropertyValue::Timestamp(time) => {
            let (seconds, fractions) = time.to_parts();
            Some(timestamp_micros(seconds, fractions))
        }
        _ => None,
    }
}

/// `value` as something JSON holds (timestamps as ISO text, non-finite floats as text).
fn jsonable(value: &PropertyValue) -> Value {
    let float = |v: f64| if v.is_finite() { json!(v) } else { json!(v.to_string()) };
    match value {
        PropertyValue::Void => Value::Null,
        PropertyValue::Boolean(v) => json!(v),
        PropertyValue::I8(v) => json!(v),
        PropertyValue::I16(v) => json!(v),
        PropertyValue::I32(v) => json!(v),
        PropertyValue::I64(v) => json!(v),
        PropertyValue::U8(v) => json!(v),
        PropertyValue::U16(v) => json!(v),
        PropertyValue::U32(v) => json!(v),
        PropertyValue::U64(v) => json!(v),
        PropertyValue::SingleFloat(v) => float(f64::from(*v)),
        PropertyValue::DoubleFloat(v) => float(*v),
        PropertyValue::String(v) => json!(v),
        PropertyValue::Timestamp(time) => {
            let (seconds, fractions) = time.to_parts();
            json!(format_micros(timestamp_micros(seconds, fractions)))
        }
        other => json!(format!("{other:?}")),
    }
}

fn properties_json(properties: &Properties) -> Value {
    Value::Object(properties.iter().map(|(k, v)| (k.clone(), jsonable(v))).collect::<Map<_, _>>())
}

// ── the file ────────────────────────────────────────────────────────────────

struct Tdms {
    file: TdmsFile<File>,
    layout: Layout,
    root: Properties,
}

impl Tdms {
    fn open(path: &str) -> Result<Self> {
        let layout = scan_layout(path)?;
        for (group, channels) in &layout.groups {
            if group.contains('\'') || channels.iter().any(|c| c.contains('\'')) {
                return invalid(format!("{path}: group or channel names with a quote are not supported"));
            }
        }
        let file = TdmsFile::load(Path::new(path)).map_err(tdms_error)?;
        let mut tdms = Self { file, layout, root: Properties::new() };
        tdms.root = tdms.properties(&PropertyPath::file());
        Ok(tdms)
    }

    fn properties(&self, path: &PropertyPath) -> Properties {
        self.file
            .read_all_properties(path)
            .map(|all| all.map(|(k, v)| (k.clone(), v.clone())).collect())
            .unwrap_or_default()
    }

    fn group_properties(&self, group: &str) -> Properties {
        self.properties(&PropertyPath::group(group))
    }

    fn channel_properties(&self, group: &str, channel: &str) -> Properties {
        self.properties(&PropertyPath::channel(group, channel))
    }

    fn length(&self, group: &str, channel: &str) -> usize {
        self.file.channel_length(&ChannelPath::new(group, channel)).unwrap_or(0) as usize
    }

    /// The channel's values as f64, with its NI scaling applied, like `tdmspy`'s `channel.read()`.
    fn read(&mut self, group: &str, channel: &str) -> Result<Vec<f64>> {
        let path = ChannelPath::new(group, channel);
        let length = self.length(group, channel);
        if length == 0 {
            return Ok(Vec::new());
        }
        // Ask for the first value as f64: a channel of another type says which one it is.
        let mut probe = [0f64];
        let stored = match self.file.read_channel::<f64>(&path, &mut probe) {
            Ok(()) => DataType::DoubleFloat,
            Err(TdmsError::DataTypeMismatch(stored, _)) => stored,
            Err(other) => return Err(tdms_error(other)),
        };
        macro_rules! read_as {
            ($t:ty) => {{
                let mut raw = vec![<$t>::default(); length];
                self.file.read_channel::<$t>(&path, &mut raw).map_err(tdms_error)?;
                raw.into_iter().map(|v| v as f64).collect::<Vec<f64>>()
            }};
        }
        let values = match stored {
            DataType::I8 => read_as!(i8),
            DataType::I16 => read_as!(i16),
            DataType::I32 => read_as!(i32),
            DataType::I64 => read_as!(i64),
            DataType::U8 => read_as!(u8),
            DataType::U16 => read_as!(u16),
            DataType::U32 => read_as!(u32),
            DataType::U64 => read_as!(u64),
            DataType::SingleFloat => read_as!(f32),
            DataType::DoubleFloat => read_as!(f64),
            other => return invalid(format!("channel {group}/{channel} has the unsupported data type {other:?}")),
        };
        let properties = self.channel_properties(group, channel);
        let group_properties = self.group_properties(group);
        scaled(values, &properties, &group_properties, &self.root)
    }
}

// ── NI scaling ──────────────────────────────────────────────────────────────

/// The number of NI scales a property set declares (`None` if none, or the data is already scaled).
fn scales_of(properties: &Properties) -> Option<usize> {
    let count = properties.get("NI_Number_Of_Scales").and_then(integer)?;
    if count <= 0 {
        return None;
    }
    let status = match properties.get("NI_Scaling_Status") {
        Some(PropertyValue::String(s)) => s.as_str(),
        _ => "unscaled",
    };
    if status == "scaled" {
        return None;
    }
    Some(count as usize)
}

fn scaled(
    raw: Vec<f64>,
    channel: &Properties,
    group: &Properties,
    file: &Properties,
) -> Result<Vec<f64>> {
    // The first of channel, group and file that declares scales applies, like tdmspy.
    let Some((properties, count)) = [channel, group, file].into_iter().find_map(|p| scales_of(p).map(|n| (p, n))) else {
        return Ok(raw);
    };
    let number = |key: String| -> Result<f64> {
        properties
            .get(&key)
            .and_then(numeric)
            .ok_or_else(|| Error::Invalid(format!("NI scaling property {key:?} is missing or not a number")))
    };
    let input_source = |scale: usize, kind: &str| -> i64 {
        properties.get(&format!("NI_Scale[{scale}]_{kind}_Input_Source")).and_then(integer).unwrap_or(RAW_DATA_INPUT_SOURCE)
    };

    #[allow(clippy::too_many_arguments)] // a recursive walk over the scales, which share their inputs
    fn compute(
        index: i64,
        raw: &[f64],
        count: usize,
        properties: &Properties,
        number: &dyn Fn(String) -> Result<f64>,
        input_source: &dyn Fn(usize, &str) -> i64,
        depth: usize,
    ) -> Result<Vec<f64>> {
        if index == RAW_DATA_INPUT_SOURCE {
            return Ok(raw.to_vec());
        }
        if index < 0 || index as usize >= count || depth > count {
            return invalid(format!("NI scale {index} is out of range or circular"));
        }
        let scale = index as usize;
        let kind = match properties.get(&format!("NI_Scale[{scale}]_Scale_Type")) {
            Some(PropertyValue::String(s)) => s.as_str(),
            _ => return invalid("NI scaling from DAQmx scalers is not supported"),
        };
        match kind {
            "Linear" => {
                let source = input_source(scale, "Linear");
                let input = compute(source, raw, count, properties, number, input_source, depth + 1)?;
                let slope = number(format!("NI_Scale[{scale}]_Linear_Slope"))?;
                let intercept = number(format!("NI_Scale[{scale}]_Linear_Y_Intercept"))?;
                Ok(input.into_iter().map(|v| v * slope + intercept).collect())
            }
            "Polynomial" => {
                let source = input_source(scale, "Polynomial");
                let input = compute(source, raw, count, properties, number, input_source, depth + 1)?;
                let size = properties
                    .get(&format!("NI_Scale[{scale}]_Polynomial_Coefficients_Size"))
                    .and_then(integer)
                    .unwrap_or(4)
                    .max(0) as usize;
                let coefficients = (0..size)
                    .map(|i| number(format!("NI_Scale[{scale}]_Polynomial_Coefficients[{i}]")))
                    .collect::<Result<Vec<f64>>>()?;
                Ok(input.into_iter().map(|x| coefficients.iter().rev().fold(0.0, |acc, c| acc * x + c)).collect())
            }
            other => invalid(format!("NI scale type {other:?} is not supported (only Linear and Polynomial)")),
        }
    }
    compute(count as i64 - 1, &raw, count, properties, &number, &input_source, 0)
}

// ── the legacy layout ───────────────────────────────────────────────────────

/// `100 - mean(quality)` is derived by `Source`; this keeps the values and their own rate. `None`
/// if the channel holds no usable data (nothing, or only non-finite values).
fn quality_of(tdms: &mut Tdms, group: &str) -> Option<g::QualityChannel> {
    let values = tdms.read(group, QUALITY_CHANNEL).ok()?;
    if !values.iter().any(|v| v.is_finite()) {
        return None;
    }
    let rate = tdms
        .channel_properties(group, QUALITY_CHANNEL)
        .get("wf_increment")
        .and_then(numeric)
        .filter(|increment| *increment > 0.0)
        .map(|increment| 1.0 / increment);
    Some(g::QualityChannel { values, sampling_frequency: rate })
}

fn mean_finite(quality: &g::QualityChannel) -> f64 {
    let finite: Vec<f64> = quality.values.iter().copied().filter(|v| v.is_finite()).collect();
    finite.iter().sum::<f64>() / finite.len() as f64
}

/// The worst (lowest mean) of the candidates; the first of equals.
fn worst(candidates: Vec<Option<g::QualityChannel>>) -> Option<g::QualityChannel> {
    let mut best: Option<g::QualityChannel> = None;
    for candidate in candidates.into_iter().flatten() {
        if best.as_ref().is_none_or(|b| mean_finite(&candidate) < mean_finite(b)) {
            best = Some(candidate);
        }
    }
    best
}

/// `(quality, the group it came from)` of a single-source file: the `system` group's, else the
/// worst of the other groups' (one per raw channel).
fn file_quality(tdms: &mut Tdms, raw_count: usize, warnings: &mut Vec<String>) -> (Option<g::QualityChannel>, Option<String>) {
    if tdms.layout.has_channel(SYSTEM_GROUP, QUALITY_CHANNEL) {
        return (quality_of(tdms, SYSTEM_GROUP), Some(SYSTEM_GROUP.to_string()));
    }
    let holders: Vec<String> = tdms
        .layout
        .groups
        .iter()
        .filter(|(name, channels)| name != RAW_GROUP && channels.iter().any(|c| c == QUALITY_CHANNEL))
        .map(|(name, _)| name.clone())
        .collect();
    if holders.is_empty() {
        return (None, None);
    }
    if holders.len() != raw_count {
        warnings.push(format!(
            "{} groups hold {QUALITY_CHANNEL} but {RAW_GROUP} has {raw_count} channel(s); signal loss is assumed 0",
            holders.len()
        ));
        return (None, None);
    }
    let candidates = holders.iter().map(|group| quality_of(tdms, group)).collect();
    (worst(candidates), None)
}

/// `{group: its rawdata channels}` (in file order) if the file holds several STUs, else `None`.
fn split_by_stu(tdms: &Tdms, channels: &[String]) -> Option<Vec<(String, Vec<String>)>> {
    if tdms.layout.has_channel(SYSTEM_GROUP, QUALITY_CHANNEL) {
        return None;
    }
    let holders: Vec<&String> = tdms
        .layout
        .groups
        .iter()
        .filter(|(name, chans)| name != RAW_GROUP && chans.iter().any(|c| c == QUALITY_CHANNEL))
        .map(|(name, _)| name)
        .collect();
    if holders.len() < 2 {
        return None;
    }
    let mut members: Vec<(String, Vec<String>)> = holders.iter().map(|h| ((*h).clone(), Vec::new())).collect();
    for channel in channels {
        let matches: Vec<usize> =
            members.iter().enumerate().filter(|(_, (name, _))| channel.starts_with(name.as_str())).map(|(i, _)| i).collect();
        // the longest match, the first of equally long ones (like Python's max())
        let mut best = *matches.first()?;
        for index in matches {
            if members[index].0.len() > members[best].0.len() {
                best = index;
            }
        }
        members[best].1.push(channel.clone());
    }
    if members.iter().any(|(_, chans)| chans.is_empty()) {
        return None;
    }
    Some(members)
}

struct Columns {
    fs: f64,
    columns: Vec<Vec<f64>>,
    rows: usize,
    start_time: Option<String>,
}

/// Reads the waveform channels of one source, which must agree on `wf_increment` and length.
fn read_channels(tdms: &mut Tdms, path: &str, place: &str, group: &str, channels: &[String]) -> Result<Columns> {
    if channels.len() > MAX_CHANNELS {
        return invalid(format!("{path}: {} channels in {place:?}, at most {MAX_CHANNELS} are supported", channels.len()));
    }
    let mut increments = Vec::new();
    let mut all = Vec::new();
    for channel in channels {
        let properties = tdms.channel_properties(group, channel);
        let increment = properties.get("wf_increment").and_then(numeric).filter(|v| *v > 0.0);
        match increment {
            Some(v) => increments.push(v),
            None => return invalid(format!("{path}: channel {channel:?} has no positive wf_increment")),
        }
        all.push(properties);
    }
    // numpy's allclose(increments, increments[0], rtol=1e-9) with its default atol of 1e-8
    if increments.iter().any(|v| (v - increments[0]).abs() > 1e-8 + 1e-9 * increments[0].abs()) {
        return invalid(format!("{path}: {place:?} channels have different wf_increment values {increments:?}"));
    }
    let fs = 1.0 / increments[0];

    let mut columns = Vec::new();
    for channel in channels {
        columns.push(tdms.read(group, channel)?);
    }
    let lengths: Vec<usize> = columns.iter().map(Vec::len).collect();
    if lengths.iter().any(|l| *l != lengths[0]) {
        return invalid(format!("{path}: {place:?} channels have different lengths {lengths:?}"));
    }
    let rows = lengths[0];
    if rows == 0 {
        return invalid(format!("{path}: the {place:?} channels hold no data"));
    }

    let start_time = match all[0].get("wf_start_time") {
        None => None,
        Some(value) => {
            let mut micros = timestamp_of(value)
                .ok_or_else(|| Error::Invalid(format!("{path}: wf_start_time of {:?} is not a timestamp", channels[0])))?;
            if let Some(offset) = all[0].get("wf_start_offset").and_then(numeric).filter(|o| *o != 0.0) {
                micros += (offset * 1e6).round_ties_even() as i64;
            }
            Some(format_micros(micros))
        }
    };
    Ok(Columns { fs, columns, rows, start_time })
}

#[allow(clippy::too_many_arguments)] // every piece of a source comes from a different place in the file
fn make_source(
    tdms: &Tdms,
    name: &str,
    stu_id: Option<&str>,
    group: &str,
    read: Columns,
    channels: &[String],
    quality: Option<g::QualityChannel>,
    additional_data: Value,
) -> g::Source {
    let metadata = |channel: &String| {
        let unit = match tdms.channel_properties(group, channel).get("unit_string") {
            Some(PropertyValue::String(s)) if !s.is_empty() => Some(s.clone()),
            _ => None,
        };
        g::ChannelMetadata {
            sensor: g::Sensor {
                sensor_id: None,
                sensor_type: None,
                name: Some(channel.clone()),
                unit,
                dimension: None,
                phys_min: None,
                phys_max: None,
                volt_min: None,
                volt_max: None,
            },
            compensations: vec![g::CompensationOrSubtype::NoConversion(g::NoConversion { order: 0 })],
        }
    };
    let mut columns = read.columns.into_iter();
    g::Source {
        name: name.to_string(),
        stu_id: stu_id.map(str::to_string),
        sth_id: None,
        sampling_frequency: Some(read.fs),
        quality,
        additional_data: Some(additional_data.to_string()),
        hardware_metadata: g::HardwareMetadata {
            revision: None,
            adc_reference_voltage: None,
            adc_prescaler: None,
            adc_acquisition_time: None,
            adc_oversample_rate: None,
            channel1_metadata: metadata(&channels[0]),
            channel2_metadata: channels.get(1).map(metadata),
            channel3_metadata: channels.get(2).map(metadata),
        },
        recording_metadata: g::RecordingMetadata { start_time: read.start_time, pre_metadata: None, post_metadata: None },
        recording_data: g::RecordingData {
            timestamp: (0..read.rows).map(|i| ((i as f64 * 1e6) / read.fs).round_ties_even() as isize).collect(),
            counter: None,
            channel1: columns.next().unwrap(),
            channel2: columns.next(),
            channel3: columns.next(),
        },
    }
}

/// A TDMS group name as a source name: one HDF5 path segment, unique.
fn source_name(group: &str, taken: &mut HashSet<String>) -> String {
    let cleaned = group.replace('/', "_");
    let cleaned = cleaned.trim_start_matches('.');
    let name = if cleaned.is_empty() { "stu" } else { cleaned };
    let mut unique = name.to_string();
    let mut n = 1;
    while taken.contains(&unique) {
        n += 1;
        unique = format!("{name}_{n}");
    }
    taken.insert(unique.clone());
    unique
}

/// The properties of the file, the source's group, its channels and the groups that hold no data
/// (e.g. `info`), as `Source.additional_data`.
fn additional_data(tdms: &Tdms, own_group: Option<&str>, group_of_channels: &str, channels: &[String], data_groups: &HashSet<String>) -> Value {
    let channel_properties: Map<String, Value> =
        channels.iter().map(|c| (c.clone(), properties_json(&tdms.channel_properties(group_of_channels, c)))).collect();
    let other_groups: Map<String, Value> = tdms
        .layout
        .groups
        .iter()
        .filter(|(name, _)| !data_groups.contains(name))
        .map(|(name, _)| (name.clone(), properties_json(&tdms.group_properties(name))))
        .collect();
    json!({
        "file": properties_json(&tdms.root),
        "group": own_group.map(|g| properties_json(&tdms.group_properties(g))),
        "channels": channel_properties,
        "other_groups": other_groups,
    })
}

fn load_stus(tdms: &mut Tdms, path: &str, members: Vec<(String, Vec<String>)>) -> Result<Vec<g::Source>> {
    let data_groups: HashSet<String> = std::iter::once(RAW_GROUP.to_string()).chain(members.iter().map(|(g, _)| g.clone())).collect();
    let mut taken = HashSet::new();
    let mut sources = Vec::new();
    for (group, channels) in members {
        let read = read_channels(tdms, path, &format!("{RAW_GROUP} ({group})"), RAW_GROUP, &channels)?;
        let quality = quality_of(tdms, &group);
        let extra = additional_data(tdms, Some(&group), RAW_GROUP, &channels, &data_groups);
        sources.push(make_source(tdms, &source_name(&group, &mut taken), Some(&group), RAW_GROUP, read, &channels, quality, extra));
    }
    Ok(sources)
}

fn load_legacy(tdms: &mut Tdms, path: &str, warnings: &mut Vec<String>) -> Result<Vec<g::Source>> {
    if !tdms.layout.has_group(RAW_GROUP) {
        let found: Vec<&String> = tdms.layout.groups.iter().map(|(n, _)| n).collect();
        return invalid(format!("{path}: no {RAW_GROUP:?} group (found {found:?})"));
    }
    let channels: Vec<String> = tdms.layout.channels(RAW_GROUP).to_vec();
    if channels.is_empty() {
        return invalid(format!("{path}: group {RAW_GROUP:?} has no channels"));
    }
    if let Some(members) = split_by_stu(tdms, &channels) {
        return load_stus(tdms, path, members);
    }
    let read = read_channels(tdms, path, RAW_GROUP, RAW_GROUP, &channels)?;
    let (quality, own_group) = file_quality(tdms, channels.len(), warnings);
    let mut data_groups: HashSet<String> = HashSet::from([RAW_GROUP.to_string()]);
    data_groups.extend(own_group.clone());
    let extra = additional_data(tdms, own_group.as_deref(), RAW_GROUP, &channels, &data_groups);
    Ok(vec![make_source(tdms, DEFAULT_SOURCE_NAME, None, RAW_GROUP, read, &channels, quality, extra)])
}

/// The sources in the TDMS file at `path`. Errors for a file without a usable `rawdata` group or
/// with an unknown format version.
///
/// A panic inside the `tedium` crate (it divides by zero on a segment that holds a channel without
/// values but with a data type, for one) is reported as an error.
pub fn load(path: &str) -> Result<Loaded> {
    std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| load_unguarded(path))).unwrap_or_else(|panic| {
        let reason = panic
            .downcast_ref::<String>()
            .map(String::as_str)
            .or_else(|| panic.downcast_ref::<&str>().copied())
            .unwrap_or("unknown reason");
        invalid(format!("{path}: the TDMS library failed on this file ({reason}); it may be damaged or use a layout it cannot read"))
    })
}

fn load_unguarded(path: &str) -> Result<Loaded> {
    let mut tdms = Tdms::open(path)?;
    if let Some(version) = tdms.root.get(FORMAT_VERSION_PROPERTY) {
        let version = match version {
            PropertyValue::String(s) => s.clone(),
            other => format!("{other:?}"),
        };
        return invalid(format!("Unsupported {FORMAT_VERSION_PROPERTY} {version:?} in {path:?}; supported versions: []"));
    }
    let mut warnings = Vec::new();
    let sources = load_legacy(&mut tdms, path, &mut warnings)?;
    Ok(Loaded { sources, version: LEGACY_VERSION.to_string(), warnings })
}
