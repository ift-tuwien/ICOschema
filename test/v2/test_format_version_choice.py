"""Choosing the HDF5 file format version when writing (`to_hdf5(format_version=...)`), against the stored
synthetic files in `test/v2/data/`. Schema version 2 has a single format version, "2.0", that holds everything: the
files of the other versions are those of schema version 1 (see `icoschema.v1`)."""

import typing
from pathlib import Path

import h5py
import pytest

from icoschema import v2
from icoschema.v2 import DatasetBundle, Recording
from icoschema.v2.storage import hdf5 as hdf5_storage

from .synthetic_files import (
    CHANNEL_COUNTS,
    DATA_DIR,
    HDF5_WRITERS,
    hdf5_name,
    tdms_name,
)

WRITABLE = v2.hdf5_format_versions(writable=True)
STORED = [hdf5_name(kind, channels) for kind in HDF5_WRITERS for channels in CHANNEL_COUNTS] + [
    tdms_name(channels, multi) for channels in CHANNEL_COUNTS for multi in (False, True)
]


def stored_bundle(name: str) -> DatasetBundle:
    read = DatasetBundle.from_hdf5 if name.endswith(".hdf5") else DatasetBundle.from_tdms
    return read(str(DATA_DIR / name))


# ── the registry ─────────────────────────────────────────────────────────────


def test_the_typed_versions_are_the_writable_ones() -> None:
    assert typing.get_args(hdf5_storage.FormatVersion) == WRITABLE == ("2.0",)


def test_the_readable_versions_are_the_writable_ones() -> None:
    assert v2.hdf5_format_versions() == WRITABLE


# ── writing each file ────────────────────────────────────────────────────────


@pytest.mark.parametrize("name", STORED)
def test_the_default_and_the_chosen_version_agree(tmp_path: Path, name: str) -> None:
    bundle = stored_bundle(name)
    bundle.to_hdf5(str(tmp_path / "default.hdf5"))
    bundle.to_hdf5(str(tmp_path / "chosen.hdf5"), format_version="2.0")
    for file in ("default.hdf5", "chosen.hdf5"):
        with h5py.File(tmp_path / file) as f:
            assert f.attrs["icoschema_format_version"] == "2.0"
        again = DatasetBundle.from_hdf5(str(tmp_path / file))
        assert again.recording.sources.keys() == bundle.recording.sources.keys()
        assert again.preprocessed_tables == bundle.preprocessed_tables
        assert again.steps == bundle.steps
        assert again.computations == bundle.computations


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_a_single_source_is_at_the_root_and_several_are_under_sources(tmp_path: Path, channels: int) -> None:
    stored_bundle(hdf5_name("packets", channels)).to_hdf5(str(tmp_path / "one.hdf5"))
    stored_bundle(hdf5_name("multi", channels)).to_hdf5(str(tmp_path / "two.hdf5"))
    with h5py.File(tmp_path / "one.hdf5") as one, h5py.File(tmp_path / "two.hdf5") as two:
        assert "sources" not in one.attrs and "recording" in one
        assert list(two.attrs["sources"]) == ["stu1", "stu2"] and "sources" in two


# ── bad requests ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("version", ["1.0", "1.2", "1.3", "1.4", "legacy", "2.1", "3.0", "2", ""])
def test_a_version_that_cannot_be_written_is_refused_with_the_writable_ones(tmp_path: Path, version: str) -> None:
    bundle = stored_bundle(hdf5_name("packets", 1))
    with pytest.raises(ValueError, match=r"Cannot write format_version .*writable versions: \['2.0'\]"):
        bundle.to_hdf5(str(tmp_path / "f.hdf5"), format_version=version)  # type: ignore[arg-type]
    assert not (tmp_path / "f.hdf5").exists()


# ── Recording.to_hdf5 ────────────────────────────────────────────────────────


@pytest.mark.parametrize("channels", CHANNEL_COUNTS)
def test_a_recording_can_choose_its_version_too(tmp_path: Path, channels: int) -> None:
    recording = Recording.from_hdf5(str(DATA_DIR / hdf5_name("multi", channels)))
    recording.to_hdf5(str(tmp_path / "a.hdf5"), format_version="2.0")
    assert Recording.from_hdf5(str(tmp_path / "a.hdf5")) == recording
    with pytest.raises(ValueError, match="Cannot write format_version '1.4'"):
        recording.to_hdf5(str(tmp_path / "b.hdf5"), format_version="1.4")  # type: ignore[arg-type]
