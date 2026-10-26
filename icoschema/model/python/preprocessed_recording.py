"""The public API for a `PreprocessedRecording`: a `Recording`'s channels
on the gap-free sample grid (lost packets filled) with timestamps rebased to
1 / sampling frequency (see ICOschema/schema/generated/python). Adds numpy
getters and a DataFrame view on top of the generated fields.

This file should never be imported directly, but rather only via a
`DatasetBundle`:

    from icoschema import DatasetBundle

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    if bundle.preprocessed is not None:
        df = bundle.preprocessed.to_dataframe()

The channels mean exactly what the raw `Recording` channels mean: they share
its `HardwareMetadata` (sensors and compensations) and are never converted
on the way. Producing the table (filling, rebasing) is up to the producer
named in `producer`; this class only holds and validates it (see
`DatasetBundle.with_preprocessed`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from icoschema.schema.generated.python import dataset as generated


class PreprocessedRecording(generated.PreprocessedRecording):
    """A recording's channels on the gap-free grid with rebased timestamps.

    Has every field of
    `ICOschema.schema.generated.python.dataset.PreprocessedRecording`, plus
    the getters below. Row `j` is grid position `j` of the raw recording
    (see `Recording.sample_index()`).
    """

    @property
    def timestamps(self) -> np.ndarray:
        """`timestamp` as a numpy array (integer microseconds since recording_metadata.start_time)."""
        return np.asarray(self.timestamp, dtype=np.int64)

    @property
    def channel1_values(self) -> np.ndarray:
        """`channel1` as a numpy array. Always present."""
        return np.asarray(self.channel1)

    @property
    def channel2_values(self) -> np.ndarray:
        """`channel2` as a numpy array. Empty if the recording has no second channel."""
        return np.asarray(self.channel2)

    @property
    def channel3_values(self) -> np.ndarray:
        """`channel3` as a numpy array. Empty if the recording has no third channel."""
        return np.asarray(self.channel3)

    @property
    def channel_count(self) -> int:
        """Number of channels present (non-empty)."""
        return sum(len(getattr(self, name)) > 0 for name in ("channel1", "channel2", "channel3"))

    def __len__(self) -> int:
        return len(self.timestamp)

    def to_dataframe(self) -> pd.DataFrame:
        """The table as a DataFrame (columns: timestamp, channel1, and
        channel2/channel3 if present). Values are not converted -- see the
        module docstring."""
        columns = {"timestamp": self.timestamp, "channel1": self.channel1}
        if self.channel2:
            columns["channel2"] = self.channel2
        if self.channel3:
            columns["channel3"] = self.channel3
        return pd.DataFrame(columns)
