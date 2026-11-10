"""ICOschema: a backend-agnostic data model for sensor/hardware recordings
and their derived computations.

    from icoschema import Recording, DatasetBundle

    recording = Recording.from_hdf5("some_file.hdf5")
    df = recording.to_dataframe()

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
    bundle.to_hdf5("some_file.hdf5")                          # the oldest file format version that fits
    bundle.to_hdf5("some_file.hdf5", format_version="1.2")    # or a chosen one (see hdf5_format_versions())

See ICOschema.model.python.recording.Recording and
ICOschema.model.python.dataset_bundle.DatasetBundle for the full API.
`DerivedDataset` is a component type with no behavior beyond what's
generated (see ICOschema.schema.generated.python.dataset.DerivedDataset).
"""

from icoschema.model.python.dataset_bundle import DatasetBundle
from icoschema.model.python.preprocessed_recording import PreprocessedRecording
from icoschema.model.python.recording import Recording
from icoschema.schema.generated.python.dataset import ComputationStep, DerivedDataset
from icoschema.storage.python.hdf5 import (
    FormatVersion,
    readable_versions,
    writable_versions,
)


def hdf5_format_versions(*, writable: bool = False) -> tuple[str, ...]:
    """The HDF5 file format versions this package reads ("legacy" is the unversioned layout), or with
    `writable=True` the ones `to_hdf5(format_version=...)` can write."""
    return writable_versions() if writable else readable_versions()


__all__ = [
    "ComputationStep",
    "DatasetBundle",
    "DerivedDataset",
    "FormatVersion",
    "PreprocessedRecording",
    "Recording",
    "hdf5_format_versions",
]
