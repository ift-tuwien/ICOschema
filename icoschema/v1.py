"""Schema version 1: the complete public API of the current schema.

    from icoschema import v1

    recording = v1.Recording(sources=[v1.Source(...)])
    bundle = v1.DatasetBundle(recording=recording)
    bundle.to_hdf5("some_file.hdf5", format_version="1.2")

Pin the schema version by importing it from here rather than from the top-level `icoschema`, which is an
alias of the latest schema version (today this one). A future schema version gets its own module next to this
one with the same layout, so that code importing `icoschema.v1` keeps the classes, and the type checking, it
was written against.

Everything here is the object defined elsewhere in the package, not a copy: `icoschema.Recording is
icoschema.v1.Recording`. The file format versions (`hdf5_format_versions()`, `FormatVersion`) are those of
the HDF5 layouts this schema version can be stored in.
"""

from icoschema.model.python.dataset_bundle import DatasetBundle
from icoschema.model.python.preprocessed_recording import PreprocessedRecording
from icoschema.model.python.recording import Recording
from icoschema.model.python.source import Source
from icoschema.schema.generated.python.dataset import (
    ChannelMetadata,
    Compensation,
    ComputationStatus,
    ComputationStep,
    Conversion,
    DerivedDataset,
    FrequencyCompensation,
    HardwareMetadata,
    LinearConversion,
    NoConversion,
    PolynomialConversion,
    Provenance,
    QualityChannel,
    RecordingData,
    RecordingMetadata,
    SamplingFrequencySource,
    Sensor,
)
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
    "ChannelMetadata",
    "Compensation",
    "ComputationStatus",
    "ComputationStep",
    "Conversion",
    "DatasetBundle",
    "DerivedDataset",
    "FormatVersion",
    "FrequencyCompensation",
    "HardwareMetadata",
    "LinearConversion",
    "NoConversion",
    "PolynomialConversion",
    "PreprocessedRecording",
    "Provenance",
    "QualityChannel",
    "Recording",
    "RecordingData",
    "RecordingMetadata",
    "SamplingFrequencySource",
    "Sensor",
    "Source",
    "hdf5_format_versions",
]
