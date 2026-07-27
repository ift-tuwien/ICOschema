"""The public API for a `DatasetBundle`: a `Recording` together with every
`DerivedDataset` computed from it (see ICOschema/schema/generated/python).
Adds loading from / writing to storage and immutable-update helpers on top
of the generated fields (`recording`, `computations`).

This file should never be imported directly, but rather only from the main
entrypoint:

    from ICOschema import DatasetBundle

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
    bundle.to_hdf5("some_file.hdf5")

`DerivedDataset` itself has no model-layer wrapper -- like `Sensor` or
`ChannelMetadata`, it's a component type with no behavior beyond what's
generated, used directly via
`ICOschema.schema.generated.python.dataset.DerivedDataset`.
"""

from __future__ import annotations

from typing import Literal

from ICOschema.model.python.recording import Recording
from ICOschema.schema.generated.python import dataset as generated
from ICOschema.schema.generated.python.dataset import DerivedDataset


class DatasetBundle(generated.DatasetBundle):
    """A Recording together with every DerivedDataset computed from it.

    Has every field of `ICOschema.schema.generated.python.dataset.DatasetBundle`
    (`recording`, `computations`), plus the loading/writing and
    immutable-update methods defined below. Construct via a `from_XXX`
    classmethod (e.g. `from_hdf5`) rather than the bare constructor when
    loading from storage.
    """

    @classmethod
    def from_hdf5(cls, path: str, *, on_error: Literal["skip", "raise"] = "skip") -> DatasetBundle:
        """Load a DatasetBundle from an HDF5 file.

        Always succeeds -- `computations` is empty if the file has none.
        A malformed computation entry is logged and skipped by default;
        pass `on_error="raise"` to fail the whole read instead. See
        ICOschema.storage.python.hdf5 for the accepted file layout.
        """
        from ICOschema.storage.python import hdf5

        loaded = hdf5.load_dataset_bundle(path, on_error=on_error)
        return cls(
            recording=Recording(
                hardware_metadata=loaded.recording.hardware_metadata,
                recording_metadata=loaded.recording.recording_metadata,
                recording_data=loaded.recording.recording_data,
            ),
            computations=dict(loaded.computations),
        )

    def to_hdf5(self, path: str) -> None:
        """Write this bundle (recording + every computation) to a fresh HDF5 file.

        See ICOschema.storage.python.hdf5 for the file layout this
        produces -- each computation is stored in its true N-D shape under
        a `/computations/` group.
        """
        from ICOschema.storage.python import hdf5

        hdf5.save_dataset_bundle(self, path)

    def with_recording(self, recording: Recording) -> DatasetBundle:
        """A copy of this bundle with `recording` replaced (e.g. after dataloss-fill)."""
        return DatasetBundle(recording=recording, computations=dict(self.computations))

    def with_computation(self, key: str, derived: DerivedDataset) -> DatasetBundle:
        """A copy of this bundle with one computation added/replaced under `key`."""
        computations = dict(self.computations)
        computations[key] = derived
        return DatasetBundle(recording=self.recording, computations=computations)
