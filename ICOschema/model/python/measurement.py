"""The public API of this repository: a `Measurement` that inherits all
fields from the generated `measurement.Measurement` (see
ICOschema/schema/generated/python) and adds a few things that aren't
auto-generated: loading from a specific storage backend, converting to a
pandas DataFrame, and quick pass-through getters for the raw arrays
(timestamps, channel1/2/3), as numpy arrays, that plotting code typically
wants directly instead of going through measurement_data or a DataFrame.

Other codebases should only ever import from here, e.g.:

    from ICOschema.model.python.measurement import Measurement
    measurement = Measurement.from_hdf5("some_file.hdf5")
    df = measurement.to_dataframe()
    plt.plot(measurement.timestamps, measurement.channel1)

ICOschema.schema.generated (plain data, no behavior) and ICOschema.storage
(storage-format-specific I/O) are internal implementation details of this
module and should not be imported directly by other codebases.

Note: Compensation/Conversion (on HardwareMetadata.channelN_metadata) is
purely descriptive of what has already been applied to a channel's raw
MeasurementData values -- it is not applied by this class, or by anything
else here.
"""

from __future__ import annotations

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
