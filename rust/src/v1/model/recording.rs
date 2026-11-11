use icoschema_gen_v1 as g;

use super::Source;
use crate::v1::storage;
use crate::{invalid, Result};

/// A complete recording: one or more independent `Source`s (one per STU/STH combination), each
/// with its own clock, packet counter, ADC settings (hence its own sampling frequency) and
/// sensors. The sources keep their order (the generated `g::Recording` is an unordered map).
///
/// Like `icoschema/v1/model/recording.py`; the per-source data and calculations live on
/// `Source`. A recording with one source is the common case: `only_source()`.
#[derive(Debug, Clone)]
pub struct Recording {
    sources: Vec<Source>,
}

impl Recording {
    /// A recording of `sources` (at least one) with unique names that are single HDF5 path
    /// segments (non-empty, no `/`, not starting with `.`).
    pub fn new(sources: Vec<Source>) -> Result<Self> {
        if sources.is_empty() {
            return invalid("a recording needs at least one source");
        }
        let mut seen = std::collections::HashSet::new();
        for source in &sources {
            let name = source.name();
            if name.is_empty() || name.contains('/') || name.starts_with('.') {
                return invalid(format!("source name {name:?} must be non-empty, contain no '/' and not start with '.'"));
            }
            if !seen.insert(name) {
                return invalid(format!("duplicate source name {name:?}"));
            }
        }
        Ok(Self { sources })
    }

    /// A recording of one source.
    pub fn single(source: impl Into<Source>) -> Result<Self> {
        Self::new(vec![source.into()])
    }

    pub fn from_hdf5(path: &str) -> Result<Self> {
        Self::new(storage::hdf5::load_sources(path)?.into_iter().map(Source::from).collect())
    }

    /// The recording of a TDMS file (see `DatasetBundle::from_tdms`).
    pub fn from_tdms(path: &str) -> Result<Self> {
        Ok(super::DatasetBundle::from_tdms(path)?.recording)
    }

    /// Writes the recording alone to a fresh HDF5 file (format 1.0 for one packet source, 1.3
    /// for several, 1.4 if a source needs it).
    pub fn to_hdf5(&self, path: &str) -> Result<()> {
        storage::write::save_sources(self.sources.iter().map(|s| &**s).collect(), path)
    }

    /// The generated type (a map keyed by source name: the order is lost).
    pub fn into_generated(self) -> g::Recording {
        g::Recording { sources: self.sources.into_iter().map(|s| (s.name().to_string(), s.into_inner())).collect() }
    }

    /// The sources, in order.
    pub fn sources(&self) -> &[Source] {
        &self.sources
    }

    pub fn source(&self, name: &str) -> Option<&Source> {
        self.sources.iter().find(|s| s.name() == name)
    }

    pub fn source_names(&self) -> Vec<&str> {
        self.sources.iter().map(Source::name).collect()
    }

    /// The one source of a single-source recording. Raises naming the sources if there are
    /// several.
    pub fn only_source(&self) -> Result<&Source> {
        match self.sources.as_slice() {
            [only] => Ok(only),
            many => invalid(format!(
                "recording has {} sources ({:?}); pick one with source(name)",
                many.len(),
                self.source_names()
            )),
        }
    }

    /// The earliest `start_time` of the sources (microseconds since the Unix epoch), `None` if
    /// none of them has one.
    pub fn earliest_start(&self) -> Result<Option<i64>> {
        let mut earliest = None;
        for source in &self.sources {
            if let Some(start) = source.start_micros()? {
                earliest = Some(earliest.map_or(start, |e: i64| e.min(start)));
            }
        }
        Ok(earliest)
    }

    /// Each source's start in seconds after the earliest source's start (`0.0` for the earliest,
    /// and for a source without a `start_time`), in source order.
    ///
    /// Sources have independent clocks: this only places them against each other by their
    /// wall-clock start times, it never changes a source's own timestamps, so computations on a
    /// source are not affected by it.
    pub fn start_offsets(&self) -> Result<Vec<(&str, f64)>> {
        let earliest = self.earliest_start()?;
        self.sources
            .iter()
            .map(|source| {
                let offset = match (source.start_micros()?, earliest) {
                    (Some(start), Some(earliest)) => (start - earliest) as f64 / 1e6,
                    _ => 0.0,
                };
                Ok((source.name(), offset))
            })
            .collect()
    }

    /// A source's sample times in seconds on the recording's common axis: its own timestamps
    /// plus its start offset. `source` may be `None` for a single-source recording.
    pub fn time_axis(&self, source: Option<&str>) -> Result<Vec<f64>> {
        let chosen = match source {
            None => self.only_source()?,
            Some(name) => self.source(name).ok_or_else(|| crate::Error::Invalid(format!("no such source: {name:?}")))?,
        };
        let offset = self.start_offsets()?.into_iter().find(|(name, _)| *name == chosen.name()).map_or(0.0, |(_, o)| o);
        Ok(chosen.timestamps().iter().map(|t| *t as f64 / 1e6 + offset).collect())
    }
}

/// Sorted by source name, since the generated type does not keep an order.
impl From<g::Recording> for Recording {
    fn from(inner: g::Recording) -> Self {
        let mut sources: Vec<Source> = inner.sources.into_values().map(Source::from).collect();
        sources.sort_by(|a, b| a.name().cmp(b.name()));
        Self { sources }
    }
}
