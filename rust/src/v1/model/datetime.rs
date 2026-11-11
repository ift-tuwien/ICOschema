use std::fmt;
use std::str::FromStr;

use super::source::{format_micros, parse_micros};
use crate::Result;

/// A naive time (no time zone, as `recording_metadata.start_time` stores it) with microsecond resolution,
/// like Python's `numpy.datetime64[us]`: what `Source::start_datetime` and `Recording::earliest_start_datetime`
/// return. Ordered, hashable and printed as `YYYY-MM-DDTHH:MM:SS.ffffff`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct DateTime {
    micros: i64,
}

/// The parts of a `DateTime`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Components {
    pub year: i64,
    pub month: u32,
    pub day: u32,
    pub hour: u32,
    pub minute: u32,
    pub second: u32,
    pub microsecond: u32,
}

impl DateTime {
    /// The time `micros` microseconds after 1970-01-01T00:00:00.
    pub fn from_micros(micros: i64) -> Self {
        Self { micros }
    }

    /// Microseconds since 1970-01-01T00:00:00.
    pub fn micros(self) -> i64 {
        self.micros
    }

    /// `YYYY-MM-DD[(T| )HH:MM[:SS[.ffffff]]]` (digits of the fraction beyond the sixth are dropped).
    pub fn parse(text: &str) -> Result<Self> {
        parse_micros(text).map(Self::from_micros)
    }

    /// Seconds from `earlier` to `self` (negative if `self` is before it).
    pub fn seconds_since(self, earlier: DateTime) -> f64 {
        (self.micros - earlier.micros) as f64 / 1e6
    }

    /// This time `seconds` later (earlier if negative), rounded to the microsecond.
    pub fn plus_seconds(self, seconds: f64) -> Self {
        Self { micros: self.micros + (seconds * 1e6).round_ties_even() as i64 }
    }

    pub fn components(self) -> Components {
        let days = self.micros.div_euclid(86_400_000_000);
        let in_day = self.micros.rem_euclid(86_400_000_000);
        // civil date from days since 1970-01-01 (Howard Hinnant's algorithm)
        let z = days + 719_468;
        let era = z.div_euclid(146_097);
        let doe = z.rem_euclid(146_097);
        let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
        let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
        let mp = (5 * doy + 2) / 153;
        let day = (doy - (153 * mp + 2) / 5 + 1) as u32;
        let month = if mp < 10 { mp + 3 } else { mp - 9 } as u32;
        let year = yoe + era * 400 + i64::from(month <= 2);
        let seconds = in_day / 1_000_000;
        Components {
            year,
            month,
            day,
            hour: (seconds / 3600) as u32,
            minute: (seconds / 60 % 60) as u32,
            second: (seconds % 60) as u32,
            microsecond: (in_day % 1_000_000) as u32,
        }
    }
}

impl fmt::Display for DateTime {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&format_micros(self.micros))
    }
}

impl FromStr for DateTime {
    type Err = crate::Error;

    fn from_str(text: &str) -> Result<Self> {
        Self::parse(text)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_prints_and_splits() {
        let time = DateTime::parse("2026-03-04T05:06:07.250000").unwrap();
        assert_eq!(time.to_string(), "2026-03-04T05:06:07.250000");
        assert_eq!(
            time.components(),
            Components { year: 2026, month: 3, day: 4, hour: 5, minute: 6, second: 7, microsecond: 250_000 }
        );
        assert_eq!(DateTime::parse("1970-01-01").unwrap().micros(), 0);
        assert_eq!("2026-03-04T05:06:07".parse::<DateTime>().unwrap().plus_seconds(0.25), time);
        assert!(DateTime::parse("yesterday").is_err());
    }

    #[test]
    fn orders_and_subtracts() {
        let early = DateTime::parse("2026-03-04T05:06:07").unwrap();
        let late = DateTime::parse("2026-03-04T05:06:08.5").unwrap();
        assert!(early < late);
        assert_eq!(late.seconds_since(early), 1.5);
        assert_eq!(early.seconds_since(late), -1.5);
        let before_epoch = DateTime::parse("1969-12-31T23:59:59").unwrap();
        assert_eq!(before_epoch.components().year, 1969);
        assert_eq!(before_epoch.micros(), -1_000_000);
    }
}
