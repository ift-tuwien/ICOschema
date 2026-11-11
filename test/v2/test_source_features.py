"""Sources without a counter, with their own rate, quality or additional data, the description and MAC
addresses of a source, provenance and the start-offset accessors."""

from pathlib import Path

import h5py
import pytest

from icoschema.v2 import DatasetBundle
from icoschema.v2.model.recording import Recording, Source
from icoschema.v2.schema.generated import dataset as generated

FIXTURE = str(Path(__file__).resolve().parent / "test_with_sensors.hdf5")


def _source(name: str, start: str | None, counter: list[int] | None = None, **extra) -> Source:
    channel = generated.ChannelMetadata(sensor=generated.Sensor(), conversion=generated.NoConversion())
    n = 4
    return Source(
        name=name,
        hardware_metadata=generated.HardwareMetadata(channel1_metadata=channel),
        recording_metadata=generated.RecordingMetadata(start_time=start),
        recording_data=generated.RecordingData(
            timestamp=[i * 100 for i in range(n)], counter=counter or [], channel1=[float(i) for i in range(n)]
        ),
        **extra,
    )


def test_a_plain_packet_recording_is_written_as_2_0_with_nothing_claimed_about_its_origin(tmp_path):
    bundle = DatasetBundle(recording=Recording(sources=[_source("source1", "2026-01-01T00:00:00", [0, 1, 2, 3])]))
    bundle.to_hdf5(str(tmp_path / "a.hdf5"))
    with h5py.File(tmp_path / "a.hdf5") as f:
        assert f.attrs["icoschema_format_version"] == "2.0"
        assert f["recording"].attrs["source_name"] == "source1"  # a single source's name is always stored
        assert f.attrs["writer"].startswith("icoschema")
        assert "source_format" not in f.attrs  # nothing is claimed about where an in-memory bundle came from


@pytest.mark.parametrize("extra", [{"sampling_frequency": 1000.0}, {"additional_data": "{}"}, {}])
def test_every_optional_source_part_survives(tmp_path, extra):
    counter = [0, 1, 2, 3] if extra else None  # (without extras: a source with no counter at all)
    bundle = DatasetBundle(recording=Recording(sources=[_source("source1", "2026-01-01T00:00:00", counter, **extra)]))
    bundle.to_hdf5(str(tmp_path / "b.hdf5"))
    again = DatasetBundle.from_hdf5(str(tmp_path / "b.hdf5"))
    source = again.recording.only_source()
    with h5py.File(tmp_path / "b.hdf5") as f:
        assert f.attrs["icoschema_format_version"] == "2.0"
    assert source.sampling_frequency == extra.get("sampling_frequency")
    assert source.additional_data == extra.get("additional_data")


def test_steps_and_computations_are_kept_with_one_or_several_sources(tmp_path):
    for sources in ([_source("a", "2026-01-01T00:00:00")], [_source("a", "2026-01-01T00:00:00"), _source("b", None)]):
        bundle = DatasetBundle(recording=Recording(sources=sources))
        bundle = bundle.with_computation(
            "x/y", generated.DerivedDataset(key="x/y", values=[1.0], shape=[1], dtype="float64")
        )
        path = str(tmp_path / f"s{len(sources)}.hdf5")
        bundle.to_hdf5(path)
        again = DatasetBundle.from_hdf5(path)
        assert list(again.recording.sources) == [str(s.name) for s in sources]
        assert list(again.computations) == ["x/y"]


def test_a_file_reads_with_provenance_naming_its_format():
    provenance = DatasetBundle.from_hdf5(FIXTURE).provenance
    assert (provenance.source_format, provenance.source_format_version) == ("hdf5", "2.0")
    assert provenance.reader.startswith("icoschema") and provenance.writer.startswith("icoschema")


def test_provenance_is_kept_by_the_immutable_updates():
    bundle = DatasetBundle.from_hdf5(FIXTURE)
    derived = generated.DerivedDataset(key="k", values=[1.0], shape=[1], dtype="float64")
    assert bundle.with_computation("k", derived).provenance == bundle.provenance


def test_sources_are_placed_by_their_start_times_without_touching_their_own_timestamps():
    recording = Recording(
        sources=[
            _source("late", "2026-01-01T00:00:10.500000"),
            _source("early", "2026-01-01T00:00:00"),
            _source("none", None),
        ]
    )
    assert str(recording.earliest_start()) == "2026-01-01T00:00:00.000000"
    assert recording.start_offsets() == {"late": pytest.approx(10.5), "early": 0.0, "none": 0.0}
    assert recording.time_axis("late")[:2].tolist() == pytest.approx([10.5, 10.5001])
    assert recording.sources["late"].timestamps.tolist() == [0, 100, 200, 300]
    with pytest.raises(ValueError, match="3 sources"):
        recording.time_axis()


def test_a_source_has_a_description_and_mac_addresses(tmp_path):
    source = _source(
        "source1", "2026-01-01T00:00:00", [0, 1, 2, 3], description="a note", stu_mac="08-6B-D7-0F-47-2C", sth_mac="14-2D-41-D7-77-7D"
    )
    path = str(tmp_path / "m.hdf5")
    DatasetBundle(recording=Recording(sources=[source])).to_hdf5(path)

    again = DatasetBundle.from_hdf5(path).recording.only_source()
    assert (again.description, again.stu_mac, again.sth_mac) == ("a note", "08-6B-D7-0F-47-2C", "14-2D-41-D7-77-7D")
    assert not hasattr(again, "stu_id") and not hasattr(again, "sth_id")  # renamed in schema version 2
