"""The namespace of this schema version (`icoschema.v1`, imported as `api`): its whole public API.

This file is version-neutral on purpose: the copy of this directory for the next schema version only needs its
`api` import changed (scripts/new_schema_version.py does it)."""

import inspect

import pytest

from icoschema import v1 as api
from icoschema.v1.model import (
    dataset_bundle,
    preprocessed_recording,
    recording,
    source,
)
from icoschema.v1.schema.generated import dataset as generated

from .synthetic_files import DATA_DIR, hdf5_name, signal


def test_everything_in_all_exists() -> None:
    for name in api.__all__:
        assert hasattr(api, name), name


def test_model_classes_are_the_ones_with_behaviour() -> None:
    assert api.Source is source.Source
    assert api.Recording is recording.Recording
    assert api.DatasetBundle is dataset_bundle.DatasetBundle
    assert api.PreprocessedRecording is preprocessed_recording.PreprocessedRecording
    assert issubclass(
        api.Source, generated.Source
    )  # ... and still a generated schema class


def test_every_schema_class_is_available_from_the_namespace() -> None:
    """A schema class added to dataset.yaml must be exposed (or explicitly left out here)."""
    classes = {
        name
        for name, obj in inspect.getmembers(generated, inspect.isclass)
        if obj.__module__ == generated.__name__
        and issubclass(obj, (generated.YAMLRoot, generated.EnumDefinitionImpl))
        and obj not in (generated.YAMLRoot, generated.EnumDefinitionImpl)
    }
    left_out = {"slots"}  # generated plumbing, not schema classes
    assert classes - left_out <= set(api.__all__), sorted(
        classes - left_out - set(api.__all__)
    )


def test_a_consumer_can_build_write_and_read_with_the_namespace_only(tmp_path) -> None:
    channel = api.ChannelMetadata(
        sensor=api.Sensor(name="s", unit="g"), compensations=[api.NoConversion(order=0)]
    )
    values = signal(1)
    bundle = api.DatasetBundle(
        recording=api.Recording(
            sources=[
                api.Source(
                    name="source1",
                    hardware_metadata=api.HardwareMetadata(channel1_metadata=channel),
                    recording_metadata=api.RecordingMetadata(
                        start_time="2026-03-04T05:06:07"
                    ),
                    recording_data=api.RecordingData(
                        timestamp=list(range(0, 1000 * len(values), 1000)),
                        counter=[i % 256 for i in range(len(values))],
                        channel1=values,
                    ),
                )
            ]
        )
    )
    path = str(tmp_path / "f.hdf5")
    bundle.to_hdf5(path, format_version="1.2")
    again = api.DatasetBundle.from_hdf5(path)
    assert isinstance(again, api.DatasetBundle)
    assert again.recording.only_source().recording_data.channel1 == values


def test_the_namespace_reads_a_stored_file_with_its_format_versions() -> None:
    assert "1.2" in api.hdf5_format_versions(writable=True)
    stored = api.DatasetBundle.from_hdf5(str(DATA_DIR / hdf5_name("1.2", 3)))
    assert isinstance(stored.recording, api.Recording)
    assert [str(step.node) for step in stored.steps] == ["rms"]


def test_the_namespace_does_not_leak_storage_internals() -> None:
    public = {name for name in dir(api) if not name.startswith("_")}
    assert not any(name in public for name in ("hdf5", "tdms", "h5py", "np", "pd"))
    with pytest.raises(AttributeError):
        api.save_dataset_bundle  # noqa: B018
