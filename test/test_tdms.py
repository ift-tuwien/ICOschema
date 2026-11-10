"""TDMS reading (legacy layout: files without `icoschema_format_version`),
on files shaped like the two real examples: one STU with a `system` group, and
two STUs with one quality group each."""

import datetime
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from icoschema import DatasetBundle, Recording
from icoschema.storage.python import tdms as tdms_storage
from test.tdms_writer import ChannelObject, GroupObject, RootObject, TdmsWriter

INCREMENT = 0.00010499790004199917
START = datetime.datetime(2025, 4, 17, 14, 8, 29, 342295)


def waveform(increment: float = INCREMENT, **extra) -> dict:
    return {"wf_increment": increment, "wf_start_time": START, "wf_start_offset": 0.0, **extra}


def write(path: Path, objects: list, root: dict | None = None) -> str:
    with TdmsWriter(str(path)) as writer:
        writer.write_segment([RootObject({"name": "t", **(root or {})}), *objects])
    return str(path)


def single_stu(path: Path, quality: list[float] | None = (100.0, 99.0, 98.0), n: int = 3000, root: dict | None = None) -> str:
    objects: list = []
    if quality is not None:
        objects += [
            GroupObject("system", {"deviceName": "Tool_01"}),
            ChannelObject("system", "signalQuality", np.array(quality, dtype=np.float32), waveform(0.1)),
        ]
    objects += [
        GroupObject("rawdata"),
        ChannelObject("rawdata", "Channel1", (np.arange(n) % 1000 - 500).astype(np.int16), waveform(unit_string="g")),
    ]
    return write(path, objects, root)


def two_stus(path: Path, qualities: tuple[list[float], list[float]] = ([100.0] * 3, [90.0, 80.0, 100.0])) -> str:
    return write(
        path,
        [
            GroupObject("STU1"),
            ChannelObject("STU1", "signalQuality", np.array(qualities[0], dtype=np.float32), waveform(0.1)),
            GroupObject("STU2"),
            ChannelObject("STU2", "signalQuality", np.array(qualities[1], dtype=np.float32), waveform(0.1)),
            GroupObject("rawdata"),
            ChannelObject("rawdata", "STU1_Channel1", np.linspace(0, 1, 3000, dtype=np.float32), waveform()),
            ChannelObject("rawdata", "STU2_Channel1", np.linspace(1, 2, 2970, dtype=np.float32), waveform()),
            GroupObject("info", {"Dashboard": "x"}),
        ],
    )


def test_single_stu_with_system_quality(tmp_path: Path) -> None:
    recording = DatasetBundle.from_tdms(single_stu(tmp_path / "a.tdms")).recording
    assert isinstance(recording, Recording)
    source = recording.only_source()
    assert str(source.name) == "source1"
    assert recording.channel_count == 1
    np.testing.assert_array_equal(recording.channel1, (np.arange(3000) % 1000 - 500).astype(float))
    assert recording.recording_metadata.start_time == "2025-04-17T14:08:29.342295"
    assert recording.timestamps[:3].tolist() == [0, 105, 210]  # from 1 / fs
    # no packet counter: a gap-free waveform, with its rate and quality on the source
    assert not recording.has_counter and recording.counter.size == 0
    assert source.sampling_frequency == pytest.approx(1 / INCREMENT)
    assert recording.channel_sampling_frequency() == (pytest.approx(1 / INCREMENT), "hardware")
    assert source.quality is not None and source.quality.values == pytest.approx([100.0, 99.0, 98.0])
    assert source.quality.sampling_frequency == pytest.approx(10.0)
    assert recording.signal_loss_percentage == pytest.approx(1.0)  # 100 - mean(100, 99, 98)
    assert recording.signal_loss_measured is True
    assert recording.rows_per_packet() == 1 and recording.sample_index().tolist() == list(range(3000))
    # the channel's name and unit come from the file; no conversion is claimed
    sensor = source.hardware_metadata.channel1_metadata.sensor
    assert (sensor.name, sensor.unit) == ("Channel1", "g")
    assert [type(c).__name__ for c in source.hardware_metadata.channel1_metadata.compensations] == ["NoConversion"]


def test_scaled_channels_are_stored_as_scaled_by_the_reader(tmp_path: Path) -> None:
    scaling = {
        "NI_Number_Of_Scales": 1,
        "NI_Scale[0]_Scale_Type": "Linear",
        "NI_Scale[0]_Linear_Slope": 2.0,
        "NI_Scale[0]_Linear_Y_Intercept": 10.0,
        "NI_Scale[0]_Linear_Input_Source": np.uint32(0xFFFFFFFF),
    }
    path = write(
        tmp_path / "s.tdms",
        [GroupObject("rawdata"), ChannelObject("rawdata", "c", np.array([1, 2, 3], dtype=np.int16), waveform(**scaling))],
    )
    source = DatasetBundle.from_tdms(path).recording.only_source()
    assert source.channel1.tolist() == [12.0, 14.0, 16.0]  # already scaled, hence NoConversion
    assert json.loads(source.additional_data)["channels"]["c"]["NI_Scale[0]_Linear_Slope"] == 2.0  # kept


def test_the_files_properties_are_kept_as_additional_data(tmp_path: Path) -> None:
    source = DatasetBundle.from_tdms(single_stu(tmp_path / "p.tdms", root={"author": "me"})).recording.only_source()
    data = json.loads(source.additional_data)
    assert data["file"]["author"] == "me" and data["group"] == {"deviceName": "Tool_01"}
    assert data["channels"]["Channel1"]["wf_start_time"] == "2025-04-17T14:08:29.342295"  # JSON-safe
    two = DatasetBundle.from_tdms(two_stus(tmp_path / "p2.tdms")).recording.sources["STU2"]
    assert json.loads(two.additional_data)["other_groups"] == {"info": {"Dashboard": "x"}}


def test_the_bundle_says_where_it_was_read_from(tmp_path: Path) -> None:
    provenance = DatasetBundle.from_tdms(single_stu(tmp_path / "a.tdms")).provenance
    assert (provenance.source_format, provenance.source_format_version) == ("tdms", "legacy")
    assert provenance.reader.startswith("icoschema")


def test_recording_from_tdms_matches_the_bundle(tmp_path: Path) -> None:
    path = two_stus(tmp_path / "b.tdms")
    assert list(Recording.from_tdms(path).sources) == list(DatasetBundle.from_tdms(path).recording.sources)


def test_two_stus_are_two_sources(tmp_path: Path) -> None:
    sources = DatasetBundle.from_tdms(two_stus(tmp_path / "b.tdms")).recording.sources
    assert list(sources) == ["STU1", "STU2"]
    stu1, stu2 = sources["STU1"], sources["STU2"]
    assert (stu1.stu_id, stu2.stu_id) == ("STU1", "STU2")
    assert (len(stu1.channel1), len(stu2.channel1)) == (3000, 2970)  # nothing is cut across STUs
    assert [s.signal_loss_percentage for s in (stu1, stu2)] == pytest.approx([0.0, 10.0])  # per STU
    assert [s.signal_loss_measured for s in (stu1, stu2)] == [True, True]


def test_two_stus_keep_their_own_rate_start_time_and_channels(tmp_path: Path) -> None:
    later = {"wf_increment": 0.0005, "wf_start_time": START + datetime.timedelta(seconds=7), "wf_start_offset": 0.0}
    path = write(
        tmp_path / "own.tdms",
        [
            GroupObject("STU1"),
            ChannelObject("STU1", "signalQuality", np.array([100.0], dtype=np.float32), waveform(0.1)),
            GroupObject("STU10"),
            ChannelObject("STU10", "signalQuality", np.array([95.0], dtype=np.float32), waveform(0.1)),
            GroupObject("rawdata"),
            ChannelObject("rawdata", "STU1_x", np.zeros(100, dtype=np.float32), waveform()),
            ChannelObject("rawdata", "STU10_x", np.ones(50, dtype=np.float32), later),
            ChannelObject("rawdata", "STU10_y", np.ones(50, dtype=np.float32), later),
        ],
    )
    recording = DatasetBundle.from_tdms(path).recording
    one, ten = recording.sources["STU1"], recording.sources["STU10"]  # longest group name wins
    assert (one.channel_count, ten.channel_count) == (1, 2)
    assert (len(one.channel1), len(ten.channel1)) == (100, 50)
    assert one.summary()["start_time"] == "2025-04-17T14:08:29.342295"
    assert ten.summary()["start_time"] == "2025-04-17T14:08:36.342295"
    assert one.sampling_frequency == pytest.approx(1 / INCREMENT) and ten.sampling_frequency == pytest.approx(2000.0)
    assert ten.total_sampling_frequency() == (pytest.approx(4000.0), "hardware")  # two channels
    # the sources are placed against each other by start time; their own timestamps are untouched
    assert recording.start_offsets() == {"STU1": 0.0, "STU10": pytest.approx(7.0)}
    assert ten.timestamps[0] == 0 and recording.time_axis("STU10")[0] == pytest.approx(7.0)
    assert recording.time_axis("STU1")[1] == pytest.approx(INCREMENT, abs=1e-6)  # timestamps are whole microseconds


def test_the_start_offset_is_added_to_the_start_time(tmp_path: Path) -> None:
    path = write(
        tmp_path / "o.tdms",
        [GroupObject("rawdata"), ChannelObject("rawdata", "c", np.zeros(5), waveform(wf_start_offset=2.5))],
    )
    assert DatasetBundle.from_tdms(path).recording.recording_metadata.start_time == "2025-04-17T14:08:31.842295"


def test_a_tdms_bundle_round_trips_through_hdf5_as_1_4(tmp_path: Path) -> None:
    bundle = DatasetBundle.from_tdms(two_stus(tmp_path / "r.tdms"))
    bundle.to_hdf5(str(tmp_path / "r.hdf5"))
    with h5py.File(tmp_path / "r.hdf5") as f:
        assert f.attrs["icoschema_format_version"] == "1.4"
        assert f.attrs["source_format"] == "tdms" and f.attrs["writer"].startswith("icoschema")
        assert "counter" not in f["sources"]["STU1"]["recording"].dtype.names
    again = DatasetBundle.from_hdf5(str(tmp_path / "r.hdf5"))
    assert list(again.recording.sources) == ["STU1", "STU2"]
    stu2 = again.recording.sources["STU2"]
    assert stu2.stu_id == "STU2" and not stu2.has_counter
    assert stu2.sampling_frequency == pytest.approx(1 / INCREMENT)
    assert stu2.quality is not None and stu2.quality.sampling_frequency == pytest.approx(10.0)
    assert stu2.signal_loss_percentage == pytest.approx(10.0)
    assert json.loads(stu2.additional_data) == json.loads(bundle.recording.sources["STU2"].additional_data)
    # where the data came from survives the round trip; the writer is the HDF5 file's
    assert (again.provenance.source_format, again.provenance.source_format_version) == ("tdms", "legacy")
    assert again.provenance.writer.startswith("icoschema")


def test_a_single_source_name_is_always_stored_in_1_4(tmp_path: Path) -> None:
    DatasetBundle.from_tdms(single_stu(tmp_path / "n.tdms")).to_hdf5(str(tmp_path / "n.hdf5"))
    with h5py.File(tmp_path / "n.hdf5") as f:
        assert f.attrs["icoschema_format_version"] == "1.4"
        assert f["recording"].attrs["source_name"] == "source1"


@pytest.mark.parametrize("quality", [None, []])
def test_missing_or_empty_quality_is_assumed_zero_loss(tmp_path: Path, quality: list[float] | None) -> None:
    source = DatasetBundle.from_tdms(single_stu(tmp_path / "c.tdms", quality=quality)).recording.only_source()
    assert source.quality is None
    assert source.signal_loss_percentage == 0.0 and source.signal_loss_measured is False


def test_quality_groups_not_matching_channels_warn(tmp_path: Path) -> None:
    path = write(
        tmp_path / "d.tdms",
        [
            GroupObject("A"),
            ChannelObject("A", "signalQuality", np.array([50.0], dtype=np.float32), waveform(0.1)),
            GroupObject("rawdata"),
            ChannelObject("rawdata", "x", np.zeros(10, dtype=np.float32), waveform()),
            ChannelObject("rawdata", "y", np.zeros(10, dtype=np.float32), waveform()),
        ],
    )
    with pytest.warns(UserWarning, match="assumed 0"):
        source = DatasetBundle.from_tdms(path).recording.only_source()
    assert source.signal_loss_measured is False


def test_the_worst_of_several_quality_groups_is_kept(tmp_path: Path) -> None:
    path = write(
        tmp_path / "w.tdms",
        [
            GroupObject("A"),
            ChannelObject("A", "signalQuality", np.array([100.0, 100.0], dtype=np.float32), waveform(0.1)),
            GroupObject("B"),
            ChannelObject("B", "signalQuality", np.array([60.0, 80.0], dtype=np.float32), waveform(0.1)),
            GroupObject("rawdata"),
            ChannelObject("rawdata", "x", np.zeros(10, dtype=np.float32), waveform()),
            ChannelObject("rawdata", "y", np.zeros(10, dtype=np.float32), waveform()),
        ],
    )
    assert DatasetBundle.from_tdms(path).recording.signal_loss_percentage == pytest.approx(30.0)


def test_unusable_files_raise(tmp_path: Path) -> None:
    no_raw = write(tmp_path / "e.tdms", [GroupObject("other"), ChannelObject("other", "x", np.zeros(3), waveform())])
    with pytest.raises(ValueError, match="rawdata"):
        DatasetBundle.from_tdms(no_raw)
    mixed = write(
        tmp_path / "f.tdms",
        [
            GroupObject("rawdata"),
            ChannelObject("rawdata", "a", np.zeros(5), waveform(0.001)),
            ChannelObject("rawdata", "b", np.zeros(5), waveform(0.002)),
        ],
    )
    with pytest.raises(ValueError, match="different wf_increment"):
        DatasetBundle.from_tdms(mixed)
    many = write(
        tmp_path / "g.tdms",
        [GroupObject("rawdata")] + [ChannelObject("rawdata", f"c{i}", np.zeros(5), waveform()) for i in range(4)],
    )
    with pytest.raises(ValueError, match="at most 3"):
        DatasetBundle.from_tdms(many)


def test_channels_of_one_source_must_have_the_same_length(tmp_path: Path) -> None:
    path = write(
        tmp_path / "l.tdms",
        [
            GroupObject("rawdata"),
            ChannelObject("rawdata", "a", np.zeros(5), waveform()),
            ChannelObject("rawdata", "b", np.zeros(4), waveform()),
        ],
    )
    with pytest.raises(ValueError, match="different lengths"):
        DatasetBundle.from_tdms(path)


def test_an_unknown_format_version_is_rejected(tmp_path: Path) -> None:
    path = single_stu(tmp_path / "v.tdms", root={tdms_storage.FORMAT_VERSION_PROPERTY: "9.9"})
    with pytest.raises(ValueError, match="Unsupported icoschema_format_version '9.9'"):
        DatasetBundle.from_tdms(path)


def test_a_registered_version_parser_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = single_stu(tmp_path / "v.tdms", root={tdms_storage.FORMAT_VERSION_PROPERTY: "2.0"})
    called = []

    def parser(file: str, tdms):
        called.append(file)
        return tdms_storage._load_recording_legacy(file, tdms)

    monkeypatch.setitem(tdms_storage._PARSERS, "2.0", parser)
    bundle = DatasetBundle.from_tdms(path)
    assert called == [path] and bundle.provenance.source_format_version == "2.0"


def test_from_file_tells_hdf5_and_tdms_apart_by_content(tmp_path: Path) -> None:
    tdms_path = single_stu(tmp_path / "noext")  # the name says nothing
    assert DatasetBundle.from_file(tdms_path).recording.channel_count == 1
    hdf5_path = str(tmp_path / "also_noext")
    DatasetBundle.from_tdms(tdms_path).to_hdf5(hdf5_path)
    assert DatasetBundle.from_file(hdf5_path).recording.channel_count == 1
    junk = tmp_path / "junk.tdms"
    junk.write_bytes(b"not a recording")
    with pytest.raises(ValueError, match="neither an HDF5 nor a TDMS"):
        DatasetBundle.from_file(str(junk))


def test_files_saved_with_the_old_tdms_json_still_report_rate_and_loss() -> None:
    from icoschema.model.python.recording import Source
    from icoschema.schema.generated.python import dataset as generated

    legacy = json.dumps({"tdms": {"sampling_frequency": 5000.0, "signal_loss_percentage": 2.5, "signal_loss_measured": True}})
    source = Source(
        name="source1",
        hardware_metadata=generated.HardwareMetadata(
            channel1_metadata=generated.ChannelMetadata(sensor=generated.Sensor(), compensations=[generated.NoConversion(order=0)])
        ),
        recording_metadata=generated.RecordingMetadata(start_time="2025-01-01T00:00:00", post_metadata=legacy),
        recording_data=generated.RecordingData(timestamp=[0, 200, 400], counter=[0, 1, 2], channel1=[1.0, 2.0, 3.0]),
    )
    assert source.channel_sampling_frequency() == (5000.0, "hardware")
    assert source.signal_loss_percentage == 2.5 and source.signal_loss_measured is True
