use std::collections::{HashMap, HashSet};
use std::io::{Read, Seek, SeekFrom};

use icoschema_gen as g;

use super::{PreprocessedRecording, Recording, Source};
use crate::storage::write::{self, Parts};
use crate::{invalid, storage, Result};

/// `source_node` for the preprocessed table of a single-source recording.
pub const PREPROCESSED_NODE: &str = "preprocessed";
/// `source_node` prefix for the preprocessed table of a named source.
pub const PREPROCESSED_PREFIX: &str = "preprocessed:";

const HDF5_SIGNATURE: [u8; 8] = [0x89, b'H', b'D', b'F', b'\r', b'\n', 0x1a, b'\n'];
const TDMS_SIGNATURE: [u8; 4] = *b"TDSm";

/// A recording, its optional preprocessed tables (at most one per source), every derived dataset
/// and the producing steps.
///
/// Like in the Python package the `with_*` / `without_*` methods return the changed bundle and
/// check what they add: a preprocessed table must fit its source, steps are numbered in order
/// and only list computations that exist. `to_hdf5` checks again, so a bundle built by filling
/// the public fields directly cannot write an inconsistent file either.
#[derive(Debug, Clone)]
pub struct DatasetBundle {
    pub recording: Recording,
    /// At most one per source, each with its `source` set, in source order.
    pub preprocessed_tables: Vec<PreprocessedRecording>,
    pub computations: HashMap<String, g::DerivedDataset>,
    /// Ordered by `step_index`.
    pub steps: Vec<g::ComputationStep>,
    /// Where the data was read from and by what the file was written; `None` for a bundle built
    /// in memory.
    pub provenance: Option<g::Provenance>,
}

impl DatasetBundle {
    pub fn new(recording: Recording) -> Self {
        Self {
            recording,
            preprocessed_tables: Vec::new(),
            computations: HashMap::new(),
            steps: Vec::new(),
            provenance: None,
        }
    }

    pub fn from_hdf5(path: &str) -> Result<Self> {
        let loaded = storage::hdf5::load_dataset_bundle(path)?;
        let mut bundle = Self::new(Recording::new(loaded.sources.into_iter().map(Source::from).collect())?);
        bundle.computations = loaded.computations;
        bundle.steps = loaded.steps;
        bundle.provenance = Some(loaded.provenance);
        for table in loaded.preprocessed {
            // A preprocessed table that does not fit its source is primary data: never skipped.
            bundle = bundle.with_preprocessed(table, None)?;
        }
        Ok(bundle)
    }

    /// Loads a TDMS file (read-only; needs the `tdms` feature, on by default). The bundle holds
    /// just the recording: save results with `to_hdf5`. Warnings about the file (Python raises
    /// them as `UserWarning`) go to standard error; `from_tdms_with_warnings` returns them.
    pub fn from_tdms(path: &str) -> Result<Self> {
        let (bundle, warnings) = Self::from_tdms_with_warnings(path)?;
        for warning in warnings {
            eprintln!("warning: {path}: {warning}");
        }
        Ok(bundle)
    }

    /// `from_tdms`, returning the warnings instead of printing them.
    #[cfg(feature = "tdms")]
    pub fn from_tdms_with_warnings(path: &str) -> Result<(Self, Vec<String>)> {
        let loaded = storage::tdms::load(path)?;
        let mut bundle = Self::new(Recording::new(loaded.sources.into_iter().map(Source::from).collect())?);
        bundle.provenance = Some(g::Provenance {
            source_format: Some("tdms".into()),
            source_format_version: Some(loaded.version),
            reader: Some(storage::software_id()),
            writer: None,
        });
        Ok((bundle, loaded.warnings))
    }

    #[cfg(not(feature = "tdms"))]
    pub fn from_tdms_with_warnings(_path: &str) -> Result<(Self, Vec<String>)> {
        invalid("this build of icoschema has no TDMS reader (the `tdms` feature is off)")
    }

    /// Loads an HDF5 or TDMS file, told apart by the file's first bytes (not its name). An HDF5
    /// file may start with a user block, so its signature is looked for where the format allows
    /// it: at byte 0, 512, 1024, 2048, ...
    pub fn from_file(path: &str) -> Result<Self> {
        let io = |e: std::io::Error| crate::Error::Invalid(format!("{path}: {e}"));
        let mut file = std::fs::File::open(path).map_err(io)?;
        let length = file.metadata().map_err(io)?.len();
        let mut head = [0u8; 4];
        let read = file.read(&mut head).map_err(io)?;
        if read == 4 && head == TDMS_SIGNATURE {
            return Self::from_tdms(path);
        }
        let mut at = 0u64;
        while at + 8 <= length {
            let mut signature = [0u8; 8];
            file.seek(SeekFrom::Start(at)).map_err(io)?;
            file.read_exact(&mut signature).map_err(io)?;
            if signature == HDF5_SIGNATURE {
                return Self::from_hdf5(path);
            }
            at = if at == 0 { 512 } else { at * 2 };
        }
        invalid(format!("{path:?} is neither an HDF5 nor a TDMS file"))
    }

    /// Writes the bundle to a fresh HDF5 file (see `storage::write` for the layout).
    pub fn to_hdf5(&self, path: &str) -> Result<()> {
        for table in &self.preprocessed_tables {
            let name = table.source.as_deref().unwrap_or_default();
            match self.recording.source(name) {
                Some(source) => validate_preprocessed(source, table)?,
                None => return invalid(format!("preprocessed table for unknown source {name:?}")),
            }
        }
        validate_steps(&self.steps, &self.computations, Some(&self.recording))?;
        write::save(
            Parts {
                sources: self.recording.sources().iter().map(|s| &**s).collect(),
                preprocessed: self
                    .preprocessed_tables
                    .iter()
                    .map(|t| (t.source.as_deref().unwrap_or_default(), &**t))
                    .collect(),
                computations: &self.computations,
                steps: &self.steps,
                provenance: self.provenance.as_ref(),
            },
            path,
        )
    }

    // ── preprocessed ───────────────────────────────────────────────────────

    /// The preprocessed table of the only source, `None` if it has none. Raises if the recording
    /// has several sources: use `preprocessed_for`.
    pub fn preprocessed(&self) -> Result<Option<&PreprocessedRecording>> {
        let names = self.recording.source_names();
        match names.as_slice() {
            [only] => self.preprocessed_for(only),
            _ => invalid(format!("recording has {} sources ({names:?}); use preprocessed_for(source)", names.len())),
        }
    }

    /// The preprocessed table of `source`, `None` if it has none. Raises for an unknown source.
    pub fn preprocessed_for(&self, source: &str) -> Result<Option<&PreprocessedRecording>> {
        if self.recording.source(source).is_none() {
            return invalid(format!("no such source: {source:?}"));
        }
        Ok(self.preprocessed_tables.iter().find(|t| t.source.as_deref() == Some(source)))
    }

    /// Replaces the recording. Refused while there is a preprocessed table or there are steps:
    /// they were built from the current recording and would silently go stale.
    pub fn with_recording(mut self, recording: Recording) -> Result<Self> {
        if !self.preprocessed_tables.is_empty() {
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

    /// Sets (adds, or replaces that source's) preprocessed table. The source is `source`, else
    /// `preprocessed.source`, else the recording's only source; naming two different ones, or
    /// none for a recording with several, is an error. The table must fit its source.
    pub fn with_preprocessed(mut self, preprocessed: g::PreprocessedRecording, source: Option<&str>) -> Result<Self> {
        let mut table = preprocessed;
        if let (Some(given), Some(own)) = (source, table.source.as_deref()) {
            if given != own {
                return invalid(format!("table is for source {own:?}, not {given:?}"));
            }
        }
        let names = self.recording.source_names();
        let name = match (source, table.source.as_deref()) {
            (Some(name), _) | (None, Some(name)) => name.to_string(),
            (None, None) => match names.as_slice() {
                [only] => only.to_string(),
                _ => {
                    return invalid(format!(
                        "recording has {} sources ({names:?}); say which one the preprocessed table is for",
                        names.len()
                    ))
                }
            },
        };
        let Some(target) = self.recording.source(&name) else { return invalid(format!("no such source: {name:?}")) };
        table.source = Some(name.clone());
        let table = PreprocessedRecording::from(table);
        validate_preprocessed(target, &table)?;
        self.preprocessed_tables.retain(|t| t.source.as_deref() != Some(name.as_str()));
        self.preprocessed_tables.push(table);
        let order: Vec<String> = self.recording.source_names().iter().map(|n| n.to_string()).collect();
        self.preprocessed_tables
            .sort_by_key(|t| order.iter().position(|n| Some(n.as_str()) == t.source.as_deref()));
        Ok(self)
    }

    /// Drops the preprocessed table of `source`, or of every source if none is named (steps and
    /// computations are kept). Raises if a named source is unknown or has no table.
    pub fn without_preprocessed(mut self, source: Option<&str>) -> Result<Self> {
        match source {
            None => self.preprocessed_tables.clear(),
            Some(name) => {
                if self.preprocessed_for(name)?.is_none() {
                    return invalid(format!("source {name:?} has no preprocessed table"));
                }
                self.preprocessed_tables.retain(|t| t.source.as_deref() != Some(name));
            }
        }
        Ok(self)
    }

    // ── computations and steps ─────────────────────────────────────────────

    pub fn computation(&self, key: &str) -> Option<&g::DerivedDataset> {
        self.computations.get(key)
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
        match validate_steps(&self.steps, &self.computations, Some(&self.recording)) {
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

    /// The name of the source that `node` ultimately comes from.
    ///
    /// `node` is anything a step can name in `source_node`: a source name, `"preprocessed"`
    /// (single source only), `"preprocessed:<source>"` or the `node` of a recorded step, which is
    /// followed back through its `source_node` (or its `inputs`, if they all share one source) to
    /// its root. `None` for a step that cannot be traced to one source (e.g. inputs from several
    /// sources). Raises for a name that is none of these, including a step that was not recorded.
    pub fn source_of(&self, node: &str) -> Result<Option<String>> {
        let sources = self.recording.source_names();
        let steps: HashMap<&str, &g::ComputationStep> = self.steps.iter().map(|s| (s.node.as_str(), s)).collect();
        let mut seen: HashSet<String> = HashSet::new();
        let mut current: Option<String> = Some(node.to_string());
        loop {
            let Some(name) = current else {
                return Ok(if let [only] = sources.as_slice() { Some(only.to_string()) } else { None });
            };
            if sources.contains(&name.as_str()) {
                return Ok(Some(name));
            }
            if name == PREPROCESSED_NODE {
                return match sources.as_slice() {
                    [only] => Ok(Some(only.to_string())),
                    _ => invalid(format!("{PREPROCESSED_NODE:?} is ambiguous with sources {sources:?}; name one")),
                };
            }
            if let Some(source) = name.strip_prefix(PREPROCESSED_PREFIX) {
                return if sources.contains(&source) {
                    Ok(Some(source.to_string()))
                } else {
                    invalid(format!("{name:?} names unknown source {source:?}"))
                };
            }
            let step = match steps.get(name.as_str()) {
                Some(step) if !seen.contains(&name) => *step,
                _ => return invalid(format!("{name:?} is not a source, a preprocessed table or a recorded step")),
            };
            seen.insert(name);
            if let Some(origin) = &step.source_node {
                current = Some(origin.clone());
            } else if let Some(inputs) = step.inputs.as_ref().filter(|i| !i.is_empty()) {
                let mut origins = HashSet::new();
                for input in inputs {
                    origins.insert(self.source_of(input)?);
                }
                return Ok(if origins.len() == 1 { origins.into_iter().next().unwrap() } else { None });
            } else {
                current = None;
            }
        }
    }

    /// The computations of the steps that trace back to `source` (see `source_of`), by key.
    /// Raises for an unknown source.
    pub fn computations_for_source(&self, source: &str) -> Result<HashMap<&str, &g::DerivedDataset>> {
        if self.recording.source(source).is_none() {
            return invalid(format!("no such source: {source:?}"));
        }
        let mut found = HashMap::new();
        for step in &self.steps {
            if !matches!(self.source_of(&step.node), Ok(Some(origin)) if origin == source) {
                continue;
            }
            for key in step.output_keys.iter().flatten() {
                if let Some(d) = self.computations.get(key) {
                    found.insert(key.as_str(), d);
                }
            }
        }
        Ok(found)
    }

    /// Computation keys no step lists in its `output_keys` (older files, or code that adds
    /// computations without recording a step).
    pub fn unmanaged_keys(&self) -> HashSet<&str> {
        let managed: HashSet<&str> =
            self.steps.iter().flat_map(|s| s.output_keys.iter().flatten().map(String::as_str)).collect();
        self.computations.keys().map(String::as_str).filter(|k| !managed.contains(k)).collect()
    }
}

/// `preprocessed` must fit `source`: one row per gap-free grid position, the same channels,
/// columns of equal length and a positive finite sampling frequency.
pub fn validate_preprocessed(source: &Source, preprocessed: &g::PreprocessedRecording) -> Result<()> {
    let grid_length = *source.sample_index()?.last().unwrap() as usize + 1;
    let channels = |a: &[f64], b: &[f64], c: &[f64]| -> Vec<&'static str> {
        [("channel1", a), ("channel2", b), ("channel3", c)]
            .into_iter()
            .filter(|(_, v)| !v.is_empty())
            .map(|(n, _)| n)
            .collect()
    };
    let raw = channels(source.channel1(), source.channel2(), source.channel3());
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
/// path segments, and every `output_keys` entry must be in `computations`. Step names share one
/// namespace with the reserved "preprocessed" names and, given `recording`, its source names; a
/// `source_node` of the form `preprocessed:<source>` must name one of its sources. (Whether a
/// `source_node` names a recorded step is never checked: that step may have failed.)
pub fn validate_steps(
    steps: &[g::ComputationStep],
    computations: &HashMap<String, g::DerivedDataset>,
    recording: Option<&Recording>,
) -> Result<()> {
    let source_names: Vec<&str> = recording.map(Recording::source_names).unwrap_or_default();
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
        if node == PREPROCESSED_NODE || node.starts_with(PREPROCESSED_PREFIX) || source_names.contains(&node.as_str()) {
            return invalid(format!("step name {node:?} is reserved: it names a source or a preprocessed table"));
        }
        if let (Some(_), Some(origin)) = (recording, step.source_node.as_deref()) {
            if let Some(source) = origin.strip_prefix(PREPROCESSED_PREFIX) {
                if !source_names.contains(&source) {
                    return invalid(format!("step {node:?} reads {origin:?}, but there is no such source"));
                }
            }
        }
    }
    Ok(())
}
