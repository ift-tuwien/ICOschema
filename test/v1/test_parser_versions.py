"""Every parser version against the stored synthetic files in `test/v1/data/` (10 seconds of sine waves, 1 and 3
channels, and two-source files wherever the format supports several sources). See `synthetic_files.py` for how
the files are made and how to rewrite them.

HDF5: one file per format version, read through the public `DatasetBundle.from_hdf5`. TDMS: only the legacy
(unversioned) layout is supported, and every versioned file is rejected.
"""

from pathlib import Path

import h5py
import numpy as np
import pytest

from icoschema.v1 import DatasetBundle
from icoschema.v1.storage import hdf5 as hdf5_storage
from icoschema.v1.storage import tdms as tdms_storage

from .synthetic_files import (
    CHANNEL_COUNTS,
    COUNTERS,
    DATA_DIR,
    HDF5_WRITERS,
    N_ROWS,
    QUALITY,
    QUALITY_FREQUENCY,
    SAMPLING_FREQUENCY,
    SECOND_START_TIME,
    SOURCES,
    START_TIME,
    TDMS_START,
    TIMESTAMPS,
    VERSIONS,
    hdf5_name,
    sensor_name,
    signal,
    tdms_name,
    write_all,
)
from .tdms_writer import ChannelObject, GroupObject, RootObject, TdmsWriter

HDF5_CASES = [(version, multi, channels) for (version, multi) in HDF5_WRITERS for channels in CHANNEL_COUNTS]
HDF5_IDS = [hdf5_name(*case) for case in HDF5_CASES]


def stored(name: str) -> str:
    path = DATA_DIR / name
    assert path.exists(), f"{path} is missing; regenerate with `cd test && uv run python -m v1.synthetic_files`"
    return str(path)


# ── the stored files ─────────────────────────────────────────────────────────


def test_the_stored_files_are_the_ones_the_generator_makes(tmp_path: Path) -> None:
    """A change to the generator (or to what a parser reads from a file) shows up here until the files are
    regenerated: the stored and the freshly written files must read as the same bundle."""
    fresh = write_all(tmp_path)
    assert sorted(p.name for p in fresh) == sorted(p.name for p in DATA_DIR.iterdir())
    for path in fresh:
        read = DatasetBundle.from_hdf5 if path.suffix == ".hdf5" else DatasetBundle.from_tdms
        assert read(str(path)) == read(stored(path.name)), path.name


def test_every_hdf5_parser_has_a_stored_file() -> None:
    assert set(VERSIONS) == set(hdf5_storage.readable_versions())  # a new parser needs a new builder
    assert {version for version, _ in HDF5_WRITERS} == set(VERSIONS)


def test_the_formats_that_support_several_sources_have_such_a_file() -> None:
    assert {(version, multi) for version, multi in HDF5_WRITERS if multi} == {("1.3", True), ("1.4", True)}


# ── HDF5 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("version", "multi", "channels"), HDF5_CASES, ids=HDF5_IDS)
def test_each_version_reads_its_sources_and_channels(version: str, multi: bool, channels: int) -> None:
    recording = DatasetBundle.from_hdf5(stored(hdf5_name(version, channels, multi))).recording

    expected_names = list(SOURCES) if multi else ["tdms-like" if (version, multi) == ("1.4", False) else "source1"]
    assert list(recording.sources) == expected_names
    for index, source in enumerate(recording.sources.values()):
        assert source.recording_metadata.start_time == (START_TIME, SECOND_START_TIME)[index]
        assert source.hardware_metadata.adc_reference_voltage == "3.3"
        assert source.recording_data.timestamp == TIMESTAMPS
        assert len(source.recording_data.timestamp) == N_ROWS  # 10 s at 1 kHz
        for channel in (1, 2, 3):
            values = getattr(source.recording_data, f"channel{channel}")
            metadata = getattr(source.hardware_metadata, f"channel{channel}_metadata")
            if channel <= channels:
                assert values == signal(channel, index)
                assert metadata.sensor.name == sensor_name(channel)
            else:
                assert not values and metadata is None

        if version == "1.4":  # no counter, own rate and quality
            assert source.recording_data.counter == []
            assert source.sampling_frequency == SAMPLING_FREQUENCY
            assert source.quality.values == pytest.approx(QUALITY)
            assert source.quality.sampling_frequency == QUALITY_FREQUENCY
        else:
            assert source.recording_data.counter == COUNTERS
            assert source.quality is None and source.sampling_frequency is None


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
@pytest.mark.parametrize("version", ["1.3", "1.4"])
def test_several_sources_are_placed_by_their_start_times(version: str, channels: int) -> None:
    recording = DatasetBundle.from_hdf5(stored(hdf5_name(version, channels, True))).recording
    assert recording.start_offsets() == {"stu1": 0.0, "stu2": pytest.approx(1.0)}


@pytest.mark.parametrize(("version", "multi", "channels"), HDF5_CASES, ids=HDF5_IDS)
def test_each_version_reads_its_bundle_parts(version: str, multi: bool, channels: int) -> None:
    bundle = DatasetBundle.from_hdf5(stored(hdf5_name(version, channels, multi)))

    has_preprocessed = version in ("1.1", "1.2", "1.3")
    assert len(bundle.preprocessed_tables) == has_preprocessed
    if has_preprocessed:
        table = bundle.preprocessed_tables[0]
        assert table.channel_sampling_frequency == SAMPLING_FREQUENCY
        assert table.channel1 == signal(1)
        assert bool(table.channel3) == (channels == 3)
        assert table.source == ("stu1" if multi else "source1")

    has_steps = version in ("1.2", "1.3")
    assert [str(step.node) for step in bundle.steps] == (["rms"] if has_steps else [])
    assert list(bundle.computations) == (["rms/ch1"] if has_steps else [])
    assert bundle.provenance.source_format == "hdf5"
    assert bundle.provenance.source_format_version == version


@pytest.mark.parametrize(("version", "multi", "channels"), HDF5_CASES, ids=HDF5_IDS)
def test_a_stored_file_survives_a_rewrite(tmp_path: Path, version: str, multi: bool, channels: int) -> None:
    """Reading a file of any version and writing it again keeps its recording, steps and computations."""
    first = DatasetBundle.from_hdf5(stored(hdf5_name(version, channels, multi)))
    first.to_hdf5(str(tmp_path / "again.hdf5"))
    second = DatasetBundle.from_hdf5(str(tmp_path / "again.hdf5"))
    assert second.recording == first.recording
    assert second.preprocessed_tables == first.preprocessed_tables
    assert second.computations == first.computations
    assert second.steps == first.steps


def test_an_unknown_hdf5_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "f.hdf5"
    path.write_bytes(Path(stored(hdf5_name("1.0", 1))).read_bytes())
    with h5py.File(path, "r+") as f:
        f.attrs["icoschema_format_version"] = "2.0"
    with pytest.raises(ValueError, match="Unsupported icoschema_format_version '2.0'"):
        DatasetBundle.from_hdf5(str(path))


# ── TDMS: the legacy layout only ─────────────────────────────────────────────

TDMS_CASES = [(multi, channels) for multi in (False, True) for channels in CHANNEL_COUNTS]
TDMS_IDS = [tdms_name(channels, multi) for multi, channels in TDMS_CASES]


@pytest.mark.parametrize(("multi", "channels"), TDMS_CASES, ids=TDMS_IDS)
def test_tdms_legacy_reads_its_sources_and_channels(multi: bool, channels: int) -> None:
    bundle = DatasetBundle.from_tdms(stored(tdms_name(channels, multi)))
    recording = bundle.recording

    assert list(recording.sources) == (["STU1", "STU2"] if multi else ["source1"])
    for index, source in enumerate(recording.sources.values()):
        assert source.recording_data.timestamp == TIMESTAMPS  # 10 s at 1 kHz, derived from the rate
        assert source.recording_data.counter == []  # a waveform has none
        assert source.sampling_frequency == pytest.approx(SAMPLING_FREQUENCY)
        assert source.recording_metadata.start_time == f"2026-03-04T05:06:{7 + index:02d}.000000"
        assert source.quality.values == pytest.approx(QUALITY)
        assert source.quality.sampling_frequency == pytest.approx(QUALITY_FREQUENCY)
        for channel in (1, 2, 3):
            values = getattr(source.recording_data, f"channel{channel}")
            metadata = getattr(source.hardware_metadata, f"channel{channel}_metadata")
            if channel <= channels:
                assert values == signal(channel, index)
                expected_name = f"STU{index + 1}_Channel{channel}" if multi else f"Channel{channel}"
                assert (metadata.sensor.name, metadata.sensor.unit) == (expected_name, "g")
            else:
                assert not values and metadata is None
    if multi:
        assert [s.stu_id for s in recording.sources.values()] == ["STU1", "STU2"]
        assert recording.start_offsets() == {"STU1": 0.0, "STU2": pytest.approx(1.0)}
    assert bundle.provenance.source_format == "tdms"
    assert bundle.provenance.source_format_version == "legacy"


def test_tdms_has_no_versioned_parsers() -> None:
    assert tdms_storage._PARSERS == {}  # legacy is the only layout


@pytest.mark.parametrize("version", ["1.0", "1.4", "2.0"])
def test_tdms_files_with_a_version_are_rejected(tmp_path: Path, version: str) -> None:
    versioned = tmp_path / "v.tdms"  # a legacy-shaped file whose only difference is the version property
    with TdmsWriter(str(versioned)) as writer:
        writer.write_segment(
            [
                RootObject({tdms_storage.FORMAT_VERSION_PROPERTY: version}),
                GroupObject("rawdata"),
                ChannelObject(
                    "rawdata",
                    "Channel1",
                    np.array(signal(1), dtype=np.float32),
                    {"wf_increment": 0.001, "wf_start_time": TDMS_START, "wf_start_offset": 0.0},
                ),
            ]
        )
    with pytest.raises(ValueError, match=f"Unsupported icoschema_format_version '{version}'"):
        DatasetBundle.from_tdms(str(versioned))


@pytest.mark.parametrize(("multi", "channels"), TDMS_CASES, ids=TDMS_IDS)
def test_tdms_legacy_converts_to_hdf5_1_4(tmp_path: Path, multi: bool, channels: int) -> None:
    first = DatasetBundle.from_tdms(stored(tdms_name(channels, multi)))
    first.to_hdf5(str(tmp_path / "f.hdf5"))
    with h5py.File(tmp_path / "f.hdf5") as f:
        assert f.attrs["icoschema_format_version"] == "1.4"
    again = DatasetBundle.from_hdf5(str(tmp_path / "f.hdf5"))
    assert list(again.recording.sources) == list(first.recording.sources)
    for name, source in first.recording.sources.items():
        # (the sensors table stores a sensor's unset fields as '' and 0.0, so the sensors themselves are not compared)
        kept = again.recording.sources[name]
        assert kept.recording_data == source.recording_data
        assert kept.quality == source.quality
        assert kept.sampling_frequency == source.sampling_frequency
        assert kept.recording_metadata.start_time == source.recording_metadata.start_time
        assert kept.stu_id == source.stu_id
        assert kept.additional_data == source.additional_data
        for slot in ("channel1_metadata", "channel2_metadata", "channel3_metadata"):
            sensor = getattr(source.hardware_metadata, slot)
            sensor_again = getattr(kept.hardware_metadata, slot)
            assert (sensor is None) == (sensor_again is None)
            if sensor is not None:
                assert (sensor_again.sensor.name, sensor_again.sensor.unit) == (sensor.sensor.name, sensor.sensor.unit)
    assert again.provenance.source_format == "tdms"
