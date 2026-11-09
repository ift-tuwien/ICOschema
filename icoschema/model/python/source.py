"""A `Source`: the data of one acquisition source (one STU/STH combination)
-- its hardware/sensor metadata and per-sample data -- plus everything that
is derived from a single source's counter, channels and ADC settings: numpy
getters, signal_loss_percentage, a JSON-encodable summary(), the gap-free
sample grid (rows_per_packet(), sample_index(), filled_mask()) and the
sampling frequency implied by the ADC settings (total_sampling_frequency(),
channel_sampling_frequency()).

Sources of one `Recording` are independent: each has its own clock, packet
counter, ADC settings (hence its own sampling frequency) and sensors.

This file should never be imported directly, but rather only via a
`Recording`:

    from icoschema import Recording

    recording = Recording.from_hdf5("some_file.hdf5")
    source = recording.sources["source1"]
    df = source.to_dataframe()

Note: Compensation/Conversion (on HardwareMetadata.channelN_metadata) is
purely descriptive of what has already been applied to a channel's raw
RecordingData values -- it is not applied by this class, or by anything
else here.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import numpy as np
import pandas as pd

from icoschema.schema.generated.python import dataset as generated

# The ADC's clock in Hz and its default (prescaler, acquisition time,
# oversample rate) settings, which nearly every recording uses. With them,
# the total sampling frequency is 38.4 MHz / (3 * 21 * 64) = 9523.8095... Hz.
ADC_CLOCK_HZ = 38_400_000
DEFAULT_ADC_SETTINGS = (2, 8, 64)

# Files saved by icocompute from TDMS files before `Source.sampling_frequency` and `Source.quality` existed
# keep the rate and the loss as JSON under this key of `post_metadata`; `Source` still understands it.
LEGACY_TDMS_KEY = "tdms"


def _lost_packets(counter: np.ndarray) -> np.ndarray:
    """Packets dropped between each pair of consecutive rows (length
    `len(counter) - 1`), from gaps in the 8-bit wrapping packet counter."""
    gaps = np.diff(counter) - 1
    gaps[gaps == -1] = 0  # counter repeated (no increment): same packet
    gaps[gaps == -256] = 0  # clean wraparound 255 -> 0
    gaps[gaps < 0] += 256  # wraparound with loss
    return gaps


class Source(generated.Source):
    """One acquisition source (STU/STH combination) of a `Recording`.

    Has every field of `ICOschema.schema.generated.python.dataset.Source`
    (`name`, `stu_id`, `sth_id`, `sampling_frequency`, `quality`,
    `additional_data`, `hardware_metadata`, `recording_metadata`,
    `recording_data`), plus the getters and calculations below.

    A source is either packet-based (HDF5: `counter` and ADC settings give the
    sampling frequency and the packet loss) or a plain waveform (TDMS: no
    counter, `sampling_frequency` is set and loss comes from `quality`).
    """

    def __post_init__(self, *args: Any, **kwargs: Any) -> None:
        super().__post_init__(*args, **kwargs)
        name = str(self.name)
        if not name or "/" in name or name.startswith("."):
            raise ValueError(f"source name {name!r} must be non-empty, contain no '/' and not start with '.'")

    @property
    def timestamps(self) -> np.ndarray:
        """recording_data.timestamp as a numpy array (integer microseconds since recording_metadata.start_time)."""
        return np.asarray(self.recording_data.timestamp)

    @property
    def channel1(self) -> np.ndarray:
        """recording_data.channel1 as a numpy array. Always present."""
        return np.asarray(self.recording_data.channel1)

    @property
    def channel2(self) -> np.ndarray:
        """recording_data.channel2 as a numpy array. Empty if this recording has no second channel."""
        return np.asarray(self.recording_data.channel2)

    @property
    def channel3(self) -> np.ndarray:
        """recording_data.channel3 as a numpy array. Empty if this recording has no third channel."""
        return np.asarray(self.recording_data.channel3)

    @property
    def counter(self) -> np.ndarray:
        """recording_data.counter as a numpy array (an 8-bit wrapping packet
        counter). Empty for a source without a packet counter (`has_counter`)."""
        return np.asarray(self.recording_data.counter, dtype=int)

    @property
    def has_counter(self) -> bool:
        """Whether this source has a packet counter (a TDMS source has none)."""
        return len(self.recording_data.counter) > 0

    def _legacy_tdms(self) -> dict[str, Any] | None:
        """The JSON section older icocompute versions kept in `post_metadata`
        for files read from TDMS (see `LEGACY_TDMS_KEY`), if present."""
        raw = self.recording_metadata.post_metadata
        if not raw:
            return None
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        section = parsed.get(LEGACY_TDMS_KEY) if isinstance(parsed, dict) else None
        return section if isinstance(section, dict) else None

    def quality_loss_percentage(self) -> float | None:
        """`100 - mean(quality)` (clipped to 0..100) of `quality`, `None` if
        there is no usable quality data (none, empty or only non-finite)."""
        if self.quality is None:
            return None
        values = np.asarray(self.quality.values, dtype=np.float64)
        values = values[np.isfinite(values)]
        if values.size == 0:
            return None
        return float(np.clip(100.0 - values.mean(), 0.0, 100.0))

    @property
    def signal_loss_measured(self) -> bool:
        """Whether `signal_loss_percentage` is measured (from `quality` or the
        packet counter) rather than an assumed 0 (a source with neither)."""
        if self.quality_loss_percentage() is not None:
            return True
        legacy = self._legacy_tdms()
        if legacy is not None and "signal_loss_percentage" in legacy:
            return bool(legacy.get("signal_loss_measured", False))
        return self.has_counter

    @property
    def channel_count(self) -> int:
        """Number of channels present (non-empty) in this recording."""
        return sum(getattr(self, name).size > 0 for name in ("channel1", "channel2", "channel3"))

    @property
    def signal_loss_percentage(self) -> float:
        """Percentage of data lost.

        From `quality` if the source has it (`100 - mean(quality)`); else, for
        a source without a packet counter, 0 (an assumption: see
        `signal_loss_measured`); else inferred from gaps/wraparounds in
        `counter`, as described next.

        `counter` is an 8-bit counter (wraps 255 -> 0) that increments once per
        packet; a jump of more than 1 between consecutive samples (accounting
        for wraparound) means packets were dropped in between.

        A packet can carry more than one sample row, all sharing one counter
        value (e.g. 3 rows per packet for a 1-channel recording, 1 for a
        3-channel one), so received packets are counted as runs of equal
        consecutive counter values, not as rows -- otherwise lost packets
        would be divided by received rows and multi-row recordings would
        under-report their loss.
        """
        from_quality = self.quality_loss_percentage()
        if from_quality is not None:
            return from_quality
        legacy = self._legacy_tdms()
        if legacy is not None and "signal_loss_percentage" in legacy:
            return float(legacy["signal_loss_percentage"])
        if not self.has_counter:
            return 0.0
        counter = self.counter
        total_lost = int(np.sum(_lost_packets(counter)))
        total_received = int(np.count_nonzero(np.diff(counter))) + 1
        return (total_lost / (total_received + total_lost)) * 100

    def rows_per_packet(self) -> int:
        """Number of rows sharing each counter value, i.e. how many rows one
        packet carries (e.g. 3 for a 1-channel recording, 1 for a 3-channel
        one).

        Inferred from the lengths of runs of equal consecutive counter
        values; the first and last run may be shorter (a recording can start
        or end mid-packet) and are only used if they're the only runs.
        Raises `ValueError` for an empty counter or if the interior runs
        disagree, since then no single per-packet row count exists and any
        grid placement would be misaligned.
        """
        counter = self.counter
        if counter.size == 0 and self.timestamps.size > 0:
            return 1  # no packets: every row is its own
        if counter.size == 0:
            raise ValueError("cannot infer rows per packet from an empty counter")
        boundaries = np.flatnonzero(np.diff(counter) != 0) + 1
        run_lengths = np.diff(np.concatenate(([0], boundaries, [counter.size])))
        interior = run_lengths[1:-1]
        if interior.size == 0:
            return int(run_lengths.max())
        distinct = np.unique(interior)
        if distinct.size != 1:
            raise ValueError(f"inconsistent rows per packet in counter: run lengths {distinct.tolist()}")
        return int(distinct[0])

    def sample_index(self) -> np.ndarray:
        """Each received row's position on the gap-free sample grid (int64).

        Row `i` lands at `i` plus every row lost to dropped packets before
        it, so the first row is position 0 and the grid's length is
        `sample_index()[-1] + 1`. A `PreprocessedRecording`'s row `j` is grid
        position `j`. Raises like `rows_per_packet()`. Without a packet
        counter every row is a position of its own (`0, 1, 2, ...`).
        """
        counter = self.counter
        if counter.size == 0 and self.timestamps.size > 0:
            return np.arange(self.timestamps.size, dtype=np.int64)
        lost_rows = _lost_packets(counter) * self.rows_per_packet()
        return np.arange(counter.size, dtype=np.int64) + np.concatenate(([0], np.cumsum(lost_rows))).astype(np.int64)

    def filled_mask(self) -> np.ndarray:
        """Boolean mask over the gap-free grid: `True` at positions no row was
        received for (lost packets), `False` at received rows. All `False`
        without a packet counter."""
        index = self.sample_index()
        mask = np.ones(int(index[-1]) + 1, dtype=bool)
        mask[index] = False
        return mask

    def total_sampling_frequency(self) -> tuple[float, Literal["hardware", "default"]]:
        """The ADC's total sampling frequency in Hz, shared round-robin by all
        channels, and where it came from.

        `ADC_CLOCK_HZ / ((adc_prescaler + 1) * (adc_acquisition_time + 13) *
        adc_oversample_rate)` from the settings in `hardware_metadata`
        (`"hardware"`) if all three are recorded, else from the default ADC
        settings (`"default"`). Raises `ValueError` if only some are recorded
        or a setting is out of range, rather than guessing.

        A source with its own `sampling_frequency` (TDMS) reports that times
        `channel_count` as `"hardware"`.
        """
        own = self._own_sampling_frequency()
        if own is not None:
            return own * max(self.channel_count, 1), "hardware"
        hardware = self.hardware_metadata
        settings = (hardware.adc_prescaler, hardware.adc_acquisition_time, hardware.adc_oversample_rate)
        if all(value is None for value in settings):
            prescaler, acquisition_time, oversample_rate = DEFAULT_ADC_SETTINGS
            source: Literal["hardware", "default"] = "default"
        elif any(value is None for value in settings):
            raise ValueError(
                "incomplete ADC settings: adc_prescaler, adc_acquisition_time and "
                f"adc_oversample_rate must all be set or all be absent, got {settings}"
            )
        else:
            prescaler, acquisition_time, oversample_rate = (int(value) for value in settings)
            source = "hardware"
        if prescaler < 0 or acquisition_time < 0 or oversample_rate <= 0:
            raise ValueError(
                "invalid ADC settings: need adc_prescaler >= 0, adc_acquisition_time >= 0 "
                f"and adc_oversample_rate > 0, got {(prescaler, acquisition_time, oversample_rate)}"
            )
        return ADC_CLOCK_HZ / ((prescaler + 1) * (acquisition_time + 13) * oversample_rate), source

    def _own_sampling_frequency(self) -> float | None:
        """The per-channel rate the source's data states (`sampling_frequency`,
        or the legacy TDMS section), `None` if it has to follow from ADC settings."""
        if self.sampling_frequency is not None:
            return float(self.sampling_frequency)
        legacy = self._legacy_tdms()
        if legacy is not None and "sampling_frequency" in legacy:
            return float(legacy["sampling_frequency"])
        return None

    def channel_sampling_frequency(self) -> tuple[float, Literal["hardware", "default"]]:
        """The per-channel sampling frequency in Hz and where it came from:
        the source's own `sampling_frequency` if it has one (`"hardware"`),
        else `total_sampling_frequency()` divided by `channel_count`. Raises
        `ValueError` for a recording without channels."""
        own = self._own_sampling_frequency()
        if own is not None:
            return own, "hardware"
        if self.channel_count == 0:
            raise ValueError("recording has no channels to split the sampling frequency across")
        total, source = self.total_sampling_frequency()
        return total / self.channel_count, source

    def summary(self) -> dict[str, Any]:
        """A compact, JSON-encodable summary of this recording.

        Every value is a plain `str`/`int`/`float`/`None` (never a numpy
        scalar or array) so `json.dumps(recording.summary())` always
        succeeds without a custom encoder -- this is meant to be safe to
        hand directly to a future web API response.
        """
        channels: dict[str, dict[str, Any]] = {}
        channel_metadata = {
            "channel1": self.hardware_metadata.channel1_metadata,
            "channel2": self.hardware_metadata.channel2_metadata,
            "channel3": self.hardware_metadata.channel3_metadata,
        }
        for name, metadata in channel_metadata.items():
            values = getattr(self, name)
            if values.size == 0:
                continue
            sensor = metadata.sensor if metadata is not None else None
            channels[name] = {
                "sensor_id": sensor.sensor_id if sensor is not None else None,
                "sensor_type": sensor.sensor_type if sensor is not None else None,
                "unit": sensor.unit if sensor is not None else None,
                "sample_count": int(values.size),
                "min": float(np.min(values)),
                "max": float(np.max(values)),
                "mean": float(np.mean(values)),
                "std": float(np.std(values)),
            }

        return {
            "start_time": self.recording_metadata.start_time,
            "sample_count": len(self.timestamps),
            "signal_loss_percentage": float(self.signal_loss_percentage),
            "signal_loss_measured": self.signal_loss_measured,
            "channels": channels,
        }

    def start_datetime(self) -> np.datetime64 | None:
        """`recording_metadata.start_time` as a `datetime64[us]`, `None` if the
        source has none."""
        start = self.recording_metadata.start_time
        return np.datetime64(start, "us") if start else None

    def to_dataframe(self) -> pd.DataFrame:
        """recording_data as a DataFrame (columns: timestamp, counter if the
        source has one, channel1, and channel2/channel3 if present).

        Values are raw and uncompensated -- see the module docstring's note
        on Compensation/Conversion.
        """
        data = self.recording_data
        columns: dict[str, Any] = {"timestamp": data.timestamp}
        if data.counter:
            columns["counter"] = data.counter
        columns["channel1"] = data.channel1
        if data.channel2:
            columns["channel2"] = data.channel2
        if data.channel3:
            columns["channel3"] = data.channel3
        return pd.DataFrame(columns)
