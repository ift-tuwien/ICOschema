"""The `icoschema.v1` namespace: the whole public API of the current schema version, and the top-level package
as an alias of it."""

import inspect

import pytest
from synthetic_files import DATA_DIR, hdf5_name, signal

import icoschema
from icoschema import v1
from icoschema.model.python import (
    dataset_bundle,
    preprocessed_recording,
    recording,
    source,
)
from icoschema.schema.generated.python import dataset as generated


def test_the_top_level_names_are_the_v1_objects() -> None:
    for name in icoschema.__all__:
        if name != "v1":
            assert getattr(icoschema, name) is getattr(v1, name), name
    assert icoschema.v1 is v1


def test_everything_in_all_exists() -> None:
    for name in v1.__all__:
        assert hasattr(v1, name), name


def test_model_classes_are_the_ones_with_behaviour() -> None:
    assert v1.Source is source.Source
    assert v1.Recording is recording.Recording
    assert v1.DatasetBundle is dataset_bundle.DatasetBundle
    assert v1.PreprocessedRecording is preprocessed_recording.PreprocessedRecording
    assert issubclass(
        v1.Source, generated.Source
    )  # ... and still a generated schema class


def test_every_schema_class_is_available_from_v1() -> None:
    """A schema class added to dataset.yaml must be exposed (or explicitly left out here)."""
    classes = {
        name
        for name, obj in inspect.getmembers(generated, inspect.isclass)
        if obj.__module__ == generated.__name__
        and issubclass(obj, (generated.YAMLRoot, generated.EnumDefinitionImpl))
        and obj not in (generated.YAMLRoot, generated.EnumDefinitionImpl)
    }
    left_out = {"slots"}  # generated plumbing, not schema classes
    assert classes - left_out <= set(v1.__all__), sorted(
        classes - left_out - set(v1.__all__)
    )


def test_a_consumer_can_build_write_and_read_with_v1_only(tmp_path) -> None:
    channel = v1.ChannelMetadata(
        sensor=v1.Sensor(name="s", unit="g"), compensations=[v1.NoConversion(order=0)]
    )
    values = signal(1)
    bundle = v1.DatasetBundle(
        recording=v1.Recording(
            sources=[
                v1.Source(
                    name="source1",
                    hardware_metadata=v1.HardwareMetadata(channel1_metadata=channel),
                    recording_metadata=v1.RecordingMetadata(
                        start_time="2026-03-04T05:06:07"
                    ),
                    recording_data=v1.RecordingData(
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
    again = v1.DatasetBundle.from_hdf5(path)
    assert isinstance(again, v1.DatasetBundle)
    assert again.recording.only_source().recording_data.channel1 == values


def test_v1_reads_a_stored_file_with_its_format_versions() -> None:
    assert "1.2" in v1.hdf5_format_versions(writable=True)
    stored = v1.DatasetBundle.from_hdf5(str(DATA_DIR / hdf5_name("1.2", 3)))
    assert isinstance(stored.recording, v1.Recording)
    assert [str(step.node) for step in stored.steps] == ["rms"]


def test_v1_does_not_leak_storage_internals() -> None:
    public = {name for name in dir(v1) if not name.startswith("_")}
    assert not any(name in public for name in ("hdf5", "tdms", "h5py", "np", "pd"))
    with pytest.raises(AttributeError):
        v1.save_dataset_bundle  # noqa: B018
