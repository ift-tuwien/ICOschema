"""Format 2.0 against the stored synthetic files in `test/v2/data/` (10 seconds of sine waves, 1 and 3 channels, in
the kinds of file `synthetic_files.py` describes), and what happens to files of other schema versions. See
`synthetic_files.py` for how the files are made and how to rewrite them.

HDF5: read through the public `DatasetBundle.from_hdf5`. TDMS: only the legacy (unversioned) layout is supported, and
every versioned file is rejected.
"""

from pathlib import Path

import h5py
import numpy as np
import pytest

from icoschema import _schemas
from icoschema.v2 import DatasetBundle, LinearConversion, NoConversion
from icoschema.v2.storage import hdf5 as hdf5_storage
from icoschema.v2.storage import tdms as tdms_storage

from .synthetic_files import (
    CHANNEL_COUNTS,
    COUNTERS,
    DATA_DIR,
    DESCRIPTION,
    FORMAT_VERSION,
    HDF5_WRITERS,
    N_ROWS,
    QUALITY,
    QUALITY_FREQUENCY,
    SAMPLING_FREQUENCY,
    SECOND_START_TIME,
    SOURCES,
    START_TIME,
    STH_MAC,
    STU_MAC,
    TDMS_START,
    TIMESTAMPS,
    conversion_of,
    hdf5_name,
    sensor_name,
    signal,
    tdms_name,
    write_all,
)
from .tdms_writer import ChannelObject, GroupObject, RootObject, TdmsWriter

V1_DATA = Path(__file__).resolve().parent.parent / "v1" / "data"
HDF5_CASES = [(kind, channels) for kind in HDF5_WRITERS for channels in CHANNEL_COUNTS]
HDF5_IDS = [hdf5_name(*case) for case in HDF5_CASES]


def stored(name: str) -> str:
    path = DATA_DIR / name
    assert path.exists(), f"{path} is missing; regenerate with `cd test && uv run python -m v2.synthetic_files`"
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


@pytest.mark.parametrize("path", sorted(DATA_DIR.iterdir()), ids=lambda p: p.name)
def test_the_stored_files_say_which_schema_version_they_are_of(path: Path) -> None:
    # A TDMS file of the (only, unversioned) layout is of schema version 1 by the rule of `schema_version_of`,
    # though every schema version reads it.
    assert _schemas.file_schema_version(str(path)) == (2 if path.suffix == ".hdf5" else 1)


def test_the_only_hdf5_format_is_2_0() -> None:
    assert hdf5_storage.readable_versions() == (FORMAT_VERSION,)


# ── HDF5 ─────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("kind", "channels"), HDF5_CASES, ids=HDF5_IDS)
def test_each_kind_reads_its_sources_and_channels(kind: str, channels: int) -> None:
    recording = DatasetBundle.from_hdf5(stored(hdf5_name(kind, channels))).recording

    expected_names = {"packets": ["source1"], "waveform": ["tdms-like"], "multi": list(SOURCES)}[kind]
    assert list(recording.sources) == expected_names
    for index, source in enumerate(recording.sources.values()):
        packets = kind == "packets" or (kind == "multi" and index == 0)
        assert source.recording_metadata.start_time == (START_TIME, SECOND_START_TIME)[index]
        assert source.hardware_metadata.adc_reference_voltage == "3.3"
        assert source.recording_data.timestamp == TIMESTAMPS
        assert len(source.recording_data.timestamp) == N_ROWS  # 10 s at 1 kHz
        for channel in (1, 2, 3):
            values = getattr(source.recording_data, f"channel{channel}")
            metadata = getattr(source.hardware_metadata, f"channel{channel}_metadata")
            if channel > channels:
                assert not values and metadata is None
                continue
            assert values == signal(channel, index)
            assert metadata.sensor.name == sensor_name(channel)
            assert metadata.sensor.unit == "g"
            kind_of_conversion, gain, offset = conversion_of(channel)
            if kind_of_conversion == "none":
                assert metadata.conversion == NoConversion()
            else:
                assert metadata.conversion == LinearConversion(gain=gain, offset=offset)

        if packets:
            assert source.recording_data.counter == COUNTERS
            assert source.quality is None and source.sampling_frequency is None
            assert source.additional_data is None
        else:  # no counter, own rate and quality
            assert source.recording_data.counter == []
            assert source.sampling_frequency == SAMPLING_FREQUENCY
            assert source.quality.values == pytest.approx(QUALITY)
            assert source.quality.sampling_frequency == QUALITY_FREQUENCY
            assert source.additional_data == '{"file": "x.tdms"}'


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_the_description_and_the_mac_addresses_are_read(channels: int) -> None:
    source = DatasetBundle.from_hdf5(stored(hdf5_name("packets", channels))).recording.only_source()
    assert (source.description, source.stu_mac, source.sth_mac) == (DESCRIPTION, STU_MAC, STH_MAC)
    first, second = DatasetBundle.from_hdf5(stored(hdf5_name("multi", channels))).recording.sources.values()
    assert (first.description, first.stu_mac, first.sth_mac) == (None, STU_MAC, None)  # not set: not there
    assert (second.description, second.stu_mac, second.sth_mac) == (None, None, None)


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_several_sources_are_placed_by_their_start_times(channels: int) -> None:
    recording = DatasetBundle.from_hdf5(stored(hdf5_name("multi", channels))).recording
    assert recording.start_offsets() == {"stu1": 0.0, "stu2": pytest.approx(1.0)}


@pytest.mark.parametrize(("kind", "channels"), HDF5_CASES, ids=HDF5_IDS)
def test_each_kind_reads_its_bundle_parts(kind: str, channels: int) -> None:
    bundle = DatasetBundle.from_hdf5(stored(hdf5_name(kind, channels)))

    has_preprocessed = kind != "waveform"
    assert len(bundle.preprocessed_tables) == has_preprocessed
    if has_preprocessed:
        table = bundle.preprocessed_tables[0]
        assert table.channel_sampling_frequency == SAMPLING_FREQUENCY
        assert table.channel1 == signal(1)
        assert bool(table.channel3) == (channels == 3)
        assert table.source == ("stu1" if kind == "multi" else "source1")

    has_steps = kind != "waveform"
    assert [str(step.node) for step in bundle.steps] == (["rms"] if has_steps else [])
    assert list(bundle.computations) == (["rms/ch1"] if has_steps else [])
    assert bundle.provenance.source_format == "hdf5"
    assert bundle.provenance.source_format_version == FORMAT_VERSION


@pytest.mark.parametrize(("kind", "channels"), HDF5_CASES, ids=HDF5_IDS)
def test_a_stored_file_survives_a_rewrite(tmp_path: Path, kind: str, channels: int) -> None:
    """Reading a file and writing it again keeps its recording, preprocessed tables, steps and computations."""
    first = DatasetBundle.from_hdf5(stored(hdf5_name(kind, channels)))
    first.to_hdf5(str(tmp_path / "again.hdf5"))
    second = DatasetBundle.from_hdf5(str(tmp_path / "again.hdf5"))
    assert second.recording == first.recording
    assert second.preprocessed_tables == first.preprocessed_tables
    assert second.computations == first.computations
    assert second.steps == first.steps


# ── files of other format versions ───────────────────────────────────────────


def test_an_unknown_hdf5_version_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "f.hdf5"
    path.write_bytes(Path(stored(hdf5_name("packets", 1))).read_bytes())
    with h5py.File(path, "r+") as f:
        f.attrs["icoschema_format_version"] = "2.7"
    with pytest.raises(ValueError, match=r"Unsupported icoschema_format_version '2.7'.*supported versions: \['2.0'\]"):
        DatasetBundle.from_hdf5(str(path))


@pytest.mark.parametrize("name", sorted(p.name for p in V1_DATA.glob("hdf5_*")))
def test_a_file_of_schema_version_1_is_refused_with_the_way_to_read_it(name: str) -> None:
    pattern = "has no icoschema_format_version.*icoschema.v1" if "legacy" in name else "read it with icoschema.v1"
    with pytest.raises(ValueError, match=pattern):
        DatasetBundle.from_hdf5(str(V1_DATA / name))


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
        assert (source.description, source.stu_mac, source.sth_mac) == (None, None, None)  # a TDMS file has none
        for channel in (1, 2, 3):
            values = getattr(source.recording_data, f"channel{channel}")
            metadata = getattr(source.hardware_metadata, f"channel{channel}_metadata")
            if channel <= channels:
                assert values == signal(channel, index)
                expected_name = f"STU{index + 1}_Channel{channel}" if multi else f"Channel{channel}"
                assert (metadata.sensor.name, metadata.sensor.unit) == (expected_name, "g")
                # the values are already in `unit`: an identity conversion, not NoConversion (raw voltage values)
                assert metadata.conversion == LinearConversion(gain=1.0, offset=0.0)
            else:
                assert not values and metadata is None
    if multi:
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
def test_tdms_legacy_converts_to_hdf5_2_0_and_back_unchanged(tmp_path: Path, multi: bool, channels: int) -> None:
    first = DatasetBundle.from_tdms(stored(tdms_name(channels, multi)))
    first.to_hdf5(str(tmp_path / "f.hdf5"))
    with h5py.File(tmp_path / "f.hdf5") as f:
        assert f.attrs["icoschema_format_version"] == FORMAT_VERSION
    again = DatasetBundle.from_hdf5(str(tmp_path / "f.hdf5"))
    assert again.recording == first.recording  # sensors and conversions included
    assert again.provenance.source_format == "tdms"
