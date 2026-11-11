//! Migration of schema version 1 data to schema version 2, and `read`, which opens a file of any schema
//! version as the latest one. Like `icoschema/migrate.py` and `icoschema/_read.py`.
//!
//! What changes (see `icoschema/v2/schema/dataset.yaml`):
//!
//! - `Source.stu_id`/`sth_id` become `stu_mac`/`sth_mac` (the same values); `Source.description` is unset.
//! - `Sensor.phys_min`/`phys_max`/`volt_min`/`volt_max` are dropped, and each channel gets a required
//!   `conversion` in place of the `compensations` list. Every channel of a v1 file becomes a
//!   `LinearConversion` (from ADC voltage to the sensor's unit), whatever its v1 conversion or the file's
//!   `conversion` attribute says: v1 files were never written with a usable one. Gain and offset are, in this
//!   order:
//!   1. the channel's `scaling_factor` and `offset` in the file's `sensors` table (`read` and `convert_file`
//!      take them from the file; a bundle no longer has them when the file said "already converted");
//!   2. the gain and offset of a v1 `LinearConversion` of the channel;
//!   3. the sensor's range: `gain = (phys_max - phys_min) / (volt_max - volt_min)` and
//!      `offset = phys_min - gain * volt_min`;
//!   4. `gain = 1`, `offset = 0` when none of that is there (e.g. a TDMS file).
//!
//!   A `PolynomialConversion` of degree 1 (`[offset, gain]`) counts as a `LinearConversion`; any other
//!   polynomial, a `FrequencyCompensation` and a channel with several compensations have no v2 form and
//!   are an error.

use std::collections::HashMap;
use std::io::{Read, Seek, SeekFrom};

use icoschema_gen_v1 as g1;
use icoschema_gen_v2 as g2;
use rust_hdf5::H5File;

use crate::{invalid, v1, v2, Error, Result};

const HDF5_SIGNATURE: [u8; 8] = [0x89, b'H', b'D', b'F', b'\r', b'\n', 0x1a, b'\n'];
const TDMS_SIGNATURE: [u8; 4] = *b"TDSm";
const FORMAT_VERSION_NAME: &str = "icoschema_format_version";
/// The newest schema version this crate has.
const LATEST: u32 = 2;

/// `(gain, offset)`.
pub type Scaling = (f64, f64);

// ── the file kinds ──────────────────────────────────────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Kind {
    Hdf5,
    Tdms,
}

/// HDF5 or TDMS, told by the file's first bytes (an HDF5 file may start with a user block, so its signature is
/// looked for where the format allows it: at byte 0, 512, 1024, 2048, ...).
fn kind_of(path: &str) -> Result<Kind> {
    let io = |e: std::io::Error| Error::Invalid(format!("{path}: {e}"));
    let mut file = std::fs::File::open(path).map_err(io)?;
    let length = file.metadata().map_err(io)?.len();
    let mut head = [0u8; 4];
    let read = file.read(&mut head).map_err(io)?;
    if read == 4 && head == TDMS_SIGNATURE {
        return Ok(Kind::Tdms);
    }
    let mut at = 0u64;
    while at + 8 <= length {
        let mut signature = [0u8; 8];
        file.seek(SeekFrom::Start(at)).map_err(io)?;
        file.read_exact(&mut signature).map_err(io)?;
        if signature == HDF5_SIGNATURE {
            return Ok(Kind::Hdf5);
        }
        at = if at == 0 { 512 } else { at * 2 };
    }
    invalid(format!("{path:?} is neither an HDF5 nor a TDMS file"))
}

/// The schema version (1, 2, ...) of the HDF5 or TDMS file at `path`, told by the file's first bytes and its
/// `icoschema_format_version`, without reading the data. A file without a version is of schema version 1, and so
/// is every TDMS file (no TDMS layout is versioned yet). An error for another kind of file or a schema version
/// this crate does not have.
pub fn schema_version_of_file(path: &str) -> Result<u32> {
    let version = match kind_of(path)? {
        Kind::Tdms => 1,
        Kind::Hdf5 => {
            let file = H5File::open(path)?;
            let present = file.attr_names().unwrap_or_default().iter().any(|n| n == FORMAT_VERSION_NAME);
            if present {
                let text = file.attr(FORMAT_VERSION_NAME)?.read_string()?;
                let major = text.split('.').next().unwrap_or("");
                match (major, text.as_str()) {
                    (_, "legacy") => 1,
                    (m, _) if !m.is_empty() && m.chars().all(|c| c.is_ascii_digit()) => m.parse().unwrap_or(0),
                    _ => return invalid(format!("not an icoschema format version: {text:?}")),
                }
            } else {
                1
            }
        }
    };
    if !(1..=LATEST).contains(&version) {
        return invalid(format!("unsupported schema version {version} in {path:?}; supported: 1 to {LATEST}"));
    }
    Ok(version)
}

/// The `DatasetBundle` of the HDF5 or TDMS file at `path`, whatever schema version it was written with, as the
/// latest schema version's (`icoschema::DatasetBundle`). A file of schema version 1 is migrated (see the module
/// documentation), so its conversions follow those rules, not the original ones. To keep a file's own version,
/// use `schema_version_of_file` and that version's module (`icoschema::v1`).
pub fn read(path: &str) -> Result<v2::DatasetBundle> {
    match schema_version_of_file(path)? {
        2 => v2::DatasetBundle::from_file(path),
        _ => {
            let (bundle, warnings) = file_as_v2(path)?;
            for warning in warnings {
                eprintln!("warning: {path}: {warning}");
            }
            Ok(bundle)
        }
    }
}

/// Reads the file of schema version 1 at `path` and writes it to `destination` as a schema version 2 HDF5 file
/// (format 2.0).
pub fn convert_file(path: &str, destination: &str) -> Result<()> {
    let (bundle, warnings) = file_as_v2(path)?;
    for warning in warnings {
        eprintln!("warning: {path}: {warning}");
    }
    bundle.to_hdf5(destination)
}

/// A v1 file as a v2 bundle (with its stored scalings), and the warnings of the migration.
fn file_as_v2(path: &str) -> Result<(v2::DatasetBundle, Vec<String>)> {
    let bundle = v1::DatasetBundle::from_file(path)?;
    let stored = match kind_of(path)? {
        Kind::Hdf5 => {
            let single = bundle.recording.only_source().map(|s| s.name().to_string()).unwrap_or_default();
            v1::storage::hdf5::stored_scalings(path, &single)?
        }
        Kind::Tdms => HashMap::new(),
    };
    v1_to_v2_with_warnings(&bundle, &stored)
}

// ── the rules ───────────────────────────────────────────────────────────────

fn has_range(sensor: &g1::Sensor) -> bool {
    matches!((sensor.phys_min, sensor.phys_max, sensor.volt_min, sensor.volt_max),
        (Some(_), Some(_), Some(lo), Some(hi)) if lo != hi)
}

/// The conversion from ADC voltage to the sensor's unit that the range of a v1 `sensor` describes:
/// `gain = delta_phys / delta_volt`, `offset = phys_min - gain * volt_min`. An error without a complete range
/// or with `volt_max == volt_min`.
pub fn linear_from_range(sensor: &g1::Sensor) -> Result<Scaling> {
    let name = sensor.sensor_id.as_deref().unwrap_or("");
    let (Some(phys_min), Some(phys_max), Some(volt_min), Some(volt_max)) =
        (sensor.phys_min, sensor.phys_max, sensor.volt_min, sensor.volt_max)
    else {
        return invalid(format!("sensor {name:?} has no complete phys/volt range to derive a conversion from"));
    };
    if volt_max == volt_min {
        return invalid(format!("sensor {name:?}: volt_min == volt_max ({volt_min}), no gain can be derived"));
    }
    let gain = (phys_max - phys_min) / (volt_max - volt_min);
    Ok((gain, phys_min - gain * volt_min))
}

fn close(a: Scaling, b: Scaling) -> bool {
    let near = |x: f64, y: f64, abs: f64| (x - y).abs() <= abs.max(1e-4 * x.abs().max(y.abs()));
    near(a.0, b.0, 1e-9) && near(a.1, b.1, 1e-3 * b.0.abs().max(1.0))
}

fn order_of(c: &g1::CompensationOrSubtype) -> isize {
    match c {
        g1::CompensationOrSubtype::Conversion(c) => c.order,
        g1::CompensationOrSubtype::FrequencyCompensation(c) => c.order,
        g1::CompensationOrSubtype::NoConversion(c) => c.order,
        g1::CompensationOrSubtype::LinearConversion(c) => c.order,
        g1::CompensationOrSubtype::PolynomialConversion(c) => c.order,
    }
}

/// The v2 conversion of a v1 channel (always a `LinearConversion`), given the scaling stored for it in its file.
fn migrate_conversion(
    metadata: &g1::ChannelMetadata,
    stored: Option<Scaling>,
    warnings: &mut Vec<String>,
) -> Result<g2::LinearConversion> {
    let sensor = &metadata.sensor;
    let name = sensor.sensor_id.as_deref().unwrap_or("");
    let mut compensations: Vec<&g1::CompensationOrSubtype> = metadata.compensations.iter().collect();
    compensations.sort_by_key(|c| order_of(c));
    if compensations.len() > 1 {
        return invalid(format!(
            "sensor {name:?}: {} compensations cannot be migrated, v2 has one conversion per channel",
            compensations.len()
        ));
    }
    let linear: Option<Scaling> = match compensations.first() {
        None | Some(g1::CompensationOrSubtype::NoConversion(_)) => None,
        Some(g1::CompensationOrSubtype::LinearConversion(l)) => Some((l.gain, l.offset)),
        Some(g1::CompensationOrSubtype::PolynomialConversion(p)) if p.coefficients.len() == 2 => {
            Some((p.coefficients[1], p.coefficients[0]))
        }
        Some(g1::CompensationOrSubtype::PolynomialConversion(p)) => {
            return invalid(format!(
                "sensor {name:?}: a polynomial of degree {} has no v2 form and cannot be migrated",
                p.coefficients.len().saturating_sub(1)
            ))
        }
        Some(g1::CompensationOrSubtype::FrequencyCompensation(_)) => {
            return invalid(format!("sensor {name:?}: a FrequencyCompensation has no v2 form and cannot be migrated"))
        }
        Some(g1::CompensationOrSubtype::Conversion(_)) => {
            return invalid(format!("sensor {name:?}: an abstract Conversion has no v2 form and cannot be migrated"))
        }
    };

    let (gain, offset) = match (stored, linear) {
        (Some(scaling), _) | (None, Some(scaling)) => {
            if has_range(sensor) && !close(scaling, linear_from_range(sensor)?) {
                warnings.push(format!(
                    "sensor {name:?}: the stored conversion (gain={}, offset={}) differs from the one its phys/volt \
                     range gives; keeping the stored one",
                    scaling.0, scaling.1
                ));
            }
            scaling
        }
        (None, None) if has_range(sensor) => linear_from_range(sensor)?,
        (None, None) => (1.0, 0.0),
    };
    Ok(g2::LinearConversion { gain, offset, conversion_type: None })
}

fn migrate_channel(
    metadata: &g1::ChannelMetadata,
    stored: Option<Scaling>,
    warnings: &mut Vec<String>,
) -> Result<g2::ChannelMetadata> {
    let g1::Sensor { sensor_id, sensor_type, name, unit, dimension, phys_min: _, phys_max: _, volt_min: _, volt_max: _ } =
        &metadata.sensor;
    Ok(g2::ChannelMetadata {
        sensor: g2::Sensor {
            sensor_id: sensor_id.clone(),
            sensor_type: sensor_type.clone(),
            name: name.clone(),
            unit: unit.clone(),
            dimension: dimension.clone(),
        },
        conversion: g2::ConversionOrSubtype::LinearConversion(migrate_conversion(metadata, stored, warnings)?),
    })
}

fn migrate_source(
    source: &g1::Source,
    stored: &HashMap<String, Vec<Scaling>>,
    warnings: &mut Vec<String>,
) -> Result<g2::Source> {
    let g1::Source {
        name,
        stu_id,
        sth_id,
        sampling_frequency,
        quality,
        additional_data,
        hardware_metadata,
        recording_metadata,
        recording_data,
    } = source;
    let scalings = stored.get(name);
    let scaling = |i: usize| scalings.and_then(|s| s.get(i)).copied();
    let g1::HardwareMetadata {
        revision,
        adc_reference_voltage,
        adc_prescaler,
        adc_acquisition_time,
        adc_oversample_rate,
        channel1_metadata,
        channel2_metadata,
        channel3_metadata,
    } = hardware_metadata;
    let g1::RecordingMetadata { start_time, pre_metadata, post_metadata } = recording_metadata;
    let g1::RecordingData { timestamp, counter, channel1, channel2, channel3 } = recording_data;
    Ok(g2::Source {
        name: name.clone(),
        description: None,
        stu_mac: stu_id.clone(),
        sth_mac: sth_id.clone(),
        sampling_frequency: *sampling_frequency,
        quality: quality.as_ref().map(|q| g2::QualityChannel {
            values: q.values.clone(),
            sampling_frequency: q.sampling_frequency,
        }),
        additional_data: additional_data.clone(),
        hardware_metadata: g2::HardwareMetadata {
            revision: revision.clone(),
            adc_reference_voltage: adc_reference_voltage.clone(),
            adc_prescaler: *adc_prescaler,
            adc_acquisition_time: *adc_acquisition_time,
            adc_oversample_rate: *adc_oversample_rate,
            channel1_metadata: migrate_channel(channel1_metadata, scaling(0), warnings)?,
            channel2_metadata: channel2_metadata
                .as_ref()
                .map(|m| migrate_channel(m, scaling(1), warnings))
                .transpose()?,
            channel3_metadata: channel3_metadata
                .as_ref()
                .map(|m| migrate_channel(m, scaling(2), warnings))
                .transpose()?,
        },
        recording_metadata: g2::RecordingMetadata {
            start_time: start_time.clone(),
            pre_metadata: pre_metadata.clone(),
            post_metadata: post_metadata.clone(),
        },
        recording_data: g2::RecordingData {
            timestamp: timestamp.clone(),
            counter: counter.clone(),
            channel1: channel1.clone(),
            channel2: channel2.clone(),
            channel3: channel3.clone(),
        },
    })
}

fn migrate_preprocessed(p: &g1::PreprocessedRecording) -> g2::PreprocessedRecording {
    let g1::PreprocessedRecording {
        timestamp,
        channel1,
        channel2,
        channel3,
        channel_sampling_frequency,
        sampling_frequency_source,
        fill_method,
        producer,
        source,
    } = p;
    g2::PreprocessedRecording {
        timestamp: timestamp.clone(),
        channel1: channel1.clone(),
        channel2: channel2.clone(),
        channel3: channel3.clone(),
        channel_sampling_frequency: *channel_sampling_frequency,
        sampling_frequency_source: match sampling_frequency_source {
            g1::SamplingFrequencySource::Override => g2::SamplingFrequencySource::Override,
            g1::SamplingFrequencySource::Hardware => g2::SamplingFrequencySource::Hardware,
            g1::SamplingFrequencySource::Default => g2::SamplingFrequencySource::Default,
        },
        fill_method: fill_method.clone(),
        producer: producer.clone(),
        source: source.clone(),
    }
}

fn migrate_derived(d: &g1::DerivedDataset) -> g2::DerivedDataset {
    let g1::DerivedDataset { key, values, shape, dtype, unit, produced_by, produced_at, params, description } = d;
    g2::DerivedDataset {
        key: key.clone(),
        values: values.clone(),
        shape: shape.clone(),
        dtype: dtype.clone(),
        unit: unit.clone(),
        produced_by: produced_by.clone(),
        produced_at: produced_at.clone(),
        params: params.clone(),
        description: description.clone(),
    }
}

fn migrate_step(s: &g1::ComputationStep) -> g2::ComputationStep {
    let g1::ComputationStep {
        node,
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
    } = s;
    g2::ComputationStep {
        node: node.clone(),
        step_index: *step_index,
        producer: producer.clone(),
        params: params.clone(),
        resolved_params: resolved_params.clone(),
        inputs: inputs.clone(),
        status: status.as_ref().map(|s| match s {
            g1::ComputationStatus::Ok => g2::ComputationStatus::Ok,
            g1::ComputationStatus::Error => g2::ComputationStatus::Error,
        }),
        error: error.clone(),
        summary: summary.clone(),
        output_keys: output_keys.clone(),
        started_at: started_at.clone(),
        duration_s: *duration_s,
        environment: environment.clone(),
        source_node: source_node.clone(),
    }
}

/// `bundle` of schema version 1 as a schema version 2 `DatasetBundle`; see the module documentation for the
/// rules. The warnings of the migration go to standard error; `v1_to_v2_with_warnings` returns them.
/// `stored_scalings` are the `(gain, offset)` of each channel of each source (by source name) as stored in the
/// file the bundle was read from; pass an empty map for a bundle built in memory.
pub fn v1_to_v2(bundle: &v1::DatasetBundle, stored_scalings: &HashMap<String, Vec<Scaling>>) -> Result<v2::DatasetBundle> {
    let (migrated, warnings) = v1_to_v2_with_warnings(bundle, stored_scalings)?;
    for warning in warnings {
        eprintln!("warning: {warning}");
    }
    Ok(migrated)
}

/// `v1_to_v2`, returning the warnings instead of printing them.
pub fn v1_to_v2_with_warnings(
    bundle: &v1::DatasetBundle,
    stored_scalings: &HashMap<String, Vec<Scaling>>,
) -> Result<(v2::DatasetBundle, Vec<String>)> {
    let mut warnings = Vec::new();
    let sources = bundle
        .recording
        .sources()
        .iter()
        .map(|s| migrate_source(s, stored_scalings, &mut warnings).map(v2::Source::from))
        .collect::<Result<Vec<_>>>()?;
    let mut migrated = v2::DatasetBundle::new(v2::Recording::new(sources)?);
    migrated.computations = bundle.computations.iter().map(|(k, d)| (k.clone(), migrate_derived(d))).collect();
    migrated.steps = bundle.steps.iter().map(migrate_step).collect();
    migrated.provenance = bundle.provenance.as_ref().map(|p| {
        let g1::Provenance { source_format, source_format_version, reader, writer } = p;
        g2::Provenance {
            source_format: source_format.clone(),
            source_format_version: source_format_version.clone(),
            reader: reader.clone(),
            writer: writer.clone(),
        }
    });
    for table in &bundle.preprocessed_tables {
        migrated = migrated.with_preprocessed(migrate_preprocessed(table), None)?;
    }
    Ok((migrated, warnings))
}
