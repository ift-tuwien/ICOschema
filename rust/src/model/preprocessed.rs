use std::ops::Deref;

use icoschema_gen as g;

/// A recording's channels on the gap-free grid with rebased timestamps.
#[derive(Debug, Clone)]
pub struct PreprocessedRecording(g::PreprocessedRecording);

impl Deref for PreprocessedRecording {
    type Target = g::PreprocessedRecording;
    fn deref(&self) -> &g::PreprocessedRecording {
        &self.0
    }
}

impl From<g::PreprocessedRecording> for PreprocessedRecording {
    fn from(inner: g::PreprocessedRecording) -> Self {
        Self(inner)
    }
}

impl PreprocessedRecording {
    pub fn timestamps(&self) -> &[isize] {
        &self.0.timestamp
    }
    pub fn channel1_values(&self) -> &[f64] {
        &self.0.channel1
    }
    pub fn channel2_values(&self) -> &[f64] {
        self.0.channel2.as_deref().unwrap_or(&[])
    }
    pub fn channel3_values(&self) -> &[f64] {
        self.0.channel3.as_deref().unwrap_or(&[])
    }
    pub fn len(&self) -> usize {
        self.0.timestamp.len()
    }
    pub fn is_empty(&self) -> bool {
        self.0.timestamp.is_empty()
    }
}
