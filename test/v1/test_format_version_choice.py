"""Choosing the HDF5 file format version when writing (`to_hdf5(format_version=...)`), against the stored
synthetic files in `test/v1/data/`: each file is written in every writable version and either comes back with the
same content or is refused, naming what the version can't hold."""

import typing
from pathlib import Path

import h5py
import pytest

from icoschema import v1
from icoschema.v1 import DatasetBundle, Recording
from icoschema.v1.storage import hdf5 as hdf5_storage

from .synthetic_files import CHANNEL_COUNTS, DATA_DIR, hdf5_name, tdms_name

WRITABLE = v1.hdf5_format_versions(writable=True)


def as_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


# file -> the oldest writable version that can hold it (every later one can too)
OLDEST = {
    "hdf5_1.0": "1.0",  # plain packets, one source
    "hdf5_1.1": "1.1",  # + a preprocessed table
    "hdf5_1.2": "1.2",  # + steps
    "hdf5_1.3_multi": "1.3",  # two sources
    "hdf5_1.4": "1.4",  # no counter, rate, quality, additional data
    "hdf5_1.4_multi": "1.4",
    "tdms_legacy": "1.4",
    "tdms_legacy_multi": "1.4",
}
CASES = [(key, channels) for key in OLDEST for channels in CHANNEL_COUNTS]


def stored_bundle(key: str, channels: int) -> DatasetBundle:
    kind = key.partition("_")[0]
    multi = key.endswith("_multi")
    version = key.removeprefix("hdf5_").removesuffix("_multi")
    if kind == "hdf5":
        return DatasetBundle.from_hdf5(
            str(DATA_DIR / hdf5_name(version, channels, multi))
        )
    return DatasetBundle.from_tdms(str(DATA_DIR / tdms_name(channels, multi)))


def assert_same_content(first: DatasetBundle, second: DatasetBundle) -> None:
    assert list(second.recording.sources) == list(first.recording.sources)
    for name, source in first.recording.sources.items():
        kept = second.recording.sources[name]
        assert kept.recording_data == source.recording_data
        assert kept.quality == source.quality
        assert kept.sampling_frequency == source.sampling_frequency
        assert (
            kept.recording_metadata.start_time == source.recording_metadata.start_time
        )
    assert second.preprocessed_tables == first.preprocessed_tables
    assert second.steps == first.steps
    assert second.computations == first.computations


# ── the registry ─────────────────────────────────────────────────────────────


def test_the_typed_versions_are_the_writable_ones() -> None:
    assert (
        typing.get_args(hdf5_storage.FormatVersion)
        == WRITABLE
        == ("1.0", "1.1", "1.2", "1.3", "1.4")
    )


def test_the_readable_versions_add_the_legacy_layout() -> None:
    assert v1.hdf5_format_versions() == ("legacy", *WRITABLE)


# ── writing each file in each version ────────────────────────────────────────


@pytest.mark.parametrize(("key", "channels"), CASES)
def test_the_default_is_the_oldest_version_that_fits(
    tmp_path: Path, key: str, channels: int
) -> None:
    stored_bundle(key, channels).to_hdf5(str(tmp_path / "f.hdf5"))
    with h5py.File(tmp_path / "f.hdf5") as f:
        assert f.attrs["icoschema_format_version"] == OLDEST[key]


@pytest.mark.parametrize(("key", "channels"), CASES)
@pytest.mark.parametrize("version", WRITABLE)
def test_a_chosen_version_is_written_or_refused(
    tmp_path: Path, key: str, channels: int, version: str
) -> None:
    bundle = stored_bundle(key, channels)
    path = tmp_path / "f.hdf5"
    if as_tuple(version) < as_tuple(OLDEST[key]):
        with pytest.raises(ValueError, match=f"Cannot write format '{version}': "):
            bundle.to_hdf5(str(path), format_version=version)
        assert not path.exists()  # refused before anything was written
        return
    bundle.to_hdf5(str(path), format_version=version)
    with h5py.File(path) as f:
        assert f.attrs["icoschema_format_version"] == version
    assert_same_content(bundle, DatasetBundle.from_hdf5(str(path)))


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_the_refusal_says_what_does_not_fit(tmp_path: Path, channels: int) -> None:
    def refusal(key: str, version: str) -> str:
        with pytest.raises(ValueError) as error:
            stored_bundle(key, channels).to_hdf5(
                str(tmp_path / "f.hdf5"), format_version=version
            )
        return str(error.value)

    assert "preprocessed table" in refusal("hdf5_1.1", "1.0")
    assert "computation steps" in refusal("hdf5_1.2", "1.1")
    assert "2 sources" in refusal("hdf5_1.3_multi", "1.2")
    assert (
        "source 'tdms-like' has no packet counter, a sampling_frequency, quality, additional_data"
        in refusal("hdf5_1.4", "1.3")
    )


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_1_3_keeps_even_a_single_source_under_sources(
    tmp_path: Path, channels: int
) -> None:
    bundle = stored_bundle("hdf5_1.0", channels)
    bundle.to_hdf5(str(tmp_path / "f.hdf5"), format_version="1.3")
    with h5py.File(tmp_path / "f.hdf5") as f:
        assert list(f.attrs["sources"]) == ["source1"]
        assert "source1" in f["sources"]


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_1_4_names_a_single_source_and_1_0_does_not_need_to(
    tmp_path: Path, channels: int
) -> None:
    bundle = stored_bundle("hdf5_1.0", channels)
    bundle.to_hdf5(str(tmp_path / "a.hdf5"), format_version="1.4")
    bundle.to_hdf5(str(tmp_path / "b.hdf5"))
    with h5py.File(tmp_path / "a.hdf5") as a, h5py.File(tmp_path / "b.hdf5") as b:
        assert a["recording"].attrs["source_name"] == "source1"
        assert "source_name" not in b["recording"].attrs


# ── bad requests ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("version", ["legacy", "2.0", "1", ""])
def test_a_version_that_cannot_be_written_is_refused_with_the_writable_ones(
    tmp_path: Path, version: str
) -> None:
    bundle = stored_bundle("hdf5_1.0", 1)
    with pytest.raises(
        ValueError, match=r"Cannot write format_version .*writable versions: \['1.0'"
    ):
        bundle.to_hdf5(str(tmp_path / "f.hdf5"), format_version=version)  # type: ignore[arg-type]
    assert not (tmp_path / "f.hdf5").exists()


# ── Recording.to_hdf5 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_a_recording_can_choose_its_version_too(tmp_path: Path, channels: int) -> None:
    recording = Recording.from_hdf5(str(DATA_DIR / hdf5_name("1.0", channels)))
    recording.to_hdf5(str(tmp_path / "a.hdf5"))
    recording.to_hdf5(str(tmp_path / "b.hdf5"), format_version="1.4")
    with h5py.File(tmp_path / "a.hdf5") as a, h5py.File(tmp_path / "b.hdf5") as b:
        assert (
            a.attrs["icoschema_format_version"],
            b.attrs["icoschema_format_version"],
        ) == ("1.0", "1.4")
    assert (
        Recording.from_hdf5(str(tmp_path / "b.hdf5")).only_source().recording_data
        == recording.only_source().recording_data
    )

    two = Recording.from_hdf5(str(DATA_DIR / hdf5_name("1.3", channels, True)))
    with pytest.raises(ValueError, match="it has 2 sources"):
        two.to_hdf5(str(tmp_path / "c.hdf5"), format_version="1.2")
