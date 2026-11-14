"""Schema version 2: the complete public API of this schema version.

    from icoschema import v2

    recording = v2.Recording(sources=[v2.Source(...)])
    bundle = v2.DatasetBundle(recording=recording)
    bundle.to_hdf5("some_file.hdf5", format_version="2.0")

Pin the schema version by importing it from here rather than from the top-level `icoschema`, which is an
alias of the latest schema version. A newer schema version is a package of its own next to this one, with the
same layout, so code importing `icoschema.v2` keeps the classes, and the type checking, it was written against.

This package is self-contained: everything in it imports from the rest of the package only relatively (the one
exception is the version-neutral `icoschema._version`), so that the next schema version starts as a copy of it.
The names here are the objects defined in its submodules, not copies. The file format versions
(`hdf5_format_versions()`, `FormatVersion`) are those of the HDF5 layouts this schema version can be stored in.
"""

from .model.attachments import EmbeddedFile, EmbeddedFileInfo
from .model.dataset_bundle import DatasetBundle
from .model.preprocessed_recording import PreprocessedRecording
from .model.recording import Recording
from .model.source import Source
from .schema.generated.dataset import (
    ChannelMetadata,
    ComputationStatus,
    ComputationStep,
    Conversion,
    DerivedDataset,
    HardwareMetadata,
    LinearConversion,
    NoConversion,
    Provenance,
    QualityChannel,
    RecordingData,
    RecordingMetadata,
    SamplingFrequencySource,
    Sensor,
)
from .storage import attachments
from .storage.hdf5 import (
    FormatVersion,
    readable_versions,
    writable_versions,
)
from .storage.writer import BundleWriter, SourceSpec, SourceWriter


def hdf5_format_versions(*, writable: bool = False) -> tuple[str, ...]:
    """The HDF5 file format versions this package reads ("legacy" is the unversioned layout), or with
    `writable=True` the ones `to_hdf5(format_version=...)` can write."""
    return writable_versions() if writable else readable_versions()


__all__ = [
    "BundleWriter",
    "ChannelMetadata",
    "ComputationStatus",
    "ComputationStep",
    "Conversion",
    "DatasetBundle",
    "DerivedDataset",
    "EmbeddedFile",
    "EmbeddedFileInfo",
    "FormatVersion",
    "HardwareMetadata",
    "LinearConversion",
    "NoConversion",
    "PreprocessedRecording",
    "Provenance",
    "QualityChannel",
    "Recording",
    "RecordingData",
    "RecordingMetadata",
    "SamplingFrequencySource",
    "Sensor",
    "Source",
    "SourceSpec",
    "SourceWriter",
    "attachments",
    "hdf5_format_versions",
]
