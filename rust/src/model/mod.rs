//! The public API: wrappers around the generated schema types that add storage and convenience
//! methods (like `icoschema/model/python`). Each wrapper derefs to its generated type, so all
//! schema fields stay reachable (`recording.hardware_metadata`, ...).
mod bundle;
mod preprocessed;
mod recording;

pub use bundle::DatasetBundle;
pub use preprocessed::PreprocessedRecording;
pub use recording::{FrequencySource, Recording, Summary, ChannelSummary};
