use std::ops::Deref;

use icoschema_gen as g;

use crate::{invalid, storage, Result};

/// The ADC clock in Hz and its default (prescaler, acquisition time, oversample rate) settings.
pub const ADC_CLOCK_HZ: f64 = 38_400_000.0;
pub const DEFAULT_ADC_SETTINGS: (isize, isize, isize) = (2, 8, 64);

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrequencySource {
    Hardware,
    Default,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ChannelSummary {
    pub sensor_id: Option<String>,
    pub sensor_type: Option<String>,
    pub unit: Option<String>,
    pub sample_count: usize,
    pub min: f64,
    pub max: f64,
    pub mean: f64,
    pub std: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Summary {
    pub start_time: Option<String>,
    pub sample_count: usize,
    pub signal_loss_percentage: f64,
    /// `("channel1", ..)` in order, only channels that have data.
    pub channels: Vec<(&'static str, ChannelSummary)>,
}

/// A complete recording: hardware/sensor metadata plus its sample data.
#[derive(Debug, Clone)]
pub struct Recording(g::Recording);

impl Deref for Recording {
    type Target = g::Recording;
    fn deref(&self) -> &g::Recording {
        &self.0
    }
}

impl From<g::Recording> for Recording {
    fn from(inner: g::Recording) -> Self {
        Self(inner)
    }
}

/// Packets dropped between each pair of consecutive rows, from gaps in the 8-bit wrapping counter.
fn lost_packets(counter: &[isize]) -> Vec<isize> {
    counter
        .windows(2)
        .map(|w| {
            let gap = w[1] - w[0] - 1;
            match gap {
                -1 | -256 => 0,
                g if g < 0 => g + 256,
                g => g,
            }
        })
        .collect()
}

impl Recording {
    pub fn from_hdf5(path: &str) -> Result<Self> {
        storage::hdf5::load_recording(path).map(Self)
    }

    pub fn into_inner(self) -> g::Recording {
        self.0
    }

    /// Integer microseconds since `recording_metadata.start_time`.
    pub fn timestamps(&self) -> &[isize] {
        &self.0.recording_data.timestamp
    }

    /// The 8-bit wrapping packet counter.
    pub fn counter(&self) -> &[isize] {
        &self.0.recording_data.counter
    }

    pub fn channel1(&self) -> &[f64] {
        &self.0.recording_data.channel1
    }

    /// Empty if the recording has no second channel.
    pub fn channel2(&self) -> &[f64] {
        self.0.recording_data.channel2.as_deref().unwrap_or(&[])
    }

    /// Empty if the recording has no third channel.
    pub fn channel3(&self) -> &[f64] {
        self.0.recording_data.channel3.as_deref().unwrap_or(&[])
    }

    fn channels(&self) -> [(&'static str, &[f64]); 3] {
        [("channel1", self.channel1()), ("channel2", self.channel2()), ("channel3", self.channel3())]
    }

    pub fn channel_count(&self) -> usize {
        self.channels().iter().filter(|(_, v)| !v.is_empty()).count()
    }

    /// Percentage of packets lost, inferred from gaps in `counter`.
    pub fn signal_loss_percentage(&self) -> f64 {
        let counter = self.counter();
        let lost: isize = lost_packets(counter).iter().sum();
        let received = counter.windows(2).filter(|w| w[0] != w[1]).count() as isize + 1;
        lost as f64 / (received + lost) as f64 * 100.0
    }

    /// How many rows one packet carries (the length of runs of equal counter values).
    pub fn rows_per_packet(&self) -> Result<usize> {
        let counter = self.counter();
        if counter.is_empty() {
            return invalid("cannot infer rows per packet from an empty counter");
        }
        let mut runs = Vec::new();
        let mut start = 0;
        for i in 1..=counter.len() {
            if i == counter.len() || counter[i] != counter[i - 1] {
                runs.push(i - start);
                start = i;
            }
        }
        // The first and last run may be partial; they only count if they are the only ones.
        let interior = if runs.len() > 2 { &runs[1..runs.len() - 1] } else { &[][..] };
        match interior {
            [] => Ok(*runs.iter().max().unwrap()),
            [first, rest @ ..] if rest.iter().all(|r| r == first) => Ok(*first),
            _ => invalid("inconsistent rows per packet in counter"),
        }
    }

    /// Each received row's position on the gap-free sample grid.
    pub fn sample_index(&self) -> Result<Vec<i64>> {
        let rows = self.rows_per_packet()? as i64;
        let mut lost_rows = 0i64;
        let mut out = Vec::with_capacity(self.counter().len());
        out.push(0);
        for (i, lost) in lost_packets(self.counter()).into_iter().enumerate() {
            lost_rows += lost as i64 * rows;
            out.push(i as i64 + 1 + lost_rows);
        }
        Ok(out)
    }

    /// `true` at grid positions no row was received for (lost packets).
    pub fn filled_mask(&self) -> Result<Vec<bool>> {
        let index = self.sample_index()?;
        let mut mask = vec![true; *index.last().unwrap_or(&-1) as usize + 1];
        for i in index {
            mask[i as usize] = false;
        }
        Ok(mask)
    }

    /// The ADC's total sampling frequency in Hz and where it came from.
    pub fn total_sampling_frequency(&self) -> Result<(f64, FrequencySource)> {
        let hw = &self.0.hardware_metadata;
        let (p, a, o, source) = match (hw.adc_prescaler, hw.adc_acquisition_time, hw.adc_oversample_rate) {
            (None, None, None) => {
                let (p, a, o) = DEFAULT_ADC_SETTINGS;
                (p, a, o, FrequencySource::Default)
            }
            (Some(p), Some(a), Some(o)) => (p, a, o, FrequencySource::Hardware),
            _ => return invalid("incomplete ADC settings: all of prescaler, acquisition time and oversample rate, or none"),
        };
        if p < 0 || a < 0 || o <= 0 {
            return invalid(format!("invalid ADC settings: {:?}", (p, a, o)));
        }
        Ok((ADC_CLOCK_HZ / ((p + 1) * (a + 13) * o) as f64, source))
    }

    pub fn channel_sampling_frequency(&self) -> Result<(f64, FrequencySource)> {
        if self.channel_count() == 0 {
            return invalid("recording has no channels to split the sampling frequency across");
        }
        let (total, source) = self.total_sampling_frequency()?;
        Ok((total / self.channel_count() as f64, source))
    }

    pub fn summary(&self) -> Summary {
        let metadata = [
            Some(&self.0.hardware_metadata.channel1_metadata),
            self.0.hardware_metadata.channel2_metadata.as_ref(),
            self.0.hardware_metadata.channel3_metadata.as_ref(),
        ];
        let channels = self
            .channels()
            .into_iter()
            .zip(metadata)
            .filter(|((_, values), _)| !values.is_empty())
            .map(|((name, values), meta)| {
                let n = values.len() as f64;
                let mean = values.iter().sum::<f64>() / n;
                let var = values.iter().map(|v| (v - mean).powi(2)).sum::<f64>() / n;
                let sensor = meta.map(|m| &m.sensor);
                (
                    name,
                    ChannelSummary {
                        sensor_id: sensor.and_then(|s| s.sensor_id.clone()),
                        sensor_type: sensor.and_then(|s| s.sensor_type.clone()),
                        unit: sensor.and_then(|s| s.unit.clone()),
                        sample_count: values.len(),
                        min: values.iter().copied().fold(f64::INFINITY, f64::min),
                        max: values.iter().copied().fold(f64::NEG_INFINITY, f64::max),
                        mean,
                        std: var.sqrt(),
                    },
                )
            })
            .collect();
        Summary {
            start_time: self.0.recording_metadata.start_time.clone(),
            sample_count: self.counter().len(),
            signal_loss_percentage: self.signal_loss_percentage(),
            channels,
        }
    }
}
