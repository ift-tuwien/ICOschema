"""The public API of this repository: a `Recording` that inherits all
fields from the generated `dataset.Recording` (see
ICOschema/schema/generated/python) and adds a few things that aren't
auto-generated: loading from / writing to a specific storage backend, and
convenient access to its sources.

A recording has one or more independent `Source`s (one per STU/STH
combination), each with its own clock, counter, ADC settings and sensors.
The per-source data and calculations (numpy getters, signal loss, gap-free
grid, sampling frequency, DataFrame) live on `Source`
(see ICOschema.model.python.source). For the very common recording with a
single source, `Recording` forwards them, so `recording.channel1` and
`Recording(hardware_metadata=..., recording_metadata=..., recording_data=...)`
keep working; with several sources they raise a `ValueError` that names the
sources, and you pick one via `recording.sources["name"]`.

This file should never be imported directly, but rather only from the main
entrypoint:

    from icoschema import Recording

    recording = Recording.from_hdf5("some_file.hdf5")
    df = recording.to_dataframe()

ICOschema.schema.generated (plain data, no behavior) and ICOschema.storage
(storage-format-specific I/O) are internal implementation details of this
module and should not be imported directly by other codebases.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Literal, cast

import numpy as np
import pandas as pd

from icoschema.model.python.source import ADC_CLOCK_HZ, DEFAULT_ADC_SETTINGS, Source
from icoschema.schema.generated.python import dataset as generated

__all__ = ["ADC_CLOCK_HZ", "DEFAULT_ADC_SETTINGS", "DEFAULT_SOURCE_NAME", "Recording", "Source"]

# Name of the source of a recording that was created or read without naming
# one (single-source files don't store a name unless they were written with
# one).
DEFAULT_SOURCE_NAME = "source1"

_LEGACY_FIELDS = ("hardware_metadata", "recording_metadata", "recording_data")


class Recording(generated.Recording):
    """A complete recording: one or more independent `Source`s.

    Has every field of `ICOschema.schema.generated.python.dataset.Recording`
    (`sources`, a dict keyed by source name), plus the loading/writing and
    convenience methods defined below. Construct via a `from_XXX` classmethod
    (e.g. `from_hdf5`) rather than the bare constructor when loading from
    storage.

    For compatibility, `Recording(hardware_metadata=..., recording_metadata=...,
    recording_data=...)` creates a recording with one source named
    `DEFAULT_SOURCE_NAME`, and those three fields read back from a
    single-source recording.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        legacy = {name: kwargs.pop(name) for name in _LEGACY_FIELDS if name in kwargs}
        if legacy:
            if args or "sources" in kwargs:
                raise TypeError("pass either `sources` or hardware_metadata/recording_metadata/recording_data, not both")
            missing = [name for name in _LEGACY_FIELDS if name not in legacy]
            if missing:
                raise TypeError(f"missing {missing}: a single-source Recording needs all of {list(_LEGACY_FIELDS)}")
            kwargs["sources"] = [Source(name=DEFAULT_SOURCE_NAME, **legacy)]
        super().__init__(*args, **kwargs)

    def __post_init__(self, *args: Any, **kwargs: Any) -> None:
        super().__post_init__(*args, **kwargs)
        # Always hold model `Source`s, even when given generated ones.
        for name, source in list(self.sources.items()):
            if not isinstance(source, Source):
                self.sources[name] = Source(**{f.name: getattr(source, f.name) for f in dataclasses.fields(source)})

    @classmethod
    def from_hdf5(cls, path: str) -> Recording:
        """Load a Recording from a PyTables-style HDF5 file.

        See ICOschema.storage.python.hdf5 for the accepted file layout and
        the legacy/versioned format dispatch. Oblivious to any
        `/computations/` group the file may also contain -- use
        ICOschema.DatasetBundle.from_hdf5() to read those too.
        """
        from icoschema.storage.python import hdf5

        return cls(sources=list(hdf5.load_recording(path).sources.values()))

    def to_hdf5(self, path: str) -> None:
        """Write this recording to a fresh HDF5 file in the current format.

        See ICOschema.storage.python.hdf5 for the file layout this
        produces.
        """
        from icoschema.storage.python import hdf5

        hdf5.save_recording(self, path)

    # ── sources ────────────────────────────────────────────────────────────

    def source_list(self) -> list[Source]:
        """The sources, in insertion order."""
        return cast(list[Source], list(self.sources.values()))

    def only_source(self) -> Source:
        """The one source of a single-source recording. Raises `ValueError`
        naming the sources if there are several."""
        sources = self.source_list()
        if len(sources) != 1:
            raise ValueError(
                f"recording has {len(sources)} sources ({[str(s.name) for s in sources]}); "
                "pick one via recording.sources['name']"
            )
        return sources[0]

    # Single-source shortcuts: the three fields of the one source...

    @property
    def hardware_metadata(self) -> generated.HardwareMetadata:
        """The hardware metadata of the only source."""
        return self.only_source().hardware_metadata

    @property
    def recording_metadata(self) -> generated.RecordingMetadata:
        """The recording metadata of the only source."""
        return self.only_source().recording_metadata

    @property
    def recording_data(self) -> generated.RecordingData:
        """The recording data of the only source."""
        return self.only_source().recording_data

    # ...and what `Source` calculates from them.

    @property
    def timestamps(self) -> np.ndarray:
        """`Source.timestamps` of the only source."""
        return self.only_source().timestamps

    @property
    def channel1(self) -> np.ndarray:
        """`Source.channel1` of the only source."""
        return self.only_source().channel1

    @property
    def channel2(self) -> np.ndarray:
        """`Source.channel2` of the only source."""
        return self.only_source().channel2

    @property
    def channel3(self) -> np.ndarray:
        """`Source.channel3` of the only source."""
        return self.only_source().channel3

    @property
    def counter(self) -> np.ndarray:
        """`Source.counter` of the only source."""
        return self.only_source().counter

    @property
    def channel_count(self) -> int:
        """`Source.channel_count` of the only source."""
        return self.only_source().channel_count

    @property
    def signal_loss_percentage(self) -> float:
        """`Source.signal_loss_percentage` of the only source."""
        return self.only_source().signal_loss_percentage

    def rows_per_packet(self) -> int:
        """`Source.rows_per_packet()` of the only source."""
        return self.only_source().rows_per_packet()

    def sample_index(self) -> np.ndarray:
        """`Source.sample_index()` of the only source."""
        return self.only_source().sample_index()

    def filled_mask(self) -> np.ndarray:
        """`Source.filled_mask()` of the only source."""
        return self.only_source().filled_mask()

    def total_sampling_frequency(self) -> tuple[float, Literal["hardware", "default"]]:
        """`Source.total_sampling_frequency()` of the only source."""
        return self.only_source().total_sampling_frequency()

    def channel_sampling_frequency(self) -> tuple[float, Literal["hardware", "default"]]:
        """`Source.channel_sampling_frequency()` of the only source."""
        return self.only_source().channel_sampling_frequency()

    def summary(self) -> dict[str, Any]:
        """A compact, JSON-encodable summary of this recording.

        A single-source recording returns that source's `Source.summary()`
        (`start_time`, `sample_count`, `signal_loss_percentage`,
        `channels`). With several sources it returns
        `{"sources": {name: {"stu_id", "sth_id", **Source.summary()}}}`.
        Every value is a plain `str`/`int`/`float`/`None`, so
        `json.dumps(recording.summary())` always succeeds.
        """
        sources = self.source_list()
        if len(sources) == 1:
            return sources[0].summary()
        return {
            "sources": {
                str(source.name): {"stu_id": source.stu_id, "sth_id": source.sth_id, **source.summary()}
                for source in sources
            }
        }

    def to_dataframe(self, source: str | None = None) -> pd.DataFrame:
        """`Source.to_dataframe()` of `source`, or of the only source if
        none is named. Raises `ValueError` if several sources exist and none
        is named."""
        if source is None:
            return self.only_source().to_dataframe()
        return cast(Source, self.sources[source]).to_dataframe()
