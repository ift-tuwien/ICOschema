"""The public API of this repository: a `Recording` that inherits all
fields from the generated `dataset.Recording` (see
ICOschema/schema/generated/python) and adds a few things that aren't
auto-generated: loading from / writing to a specific storage backend,
converting to a pandas DataFrame, quick pass-through getters for the raw
arrays (timestamps, counter, channel1/2/3), as numpy arrays, that plotting
code typically wants directly instead of going through recording_data or a
DataFrame, signal_loss_percentage, a JSON-encodable summary() of the
whole recording, the gap-free sample grid (rows_per_packet(),
sample_index(), filled_mask()), and the sampling frequency implied by the
ADC settings (total_sampling_frequency(), channel_sampling_frequency()).

This file should never be imported directly, but rather only from the main
entrypoint:

    from icoschema import Recording

    recording = Recording.from_hdf5("some_file.hdf5")
    df = recording.to_dataframe()

ICOschema.schema.generated (plain data, no behavior) and ICOschema.storage
(storage-format-specific I/O) are internal implementation details of this
module and should not be imported directly by other codebases.

Note: Compensation/Conversion (on HardwareMetadata.channelN_metadata) is
purely descriptive of what has already been applied to a channel's raw
RecordingData values -- it is not applied by this class, or by anything
else here.
"""

from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd

from icoschema.schema.generated.python import dataset as generated

# The ADC's clock in Hz and its default (prescaler, acquisition time,
# oversample rate) settings, which nearly every recording uses. With them,
# the total sampling frequency is 38.4 MHz / (3 * 21 * 64) = 9523.8095... Hz.
ADC_CLOCK_HZ = 38_400_000
DEFAULT_ADC_SETTINGS = (2, 8, 64)


def _lost_packets(counter: np.ndarray) -> np.ndarray:
    """Packets dropped between each pair of consecutive rows (length
    `len(counter) - 1`), from gaps in the 8-bit wrapping packet counter."""
    gaps = np.diff(counter) - 1
    gaps[gaps == -1] = 0  # counter repeated (no increment): same packet
    gaps[gaps == -256] = 0  # clean wraparound 255 -> 0
    gaps[gaps < 0] += 256  # wraparound with loss
    return gaps


class Recording(generated.Recording):
    """A complete recording: hardware/sensor metadata plus its sample data.

    Has every field of `ICOschema.schema.generated.python.dataset.Recording`
    (`hardware_metadata`, `recording_metadata`, `recording_data`), plus the
    loading/writing and convenience methods defined below. Construct via a
    `from_XXX` classmethod (e.g. `from_hdf5`) rather than the bare
    constructor when loading from storage.
    """

    @classmethod
    def from_hdf5(cls, path: str) -> Recording:
        """Load a Recording from a PyTables-style HDF5 file.

        See ICOschema.storage.python.hdf5 for the accepted file layout and
        the legacy/versioned format dispatch. Oblivious to any
        `/computations/` group the file may also contain -- use
        ICOschema.DatasetBundle.from_hdf5() to read those too.
        """
        from icoschema.storage.python import hdf5

        loaded = hdf5.load_recording(path)
        return cls(
            hardware_metadata=loaded.hardware_metadata,
            recording_metadata=loaded.recording_metadata,
            recording_data=loaded.recording_data,
        )

    def to_hdf5(self, path: str) -> None:
        """Write this recording to a fresh HDF5 file in the current format.

        See ICOschema.storage.python.hdf5 for the file layout this
        produces.
        """
        from icoschema.storage.python import hdf5

        hdf5.save_recording(self, path)

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
        """recording_data.counter as a numpy array (an 8-bit wrapping packet counter)."""
        return np.asarray(self.recording_data.counter, dtype=int)

    @property
    def channel_count(self) -> int:
        """Number of channels present (non-empty) in this recording."""
        return sum(getattr(self, name).size > 0 for name in ("channel1", "channel2", "channel3"))

    @property
    def signal_loss_percentage(self) -> float:
        """Percentage of packets lost, inferred from gaps/wraparounds in `counter`.


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
        position `j`. Raises like `rows_per_packet()`.
        """
        counter = self.counter
        lost_rows = _lost_packets(counter) * self.rows_per_packet()
        return np.arange(counter.size, dtype=np.int64) + np.concatenate(([0], np.cumsum(lost_rows))).astype(np.int64)

    def filled_mask(self) -> np.ndarray:
        """Boolean mask over the gap-free grid: `True` at positions no row was
        received for (lost packets), `False` at received rows."""
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
        """
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

    def channel_sampling_frequency(self) -> tuple[float, Literal["hardware", "default"]]:
        """The per-channel sampling frequency in Hz -- `total_sampling_frequency()`
        divided by `channel_count` -- and where it came from. Raises
        `ValueError` for a recording without channels."""
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
            "sample_count": len(self.counter),
            "signal_loss_percentage": float(self.signal_loss_percentage),
            "channels": channels,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """recording_data as a DataFrame (columns: timestamp, counter, channel1, and channel2/channel3 if present).

        Values are raw and uncompensated -- see the module docstring's note
        on Compensation/Conversion.
        """
        data = self.recording_data
        columns = {
            "timestamp": data.timestamp,
            "counter": data.counter,
            "channel1": data.channel1,
        }
        if data.channel2:
            columns["channel2"] = data.channel2
        if data.channel3:
            columns["channel3"] = data.channel3
        return pd.DataFrame(columns)
