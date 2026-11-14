"""The streaming `BundleWriter`: the files it writes are the ones `DatasetBundle.to_hdf5` writes."""

import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from icoschema.v2 import (
    BundleWriter,
    ChannelMetadata,
    DatasetBundle,
    LinearConversion,
    NoConversion,
    Sensor,
    SourceSpec,
)

START = "2026-11-14T10:00:00.000000"


def channel(number: int) -> ChannelMetadata:
    return ChannelMetadata(
        sensor=Sensor(sensor_id=f"acc{number}", name=f"Acceleration {number}", unit="g", dimension="Acceleration"),
        conversion=LinearConversion(gain=0.5 * number, offset=-1.0 * number),
    )


def spec(name: str = "sth1", channels: int = 3, **extra) -> SourceSpec:
    values = {
        "name": name,
        "channels": [channel(n) for n in range(1, channels + 1)],
        "start_time": START,
        "stu_mac": "08-6B-D7-0F-47-2C",
        "sth_mac": "14-2D-41-D7-77-7D",
        "adc_reference_voltage": 3.3,
        "adc_prescaler": 2,
        "adc_acquisition_time": 8,
        "adc_oversample_rate": 64,
    }
    values.update(extra)
    return SourceSpec(**values)


def rows(count: int, channels: int = 3, first: int = 0):
    index = np.arange(first, first + count)
    return (
        index * 315,  # microseconds
        [(index * (n + 1) % 1000).astype(np.float32) for n in range(channels)],
        index % 256,
    )


def test_a_single_source_is_written_at_the_root_and_read_back(tmp_path: Path) -> None:
    path = str(tmp_path / "one.hdf5")
    timestamps, values, counters = rows(1000)
    with BundleWriter(path, [spec()]) as writer:
        writer["sth1"].append(timestamps, values, counters)

    with h5py.File(path) as f:
        assert f.attrs["icoschema_format_version"] == "2.0"
        assert "sources" not in f.attrs and "recording" in f and "sensors" in f

    source = DatasetBundle.from_hdf5(path).recording.only_source()
    assert source.name == "sth1"
    assert source.stu_mac == "08-6B-D7-0F-47-2C" and source.sth_mac == "14-2D-41-D7-77-7D"
    assert source.recording_metadata.start_time == START
    assert source.hardware_metadata.adc_reference_voltage == "3.3"
    assert (
        source.hardware_metadata.adc_prescaler,
        source.hardware_metadata.adc_acquisition_time,
        source.hardware_metadata.adc_oversample_rate,
    ) == (2, 8, 64)
    np.testing.assert_array_equal(source.timestamps, timestamps)
    np.testing.assert_array_equal(source.counter, counters)
    for number, column in enumerate((source.channel1, source.channel2, source.channel3)):
        np.testing.assert_array_equal(column, values[number])
    conversion = source.hardware_metadata.channel2_metadata.conversion
    assert isinstance(conversion, LinearConversion) and (conversion.gain, conversion.offset) == (1.0, -2.0)
    assert source.hardware_metadata.channel3_metadata.sensor.sensor_id == "acc3"


def test_several_sources_are_written_under_sources_with_their_own_clocks(tmp_path: Path) -> None:
    path = str(tmp_path / "two.hdf5")
    with BundleWriter(
        path,
        [spec("sth1"), spec("sth2", channels=1, start_time="2026-11-14T10:00:00.250000", sth_mac="14-2D-41-D7-77-7E")],
    ) as writer:
        writer["sth1"].append(*rows(50)[:2], rows(50)[2])
        writer["sth2"].append(*rows(30, channels=1)[:2], rows(30, channels=1)[2])

    with h5py.File(path) as f:
        assert list(f.attrs["sources"]) == ["sth1", "sth2"]
        assert set(f["sources"]) == {"sth1", "sth2"}

    recording = DatasetBundle.from_hdf5(path).recording
    assert list(recording.sources) == ["sth1", "sth2"]
    assert len(recording.sources["sth1"].timestamps) == 50 and len(recording.sources["sth2"].timestamps) == 30
    assert recording.sources["sth2"].channel_count == 1
    assert recording.start_offsets() == {"sth1": 0.0, "sth2": 0.25}


def test_rows_and_blocks_can_be_mixed_across_the_buffer_boundary(tmp_path: Path) -> None:
    path = str(tmp_path / "mixed.hdf5")
    with BundleWriter(path, [spec(channels=2)], chunk_rows=7) as writer:
        source = writer["sth1"]
        for i in range(10):
            source.append_row(i * 100, [float(i), float(-i)], counter=i)
        assert source.rows == 10
        timestamps, values, counters = rows(20, channels=2, first=10)
        source.append(timestamps, np.stack(values, axis=1), counters)  # (rows, channels) form
        for i in range(30, 40):
            source.append_row(i * 315, [float(i), float(-i)], counter=i % 256)
        assert source.rows == 40

    source = DatasetBundle.from_hdf5(path).recording.only_source()
    assert len(source.timestamps) == 40
    np.testing.assert_array_equal(source.counter, np.arange(40))
    np.testing.assert_array_equal(source.channel1[:10], np.arange(10))
    np.testing.assert_array_equal(source.channel2[:10], -np.arange(10))


def test_what_is_only_known_later_is_updated(tmp_path: Path) -> None:
    path = str(tmp_path / "later.hdf5")
    with BundleWriter(path, [spec(channels=1)]) as writer:
        writer["sth1"].append_row(0, [1.0], counter=0)
        writer["sth1"].update(additional_data=json.dumps({"dataloss": 0.0}), post_metadata='{"x": 1}')
        with pytest.raises(TypeError, match="cannot update"):
            writer["sth1"].update(nonsense=1)

    source = DatasetBundle.from_hdf5(path).recording.only_source()
    assert json.loads(source.additional_data) == {"dataloss": 0.0}
    assert source.recording_metadata.post_metadata == '{"x": 1}'


def test_a_source_without_a_counter_is_a_waveform(tmp_path: Path) -> None:
    path = str(tmp_path / "waveform.hdf5")
    with BundleWriter(path, [spec(channels=1, has_counter=False, sampling_frequency=1000.0)]) as writer:
        for i in range(5):
            writer["sth1"].append_row(i * 1000, [float(i)])
    source = DatasetBundle.from_hdf5(path).recording.only_source()
    assert not source.has_counter and source.sampling_frequency == 1000.0


def test_it_writes_what_to_hdf5_writes(tmp_path: Path) -> None:
    streamed = str(tmp_path / "streamed.hdf5")
    timestamps, values, counters = rows(300)
    with BundleWriter(streamed, [spec()]) as writer:
        writer["sth1"].append(timestamps, values, counters)
    bundle = DatasetBundle.from_hdf5(streamed)
    bundle.to_hdf5(str(tmp_path / "saved.hdf5"))
    again = DatasetBundle.from_hdf5(str(tmp_path / "saved.hdf5"))
    assert again.recording.only_source() == bundle.recording.only_source()
    with h5py.File(streamed) as a, h5py.File(tmp_path / "saved.hdf5") as b:
        assert dict(a["recording"].attrs.items()).keys() == dict(b["recording"].attrs.items()).keys()
        assert a["sensors"][()].tolist() == b["sensors"][()].tolist()


def test_attachments_are_added_while_recording(tmp_path: Path) -> None:
    path = str(tmp_path / "attached.hdf5")
    with BundleWriter(path, [spec(channels=1)]) as writer:
        writer["sth1"].append_row(0, [1.0], counter=0)
        writer.add_picture("post__pictures", ["aGVsbG8=", "d29ybGQ="])
        writer.add_file("report", b"%PDF-1.4 ...", mime="application/pdf", original_name="Report 1.pdf")
        with pytest.raises(ValueError, match="already exists"):
            writer.add_file("report", b"other")

    with h5py.File(path) as f:
        assert f.attrs["icoschema_format_version"] == "2.0"
    bundle = DatasetBundle.from_hdf5(path)
    assert bundle.pictures == {"post__pictures": ["aGVsbG8=", "d29ybGQ="]}
    assert bundle.files["report"].content == b"%PDF-1.4 ..."
    assert bundle.files["report"].mime == "application/pdf" and bundle.files["report"].original_name == "Report 1.pdf"


def test_the_file_is_readable_after_an_exception_in_the_block(tmp_path: Path) -> None:
    path = str(tmp_path / "interrupted.hdf5")
    with pytest.raises(RuntimeError), BundleWriter(path, [spec(channels=1)]) as writer:
        for i in range(10):
            writer["sth1"].append_row(i, [float(i)], counter=i)
        raise RuntimeError("the recording failed")
    assert len(DatasetBundle.from_hdf5(path).recording.only_source().timestamps) == 10


def test_closing_twice_is_fine_and_a_closed_writer_refuses_more(tmp_path: Path) -> None:
    writer = BundleWriter(str(tmp_path / "closed.hdf5"), [spec(channels=1)])
    writer.close()
    writer.close()
    with pytest.raises(ValueError, match="closed"):
        writer.add_file("x", b"")


@pytest.mark.parametrize(
    ("sources", "message"),
    [
        ([], "at least one source"),
        ([spec("a"), spec("a")], "duplicate source names"),
        ([spec("a/b")], "must be non-empty, contain no '/'"),
        ([spec(".hidden")], "must be non-empty, contain no '/'"),
        ([SourceSpec(name="a", channels=[])], "one to three channels"),
        ([SourceSpec(name="a", channels=[channel(1)] * 4)], "one to three channels"),
    ],
)
def test_bad_sources_are_refused_before_a_file_is_written(tmp_path: Path, sources, message: str) -> None:
    path = tmp_path / "bad.hdf5"
    with pytest.raises(ValueError, match=message):
        BundleWriter(str(path), sources)


def test_bad_rows_are_refused(tmp_path: Path) -> None:
    with BundleWriter(str(tmp_path / "rows.hdf5"), [spec(channels=2)]) as writer:
        source = writer["sth1"]
        with pytest.raises(ValueError, match="2 channels, got 1 values"):
            source.append_row(0, [1.0], counter=0)
        with pytest.raises(ValueError, match="packet counter"):
            source.append_row(0, [1.0, 2.0])
        with pytest.raises(ValueError, match="packet counter"):
            source.append([0], [[1.0], [2.0]])
        with pytest.raises(ValueError, match="expected 3 rows"):
            source.append([0, 1, 2], [[1.0, 2.0, 3.0]], [0, 1, 2])


def test_no_channel_data_means_an_empty_but_readable_table(tmp_path: Path) -> None:
    path = str(tmp_path / "empty.hdf5")
    with BundleWriter(path, [spec(channels=1)]):
        pass
    with h5py.File(path) as f:
        assert f["recording"].shape == (0,) and f["recording"].maxshape == (None,)


def test_a_conversion_of_none_is_kept(tmp_path: Path) -> None:
    path = str(tmp_path / "none.hdf5")
    plain = ChannelMetadata(sensor=Sensor(sensor_id="v", unit="V"), conversion=NoConversion())
    with BundleWriter(path, [SourceSpec(name="a", channels=[plain], start_time=START)]) as writer:
        writer["a"].append_row(0, [1.5], counter=0)
    source = DatasetBundle.from_hdf5(path).recording.only_source()
    assert isinstance(source.hardware_metadata.channel1_metadata.conversion, NoConversion)
