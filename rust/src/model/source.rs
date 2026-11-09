use std::ops::Deref;

use icoschema_gen as g;

use crate::{invalid, Result};

/// The ADC clock in Hz and its default (prescaler, acquisition time, oversample rate) settings.
pub const ADC_CLOCK_HZ: f64 = 38_400_000.0;
pub const DEFAULT_ADC_SETTINGS: (isize, isize, isize) = (2, 8, 64);

/// Files icocompute saved from TDMS files before `Source::sampling_frequency` and
/// `Source::quality` existed keep the rate and the loss as JSON under this key of `post_metadata`.
pub const LEGACY_TDMS_KEY: &str = "tdms";

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
    pub signal_loss_measured: bool,
    /// `("channel1", ..)` in order, only channels that have data.
    pub channels: Vec<(&'static str, ChannelSummary)>,
}

/// One acquisition source (STU/STH combination) of a recording: its hardware and sensor metadata
/// and its per-sample data, plus everything derived from a single source's counter, channels and
/// ADC settings (like `icoschema/model/python/source.py`).
///
/// A source is either packet-based (HDF5: `counter` and the ADC settings give the sampling
/// frequency and the packet loss) or a plain waveform (TDMS: no counter, `sampling_frequency` is
/// set and the loss comes from `quality`).
#[derive(Debug, Clone)]
pub struct Source(g::Source);

impl Deref for Source {
    type Target = g::Source;
    fn deref(&self) -> &g::Source {
        &self.0
    }
}

impl From<g::Source> for Source {
    fn from(inner: g::Source) -> Self {
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

impl Source {
    pub fn into_inner(self) -> g::Source {
        self.0
    }

    pub fn name(&self) -> &str {
        &self.0.name
    }

    /// Integer microseconds since `recording_metadata.start_time`.
    pub fn timestamps(&self) -> &[isize] {
        &self.0.recording_data.timestamp
    }

    /// The 8-bit wrapping packet counter; empty for a source without one (`has_counter`).
    pub fn counter(&self) -> &[isize] {
        self.0.recording_data.counter.as_deref().unwrap_or(&[])
    }

    /// Whether this source has a packet counter (a TDMS source has none).
    pub fn has_counter(&self) -> bool {
        !self.counter().is_empty()
    }

    pub fn channel1(&self) -> &[f64] {
        &self.0.recording_data.channel1
    }

    /// Empty if the source has no second channel.
    pub fn channel2(&self) -> &[f64] {
        self.0.recording_data.channel2.as_deref().unwrap_or(&[])
    }

    /// Empty if the source has no third channel.
    pub fn channel3(&self) -> &[f64] {
        self.0.recording_data.channel3.as_deref().unwrap_or(&[])
    }

    fn channels(&self) -> [(&'static str, &[f64]); 3] {
        [("channel1", self.channel1()), ("channel2", self.channel2()), ("channel3", self.channel3())]
    }

    pub fn channel_count(&self) -> usize {
        self.channels().iter().filter(|(_, v)| !v.is_empty()).count()
    }

    /// The JSON section older icocompute versions kept in `post_metadata` for files read from
    /// TDMS (see `LEGACY_TDMS_KEY`), if present.
    fn legacy_tdms(&self) -> Option<serde_json::Map<String, serde_json::Value>> {
        let raw = self.0.recording_metadata.post_metadata.as_deref().filter(|s| !s.is_empty())?;
        let parsed: serde_json::Value = serde_json::from_str(raw).ok()?;
        parsed.get(LEGACY_TDMS_KEY)?.as_object().cloned()
    }

    /// `100 - mean(quality)` (clipped to 0..100) of `quality`; `None` if there is no usable
    /// quality data (none, empty or only non-finite values).
    pub fn quality_loss_percentage(&self) -> Option<f64> {
        let finite: Vec<f64> = self.0.quality.as_ref()?.values.iter().copied().filter(|v| v.is_finite()).collect();
        if finite.is_empty() {
            return None;
        }
        let mean = finite.iter().sum::<f64>() / finite.len() as f64;
        Some((100.0 - mean).clamp(0.0, 100.0))
    }

    /// Whether `signal_loss_percentage` is measured (from `quality` or the packet counter) rather
    /// than an assumed 0 (a source with neither).
    pub fn signal_loss_measured(&self) -> bool {
        if self.quality_loss_percentage().is_some() {
            return true;
        }
        if let Some(legacy) = self.legacy_tdms() {
            if legacy.contains_key("signal_loss_percentage") {
                return legacy.get("signal_loss_measured").and_then(serde_json::Value::as_bool).unwrap_or(false);
            }
        }
        self.has_counter()
    }

    /// Percentage of data lost: from `quality` if the source has it (`100 - mean(quality)`); else,
    /// for a source without a packet counter, 0 (an assumption: see `signal_loss_measured`); else
    /// inferred from gaps in `counter`. A packet can carry more than one row, all sharing one
    /// counter value, so received packets are counted as runs of equal consecutive values.
    pub fn signal_loss_percentage(&self) -> f64 {
        if let Some(loss) = self.quality_loss_percentage() {
            return loss;
        }
        if let Some(loss) = self.legacy_tdms().and_then(|l| l.get("signal_loss_percentage")?.as_f64()) {
            return loss;
        }
        if !self.has_counter() {
            return 0.0;
        }
        let counter = self.counter();
        let lost: isize = lost_packets(counter).iter().sum();
        let received = counter.windows(2).filter(|w| w[0] != w[1]).count() as isize + 1;
        lost as f64 / (received + lost) as f64 * 100.0
    }

    /// How many rows one packet carries (the length of runs of equal counter values); 1 for a
    /// source without a counter.
    pub fn rows_per_packet(&self) -> Result<usize> {
        let counter = self.counter();
        if counter.is_empty() && !self.timestamps().is_empty() {
            return Ok(1);
        }
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

    /// Each received row's position on the gap-free sample grid. Without a packet counter every
    /// row is a position of its own (`0, 1, 2, ...`).
    pub fn sample_index(&self) -> Result<Vec<i64>> {
        if !self.has_counter() && !self.timestamps().is_empty() {
            return Ok((0..self.timestamps().len() as i64).collect());
        }
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

    /// `true` at grid positions no row was received for (lost packets); all `false` without a
    /// packet counter.
    pub fn filled_mask(&self) -> Result<Vec<bool>> {
        let index = self.sample_index()?;
        let mut mask = vec![true; *index.last().unwrap_or(&-1) as usize + 1];
        for i in index {
            mask[i as usize] = false;
        }
        Ok(mask)
    }

    /// The per-channel rate the source's data states (`sampling_frequency`, or the legacy TDMS
    /// section); `None` if it has to follow from the ADC settings.
    fn own_sampling_frequency(&self) -> Option<f64> {
        self.0
            .sampling_frequency
            .or_else(|| self.legacy_tdms().and_then(|l| l.get("sampling_frequency")?.as_f64()))
    }

    /// The ADC's total sampling frequency in Hz, shared round-robin by all channels, and where it
    /// came from. A source with its own `sampling_frequency` reports that times `channel_count`.
    pub fn total_sampling_frequency(&self) -> Result<(f64, FrequencySource)> {
        if let Some(own) = self.own_sampling_frequency() {
            return Ok((own * self.channel_count().max(1) as f64, FrequencySource::Hardware));
        }
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

    /// The per-channel sampling frequency in Hz and where it came from: the source's own
    /// `sampling_frequency` if it has one, else `total_sampling_frequency` divided by
    /// `channel_count`.
    pub fn channel_sampling_frequency(&self) -> Result<(f64, FrequencySource)> {
        if let Some(own) = self.own_sampling_frequency() {
            return Ok((own, FrequencySource::Hardware));
        }
        if self.channel_count() == 0 {
            return invalid("recording has no channels to split the sampling frequency across");
        }
        let (total, source) = self.total_sampling_frequency()?;
        Ok((total / self.channel_count() as f64, source))
    }

    /// `recording_metadata.start_time` as microseconds since the Unix epoch (naive time, as
    /// stored), `None` if the source has none. Raises for a value that is not an ISO 8601 time.
    pub fn start_micros(&self) -> Result<Option<i64>> {
        match self.0.recording_metadata.start_time.as_deref().filter(|s| !s.is_empty()) {
            None => Ok(None),
            Some(text) => parse_micros(text).map(Some),
        }
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
            sample_count: self.timestamps().len(),
            signal_loss_percentage: self.signal_loss_percentage(),
            signal_loss_measured: self.signal_loss_measured(),
            channels,
        }
    }
}

/// `YYYY-MM-DD[(T| )HH:MM[:SS[.ffffff]]]` as microseconds since 1970-01-01 (digits of the
/// fraction beyond the sixth are dropped).
fn parse_micros(text: &str) -> Result<i64> {
    let bad = || crate::Error::Invalid(format!("{text:?} is not an ISO 8601 time (YYYY-MM-DDTHH:MM:SS.ffffff)"));
    let (date, time) = match text.split_once(['T', ' ']) {
        Some((d, t)) => (d, Some(t)),
        None => (text, None),
    };
    let number = |s: &str| s.parse::<i64>().map_err(|_| bad());
    let mut d = date.splitn(3, '-');
    let (year, month, day) = (number(d.next().ok_or_else(bad)?)?, number(d.next().ok_or_else(bad)?)?, number(d.next().ok_or_else(bad)?)?);
    if !(1..=12).contains(&month) || !(1..=31).contains(&day) {
        return Err(bad());
    }
    // days since 1970-01-01 (proleptic Gregorian; Howard Hinnant's algorithm)
    let y = if month <= 2 { year - 1 } else { year };
    let era = y.div_euclid(400);
    let yoe = y.rem_euclid(400);
    let doy = (153 * (if month > 2 { month - 3 } else { month + 9 }) + 2) / 5 + day - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;

    let mut micros = 0i64;
    if let Some(time) = time {
        let (clock, fraction) = match time.split_once('.') {
            Some((c, f)) => (c, f),
            None => (time, ""),
        };
        let mut t = clock.splitn(3, ':');
        let hours = number(t.next().ok_or_else(bad)?)?;
        let minutes = number(t.next().ok_or_else(bad)?)?;
        let seconds = t.next().map(number).transpose()?.unwrap_or(0);
        if !(0..24).contains(&hours) || !(0..60).contains(&minutes) || !(0..=60).contains(&seconds) {
            return Err(bad());
        }
        let digits: String = fraction.chars().take(6).collect();
        if !digits.chars().all(|c| c.is_ascii_digit()) {
            return Err(bad());
        }
        let fraction_micros = if digits.is_empty() { 0 } else { number(&format!("{digits:0<6}"))? };
        micros = ((hours * 60 + minutes) * 60 + seconds) * 1_000_000 + fraction_micros;
    }
    Ok(days * 86_400_000_000 + micros)
}

#[cfg(test)]
mod tests {
    use super::parse_micros;

    #[test]
    fn parses_iso_times_like_numpy() {
        assert_eq!(parse_micros("1970-01-01").unwrap(), 0);
        assert_eq!(parse_micros("1970-01-02T00:00:01.5").unwrap(), 86_400_000_000 + 1_500_000);
        assert_eq!(parse_micros("2026-01-01 00:00:10.500000").unwrap() - parse_micros("2026-01-01T00:00:00").unwrap(), 10_500_000);
        assert_eq!(parse_micros("2000-03-01").unwrap() - parse_micros("2000-02-28").unwrap(), 2 * 86_400_000_000); // leap year
        assert!(parse_micros("yesterday").is_err());
    }
}
