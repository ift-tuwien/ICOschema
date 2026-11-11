//! What the Rust model and storage layers handle of the LinkML schema.
//!
//! The generated types change whenever `dataset.yaml` does. Most changes already break the build
//! (the storage code builds every generated struct field by field and matches the generated enums
//! exhaustively), but not all: a new enum value or a new subclass can compile fine and still be
//! silently unsupported. `tests/schema_coverage.rs` therefore compares the schema with this
//! manifest and fails, naming the new element, until somebody decides how it is handled:
//!
//! 1. handle it in `storage/hdf5.rs` / `model/`, then
//! 2. list it here (as `Support::Full`, or `Support::Unsupported` with the reason).

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Support {
    /// Read from the HDF5 file and available through the model.
    Full,
    /// Exists in the schema, but the file format cannot hold it. The writer refuses it with this
    /// reason (`storage/write.rs`); the reader never produces it.
    Unsupported(&'static str),
}

/// A class of the schema with *all* its attributes, inherited ones included.
pub struct ClassSupport {
    pub name: &'static str,
    pub attributes: &'static [&'static str],
    pub support: Support,
}

pub const NOT_IN_FILE_FORMAT: &str = "not representable in the HDF5 file format (format versions 1.0 to 1.4)";

pub const CLASSES: &[ClassSupport] = &[
    ClassSupport { name: "RecordingMetadata", attributes: &["start_time", "pre_metadata", "post_metadata"], support: Support::Full },
    ClassSupport {
        name: "HardwareMetadata",
        attributes: &[
            "revision",
            "adc_reference_voltage",
            "adc_prescaler",
            "adc_acquisition_time",
            "adc_oversample_rate",
            "channel1_metadata",
            "channel2_metadata",
            "channel3_metadata",
        ],
        support: Support::Full,
    },
    ClassSupport { name: "ChannelMetadata", attributes: &["sensor", "compensations"], support: Support::Full },
    ClassSupport {
        name: "Sensor",
        attributes: &["sensor_id", "sensor_type", "name", "unit", "dimension", "phys_min", "phys_max", "volt_min", "volt_max"],
        support: Support::Full,
    },
    ClassSupport { name: "Compensation", attributes: &["order"], support: Support::Full },
    ClassSupport { name: "Conversion", attributes: &["order"], support: Support::Full },
    ClassSupport { name: "NoConversion", attributes: &["order"], support: Support::Full },
    ClassSupport { name: "LinearConversion", attributes: &["order", "gain", "offset"], support: Support::Full },
    ClassSupport {
        name: "PolynomialConversion",
        attributes: &["order", "coefficients"],
        support: Support::Unsupported(NOT_IN_FILE_FORMAT),
    },
    ClassSupport { name: "FrequencyCompensation", attributes: &["order"], support: Support::Unsupported(NOT_IN_FILE_FORMAT) },
    ClassSupport {
        name: "RecordingData",
        attributes: &["timestamp", "counter", "channel1", "channel2", "channel3"],
        support: Support::Full,
    },
    ClassSupport {
        name: "QualityChannel",
        attributes: &["values", "sampling_frequency"],
        support: Support::Full,
    },
    ClassSupport {
        name: "Source",
        attributes: &[
            "name",
            "stu_id",
            "sth_id",
            "sampling_frequency",
            "quality",
            "additional_data",
            "hardware_metadata",
            "recording_metadata",
            "recording_data",
        ],
        support: Support::Full,
    },
    ClassSupport { name: "Recording", attributes: &["sources"], support: Support::Full },
    ClassSupport {
        name: "PreprocessedRecording",
        attributes: &[
            "timestamp",
            "channel1",
            "channel2",
            "channel3",
            "channel_sampling_frequency",
            "sampling_frequency_source",
            "fill_method",
            "producer",
            "source",
        ],
        support: Support::Full,
    },
    ClassSupport {
        name: "DerivedDataset",
        attributes: &["key", "values", "shape", "dtype", "unit", "produced_by", "produced_at", "params", "description"],
        support: Support::Full,
    },
    ClassSupport {
        name: "ComputationStep",
        attributes: &[
            "node",
            "step_index",
            "producer",
            "params",
            "resolved_params",
            "inputs",
            "status",
            "error",
            "summary",
            "output_keys",
            "started_at",
            "duration_s",
            "environment",
            "source_node",
        ],
        support: Support::Full,
    },
    ClassSupport {
        name: "Provenance",
        attributes: &["source_format", "source_format_version", "reader", "writer"],
        support: Support::Full,
    },
    ClassSupport {
        name: "DatasetBundle",
        attributes: &["recording", "provenance", "preprocessed_tables", "computations", "steps"],
        support: Support::Full,
    },
];

pub const ENUMS: &[(&str, &[&str])] = &[
    ("ComputationStatus", &["ok", "error"]),
    ("SamplingFrequencySource", &["override", "hardware", "default"]),
];
