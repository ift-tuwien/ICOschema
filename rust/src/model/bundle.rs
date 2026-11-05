use std::collections::HashMap;

use icoschema_gen as g;

use super::{PreprocessedRecording, Recording};
use crate::{storage, Result};

/// A recording, its optional preprocessed table, every derived dataset and the producing steps.
#[derive(Debug, Clone)]
pub struct DatasetBundle {
    pub recording: Recording,
    pub preprocessed: Option<PreprocessedRecording>,
    pub computations: HashMap<String, g::DerivedDataset>,
    /// Ordered by `step_index`.
    pub steps: Vec<g::ComputationStep>,
}

impl DatasetBundle {
    pub fn from_hdf5(path: &str) -> Result<Self> {
        let loaded = storage::hdf5::load_dataset_bundle(path)?;
        Ok(Self {
            recording: loaded.recording.into(),
            preprocessed: loaded.preprocessed.map(Into::into),
            computations: loaded.computations.unwrap_or_default(),
            steps: loaded.steps.unwrap_or_default(),
        })
    }

    pub fn computation(&self, key: &str) -> Option<&g::DerivedDataset> {
        self.computations.get(key)
    }
}
