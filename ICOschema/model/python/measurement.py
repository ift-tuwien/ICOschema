"""The public API of this repository: a `Measurement` that inherits all
fields from the generated `measurement.Measurement` (see
ICOschema/schema/generated/python) and adds a few things that aren't
auto-generated: loading from a specific storage backend, converting to a
pandas DataFrame, quick pass-through getters for the raw arrays (timestamps,
counter, channel1/2/3), as numpy arrays, that plotting code typically wants
directly instead of going through measurement_data or a DataFrame,
signal_loss_percentage, and a JSON-encodable summary() of the whole
measurement.

This file should never be imported directly, but rather only from the main
entrypoint:

    from ICOschema import Measurement

    measurement = Measurement.from_hdf5("some_file.hdf5")
    df = measurement.to_dataframe()

ICOschema.schema.generated (plain data, no behavior) and ICOschema.storage
(storage-format-specific I/O) are internal implementation details of this
module and should not be imported directly by other codebases.

Note: Compensation/Conversion (on HardwareMetadata.channelN_metadata) is
purely descriptive of what has already been applied to a channel's raw
MeasurementData values -- it is not applied by this class, or by anything
else here.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from ICOschema.schema.generated.python import measurement as generated


class Measurement(generated.Measurement):
    """A complete measurement: hardware/sensor metadata plus its sample data.

    Has every field of `ICOschema.schema.generated.python.measurement.Measurement`
    (`hardware_metadata`, `measurement_metadata`, `measurement_data`), plus the
    loading and convenience methods defined below. Construct via a `from_XXX`
    classmethod (e.g. `from_hdf5`) rather than the bare constructor.
    """

    @classmethod
    def from_hdf5(cls, path: str) -> Measurement:
        """Load a Measurement from a PyTables-style HDF5 file.

        See ICOschema.storage.python.hdf5 for the accepted file layout and
        the legacy/versioned format dispatch.
        """
        from ICOschema.storage.python import hdf5

        loaded = hdf5.load_measurement(path)
        return cls(
            hardware_metadata=loaded.hardware_metadata,
            measurement_metadata=loaded.measurement_metadata,
            measurement_data=loaded.measurement_data,
        )

    @property
    def timestamps(self) -> np.ndarray:
        """measurement_data.timestamp as a numpy array (integer microseconds since measurement_metadata.start_time)."""
        return np.asarray(self.measurement_data.timestamp)

    @property
    def channel1(self) -> np.ndarray:
        """measurement_data.channel1 as a numpy array. Always present."""
        return np.asarray(self.measurement_data.channel1)

    @property
    def channel2(self) -> np.ndarray:
        """measurement_data.channel2 as a numpy array. Empty if this measurement has no second channel."""
        return np.asarray(self.measurement_data.channel2)

    @property
    def channel3(self) -> np.ndarray:
        """measurement_data.channel3 as a numpy array. Empty if this measurement has no third channel."""
        return np.asarray(self.measurement_data.channel3)

    @property
    def counter(self) -> np.ndarray:
        """measurement_data.counter as a numpy array (an 8-bit wrapping packet counter)."""
        return np.asarray(self.measurement_data.counter, dtype=int)

    @property
    def signal_loss_percentage(self) -> float:
        """Percentage of packets lost, inferred from gaps/wraparounds in `counter`.


        `counter` is an 8-bit counter (wraps 255 -> 0) that increments once per
        packet; a jump of more than 1 between consecutive samples (accounting
        for wraparound) means packets were dropped in between.
        """
        counter = self.counter
        gaps = np.diff(counter) - 1
        gaps[gaps == -1] = 0  # counter repeated (no increment)
        gaps[gaps == -256] = 0  # clean wraparound 255 -> 0
        gaps[gaps < 0] += 256  # wraparound with loss
        total_lost = int(np.sum(gaps))
        total_received = len(counter)
        return (total_lost / (total_received + total_lost)) * 100

    def summary(self) -> dict[str, Any]:
        """A compact, JSON-encodable summary of this measurement.

        Every value is a plain `str`/`int`/`float`/`None` (never a numpy
        scalar or array) so `json.dumps(measurement.summary())` always
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
            "start_time": self.measurement_metadata.start_time,
            "sample_count": int(len(self.counter)),
            "signal_loss_percentage": float(self.signal_loss_percentage),
            "channels": channels,
        }

    def to_dataframe(self) -> pd.DataFrame:
        """measurement_data as a DataFrame (columns: timestamp, counter, channel1, and channel2/channel3 if present).

        Values are raw and uncompensated -- see the module docstring's note
        on Compensation/Conversion.
        """
        data = self.measurement_data
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
