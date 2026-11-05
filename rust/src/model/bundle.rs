use std::collections::{HashMap, HashSet};

use icoschema_gen as g;

use super::{PreprocessedRecording, Recording};
use crate::storage::write::{self, Parts};
use crate::{invalid, storage, Result};

/// A recording, its optional preprocessed table, every derived dataset and the producing steps.
///
/// Like in the Python package the `with_*` / `without_*` methods return the changed bundle and
/// check what they add: a preprocessed table must fit the recording, steps are numbered in order
/// and only list computations that exist. `to_hdf5` checks again, so a bundle built by filling
/// the public fields directly cannot write an inconsistent file either.
#[derive(Debug, Clone)]
pub struct DatasetBundle {
    pub recording: Recording,
    pub preprocessed: Option<PreprocessedRecording>,
    pub computations: HashMap<String, g::DerivedDataset>,
    /// Ordered by `step_index`.
    pub steps: Vec<g::ComputationStep>,
}

impl DatasetBundle {
    pub fn new(recording: Recording) -> Self {
        Self { recording, preprocessed: None, computations: HashMap::new(), steps: Vec::new() }
    }

    pub fn from_hdf5(path: &str) -> Result<Self> {
        let loaded = storage::hdf5::load_dataset_bundle(path)?;
        let mut bundle = Self::new(loaded.recording.into());
        bundle.computations = loaded.computations.unwrap_or_default();
        bundle.steps = loaded.steps.unwrap_or_default();
        match loaded.preprocessed {
            // A preprocessed table that does not fit the recording is primary data: never skipped.
            Some(p) => bundle.with_preprocessed(p),
            None => Ok(bundle),
        }
    }

    /// Writes the bundle to a fresh HDF5 file (see `storage::write` for the layout).
    pub fn to_hdf5(&self, path: &str) -> Result<()> {
        if let Some(p) = &self.preprocessed {
            validate_preprocessed(&self.recording, p)?;
        }
        validate_steps(&self.steps, &self.computations)?;
        write::save(
            Parts {
                recording: &self.recording,
                preprocessed: self.preprocessed.as_deref(),
                computations: &self.computations,
                steps: &self.steps,
            },
            path,
        )
    }

    pub fn computation(&self, key: &str) -> Option<&g::DerivedDataset> {
        self.computations.get(key)
    }

    /// Replaces the recording. Refused while there is a preprocessed table or there are steps:
    /// they were built from the current recording and would silently go stale.
    pub fn with_recording(mut self, recording: Recording) -> Result<Self> {
        if self.preprocessed.is_some() {
            return invalid(
                "cannot replace the recording of a bundle with a preprocessed table \
                 (it was built from the current recording): call without_preprocessed() first",
            );
        }
        if !self.steps.is_empty() {
            return invalid(
                "cannot replace the recording of a bundle with computation steps \
                 (they were computed from the current recording): call without_steps() first",
            );
        }
        self.recording = recording;
        Ok(self)
    }

    /// Sets (adds or replaces) the preprocessed table; it must fit the recording.
    pub fn with_preprocessed(mut self, preprocessed: g::PreprocessedRecording) -> Result<Self> {
        let preprocessed = PreprocessedRecording::from(preprocessed);
        validate_preprocessed(&self.recording, &preprocessed)?;
        self.preprocessed = Some(preprocessed);
        Ok(self)
    }

    /// Drops the preprocessed table (steps and computations are kept).
    pub fn without_preprocessed(mut self) -> Self {
        self.preprocessed = None;
        self
    }

    /// Adds or replaces one computation under `key`.
    pub fn with_computation(mut self, key: impl Into<String>, derived: g::DerivedDataset) -> Self {
        self.computations.insert(key.into(), derived);
        self
    }

    /// Appends `step` as the last step. Its `step_index` is assigned here. The node name must be
    /// unused and a single HDF5 path segment, and every `output_keys` entry must already be in
    /// `computations`: add the step's computations first.
    pub fn with_step(mut self, mut step: g::ComputationStep) -> Result<Self> {
        step.step_index = self.steps.len() as isize;
        self.steps.push(step);
        match validate_steps(&self.steps, &self.computations) {
            Ok(()) => Ok(self),
            Err(e) => {
                self.steps.pop();
                Err(e)
            }
        }
    }

    /// Removes the steps named `nodes` and the computations they list in `output_keys`. The
    /// remaining steps are renumbered 0, 1, 2, ... Nothing else is dropped.
    pub fn without_steps<'a>(mut self, nodes: impl IntoIterator<Item = &'a str>) -> Result<Self> {
        let nodes: HashSet<&str> = nodes.into_iter().collect();
        let known: HashSet<&str> = self.steps.iter().map(|s| s.node.as_str()).collect();
        let mut unknown: Vec<&str> = nodes.difference(&known).copied().collect();
        if !unknown.is_empty() {
            unknown.sort();
            return invalid(format!("no such step(s): {unknown:?}"));
        }
        let removed: HashSet<String> = self
            .steps
            .iter()
            .filter(|s| nodes.contains(s.node.as_str()))
            .flat_map(|s| s.output_keys.clone().unwrap_or_default())
            .collect();
        self.steps.retain(|s| !nodes.contains(s.node.as_str()));
        for (i, step) in self.steps.iter_mut().enumerate() {
            step.step_index = i as isize;
        }
        self.computations.retain(|k, _| !removed.contains(k));
        Ok(self)
    }

    /// The computations step `node` wrote (its `output_keys`), by key.
    pub fn computations_of(&self, node: &str) -> Result<HashMap<&str, &g::DerivedDataset>> {
        let Some(step) = self.steps.iter().find(|s| s.node == node) else {
            return invalid(format!("no such step: {node:?}"));
        };
        step.output_keys
            .iter()
            .flatten()
            .map(|key| match self.computations.get(key) {
                Some(d) => Ok((key.as_str(), d)),
                None => invalid(format!("step {node:?} lists output key {key:?} that is not in computations")),
            })
            .collect()
    }

    /// Computation keys no step lists in its `output_keys` (older files, or code that adds
    /// computations without recording a step).
    pub fn unmanaged_keys(&self) -> HashSet<&str> {
        let managed: HashSet<&str> =
            self.steps.iter().flat_map(|s| s.output_keys.iter().flatten().map(String::as_str)).collect();
        self.computations.keys().map(String::as_str).filter(|k| !managed.contains(k)).collect()
    }
}

/// `preprocessed` must fit `recording`: one row per gap-free grid position, the same channels,
/// columns of equal length and a positive finite sampling frequency.
pub fn validate_preprocessed(recording: &Recording, preprocessed: &g::PreprocessedRecording) -> Result<()> {
    let grid_length = *recording.sample_index()?.last().unwrap() as usize + 1;
    let channels = |a: &[f64], b: &[f64], c: &[f64]| -> Vec<&'static str> {
        [("channel1", a), ("channel2", b), ("channel3", c)]
            .into_iter()
            .filter(|(_, v)| !v.is_empty())
            .map(|(n, _)| n)
            .collect()
    };
    let raw = channels(recording.channel1(), recording.channel2(), recording.channel3());
    let pre = channels(
        &preprocessed.channel1,
        preprocessed.channel2.as_deref().unwrap_or(&[]),
        preprocessed.channel3.as_deref().unwrap_or(&[]),
    );
    if pre != raw {
        return invalid(format!("preprocessed table has channels {pre:?}, but the recording has {raw:?}"));
    }
    let lengths = [
        ("timestamp", preprocessed.timestamp.len()),
        ("channel1", preprocessed.channel1.len()),
        ("channel2", preprocessed.channel2.as_deref().map_or(0, <[f64]>::len)),
        ("channel3", preprocessed.channel3.as_deref().map_or(0, <[f64]>::len)),
    ];
    for (column, length) in lengths {
        if (column == "timestamp" || raw.contains(&column)) && length != grid_length {
            return invalid(format!(
                "preprocessed {column} has {length} rows, but the recording's gap-free grid has {grid_length}"
            ));
        }
    }
    let frequency = preprocessed.channel_sampling_frequency;
    if !(frequency.is_finite() && frequency > 0.0) {
        return invalid(format!("preprocessed channel_sampling_frequency must be positive and finite, got {frequency}"));
    }
    Ok(())
}

/// `steps` must be numbered 0, 1, 2, ... in order, with unique node names that are single HDF5
/// path segments, and every `output_keys` entry must be in `computations`.
pub fn validate_steps(steps: &[g::ComputationStep], computations: &HashMap<String, g::DerivedDataset>) -> Result<()> {
    let mut seen = HashSet::new();
    for (position, step) in steps.iter().enumerate() {
        let node = &step.node;
        if node.is_empty() || node.contains('/') || node.starts_with('.') {
            return invalid(format!("step name {node:?} must be non-empty, contain no '/' and not start with '.'"));
        }
        if !seen.insert(node.as_str()) {
            return invalid(format!("duplicate step name {node:?}"));
        }
        if step.step_index != position as isize {
            return invalid(format!("step {node:?} has step_index {}, expected {position}", step.step_index));
        }
        let missing: Vec<&String> =
            step.output_keys.iter().flatten().filter(|k| !computations.contains_key(*k)).collect();
        if !missing.is_empty() {
            return invalid(format!("step {node:?} lists output_keys missing from computations: {missing:?}"));
        }
    }
    Ok(())
}
