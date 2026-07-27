"""ICOschema: a backend-agnostic data model for sensor/hardware recordings
and their derived computations.

    from ICOschema import Recording, DatasetBundle

    recording = Recording.from_hdf5("some_file.hdf5")
    df = recording.to_dataframe()

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
    bundle.to_hdf5("some_file.hdf5")

See ICOschema.model.python.recording.Recording and
ICOschema.model.python.dataset_bundle.DatasetBundle for the full API.
`DerivedDataset` is a component type with no behavior beyond what's
generated (see ICOschema.schema.generated.python.dataset.DerivedDataset).
"""

from ICOschema.model.python.dataset_bundle import DatasetBundle
from ICOschema.model.python.recording import Recording
from ICOschema.schema.generated.python.dataset import DerivedDataset

__all__ = ["DatasetBundle", "DerivedDataset", "Recording"]
