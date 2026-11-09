"""TDMS reading (legacy layout: files without `icoschema_format_version`),
on files shaped like the two real examples: one STU with a `system` group, and
two STUs with one quality group each."""

import datetime
import json
from pathlib import Path

import numpy as np
import pytest
from nptdms import ChannelObject, GroupObject, RootObject, TdmsWriter

from icoschema import DatasetBundle, Recording
from icoschema.storage.python import tdms as tdms_storage
from icoschema.storage.python.tdms import TDMS_METADATA_KEY

INCREMENT = 0.00010499790004199917
START = datetime.datetime(2025, 4, 17, 14, 8, 29, 342295)


def waveform(increment: float = INCREMENT) -> dict:
    return {"wf_increment": increment, "wf_start_time": START, "wf_start_offset": 0.0}


def write(path: Path, objects: list, root: dict | None = None) -> str:
    with TdmsWriter(str(path)) as writer:
        writer.write_segment([RootObject({"name": "t", **(root or {})}), *objects])
    return str(path)


def section_of(source) -> dict:
    return json.loads(source.recording_metadata.post_metadata)[TDMS_METADATA_KEY]


def single_stu(path: Path, quality: list[float] | None = (100.0, 99.0, 98.0), n: int = 3000, root: dict | None = None) -> str:
    objects: list = []
    if quality is not None:
        objects += [
            GroupObject("system", {"deviceName": "Tool_01"}),
            ChannelObject("system", "signalQuality", np.array(quality, dtype=np.float32), waveform(0.1)),
        ]
    objects += [
        GroupObject("rawdata"),
        ChannelObject("rawdata", "Channel1", (np.arange(n) % 1000 - 500).astype(np.int16), waveform()),
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
    assert list(recording.sources) == ["source1"]
    assert recording.channel_count == 1
    np.testing.assert_array_equal(recording.channel1, (np.arange(3000) % 1000 - 500).astype(float))  # as stored
    assert recording.recording_metadata.start_time == "2025-04-17T14:08:29.342295"
    assert recording.timestamps[:3].tolist() == [0, 105, 210]
    assert recording.counter[:3].tolist() == [0, 1, 2] and recording.counter[256] == 0
    assert recording.signal_loss_percentage == 0  # the counter has no gaps by construction
    section = section_of(recording.only_source())
    assert section["sampling_frequency"] == pytest.approx(1 / INCREMENT)
    assert section["signal_loss_percentage"] == pytest.approx(1.0)  # 100 - mean(100, 99, 98)
    assert section["signal_loss_measured"] is True and section["signal_quality_source"] == "system"
    assert section["channels"] == ["Channel1"]


def test_recording_from_tdms_matches_the_bundle(tmp_path: Path) -> None:
    path = two_stus(tmp_path / "b.tdms")
    assert list(Recording.from_tdms(path).sources) == list(DatasetBundle.from_tdms(path).recording.sources)


def test_two_stus_are_two_sources(tmp_path: Path) -> None:
    sources = DatasetBundle.from_tdms(two_stus(tmp_path / "b.tdms")).recording.sources
    assert list(sources) == ["STU1", "STU2"]
    stu1, stu2 = sources["STU1"], sources["STU2"]
    assert (stu1.stu_id, stu2.stu_id) == ("STU1", "STU2")
    assert (len(stu1.channel1), len(stu2.channel1)) == (3000, 2970)  # nothing is cut across STUs
    sections = [section_of(s) for s in (stu1, stu2)]
    assert [s["dropped_rows"] for s in sections] == [0, 0]
    assert [s["signal_quality_source"] for s in sections] == ["group", "group"]
    assert [s["signal_loss_percentage"] for s in sections] == pytest.approx([0.0, 10.0])


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
            ChannelObject("rawdata", "STU10_y", np.ones(60, dtype=np.float32), later),
        ],
    )
    sources = DatasetBundle.from_tdms(path).recording.sources
    one, ten = sources["STU1"], sources["STU10"]  # longest group name wins
    assert (one.channel_count, ten.channel_count) == (1, 2)
    assert (len(one.channel1), len(ten.channel1)) == (100, 50)
    assert section_of(ten)["dropped_rows"] == 10  # cut within the STU only
    assert one.summary()["start_time"] == "2025-04-17T14:08:29.342295"
    assert ten.summary()["start_time"] == "2025-04-17T14:08:36.342295"
    assert section_of(one)["sampling_frequency"] == pytest.approx(1 / INCREMENT)
    assert section_of(ten)["sampling_frequency"] == pytest.approx(2000.0)


def test_a_tdms_bundle_round_trips_through_hdf5(tmp_path: Path) -> None:
    bundle = DatasetBundle.from_tdms(two_stus(tmp_path / "r.tdms"))
    bundle.to_hdf5(str(tmp_path / "r.hdf5"))
    again = DatasetBundle.from_hdf5(str(tmp_path / "r.hdf5"))
    assert list(again.recording.sources) == ["STU1", "STU2"]
    assert again.recording.sources["STU2"].stu_id == "STU2"
    assert section_of(again.recording.sources["STU2"])["signal_loss_percentage"] == pytest.approx(10.0)


@pytest.mark.parametrize("quality", [None, []])
def test_missing_or_empty_quality_is_assumed_zero_loss(tmp_path: Path, quality: list[float] | None) -> None:
    section = section_of(DatasetBundle.from_tdms(single_stu(tmp_path / "c.tdms", quality=quality)).recording.only_source())
    assert section["signal_loss_percentage"] == 0.0 and section["signal_loss_measured"] is False


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
        recording = DatasetBundle.from_tdms(path).recording
    assert section_of(recording.only_source())["signal_loss_measured"] is False


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
    DatasetBundle.from_tdms(path)
    assert called == [path]


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
