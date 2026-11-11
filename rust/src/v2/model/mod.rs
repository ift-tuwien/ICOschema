//! The public API: wrappers around the generated schema types that add storage and convenience
//! methods (like `icoschema/v2/model`). `Source` and `PreprocessedRecording` deref to their
//! generated types, so all schema fields stay reachable (`source.hardware_metadata`, ...).
mod bundle;
mod datetime;
mod preprocessed;
mod recording;
mod source;

pub use datetime::{Components, DateTime};
pub use bundle::{validate_preprocessed, validate_steps, DatasetBundle, PREPROCESSED_NODE, PREPROCESSED_PREFIX};
pub use preprocessed::PreprocessedRecording;
pub use recording::Recording;
pub use source::{
    format_micros, ChannelSummary, FrequencySource, Source, Summary, ADC_CLOCK_HZ, DEFAULT_ADC_SETTINGS, LEGACY_TDMS_KEY,
};
