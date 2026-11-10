"""ICOschema: a backend-agnostic data model for sensor/hardware recordings
and their derived computations.

    from icoschema import Recording, DatasetBundle

    recording = Recording.from_hdf5("some_file.hdf5")
    df = recording.to_dataframe()

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
    bundle.to_hdf5("some_file.hdf5")                          # the oldest file format version that fits
    bundle.to_hdf5("some_file.hdf5", format_version="1.2")    # or a chosen one (see hdf5_format_versions())

These names are those of the latest schema version, today `icoschema.v1`. To stay on a schema version, import
from it (`from icoschema import v1`; `v1.Recording`, `v1.Source`, `v1.Sensor`, ...): it has the complete API.

See ICOschema.model.python.recording.Recording and
ICOschema.model.python.dataset_bundle.DatasetBundle for the full API.
`DerivedDataset` is a component type with no behavior beyond what's
generated (see ICOschema.schema.generated.python.dataset.DerivedDataset).
"""

from icoschema import v1
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
