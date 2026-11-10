"""ICOschema: a backend-agnostic data model for sensor/hardware recordings
and their derived computations.

    from icoschema import Recording, DatasetBundle

    recording = Recording.from_hdf5("some_file.hdf5")
    df = recording.to_dataframe()

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
    bundle.to_hdf5("some_file.hdf5")                          # the oldest file format version that fits
    bundle.to_hdf5("some_file.hdf5", format_version="1.2")    # or a chosen one (see hdf5_format_versions())

These names are those of the latest schema version (`icoschema._schemas.LATEST`, today `icoschema.v1`). To stay
on a schema version, import from it (`from icoschema import v1`; `v1.Recording`, `v1.Source`, `v1.Sensor`, ...):
each has the complete API, and old versions stay as they were.

See icoschema.v1.model.recording.Recording and icoschema.v1.model.dataset_bundle.DatasetBundle for the full API.
`DerivedDataset` is a component type with no behavior beyond what's generated (see
icoschema.v1.schema.generated.dataset.DerivedDataset).

The latest schema version is named in exactly two places: the second import below, and `LATEST` in
`icoschema/_schemas.py`. See doc/adding-a-schema-version.md.
"""

# Every schema version is importable from here: add `v2` to this import when there is one.
from icoschema import v1

# The latest schema version is the one whose names are imported here (and `LATEST` in _schemas.py).
from icoschema.v1 import (
    ComputationStep,
    DatasetBundle,
    DerivedDataset,
    FormatVersion,
    PreprocessedRecording,
    Recording,
    hdf5_format_versions,
)

__all__ = [
    "ComputationStep",
    "DatasetBundle",
    "DerivedDataset",
    "FormatVersion",
    "PreprocessedRecording",
    "Recording",
    "hdf5_format_versions",
    "v1",
]
