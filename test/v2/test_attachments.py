"""Pictures, embedded files, and keeping everything a file has that the package doesn't model."""

import logging
import shutil
from pathlib import Path

import h5py
import numpy as np
import pytest

from icoschema.v2 import DatasetBundle, EmbeddedFile, attachments

from .synthetic_files import DATA_DIR, hdf5_name

PACKETS = str(DATA_DIR / hdf5_name("packets", 1))
MULTI = str(DATA_DIR / hdf5_name("multi", 1))


def copy(tmp_path: Path, source: str, name: str = "file.hdf5") -> str:
    target = tmp_path / name
    shutil.copy(source, target)
    return str(target)


def version(path: str) -> str:
    with h5py.File(path) as f:
        return str(f.attrs["icoschema_format_version"])


# ── the bundle API ───────────────────────────────────────────────────────────


def test_pictures_and_files_are_stored_in_groups(tmp_path: Path) -> None:
    bundle = (
        DatasetBundle.from_hdf5(PACKETS)
        .with_picture("post__pictures", ["aGVsbG8=", "d29ybGQ="])
        .with_file("report", b"abc", mime="application/pdf", original_name="Report 1.pdf")
    )
    path = str(tmp_path / "out.hdf5")
    bundle.to_hdf5(path)

    assert version(path) == "2.0"
    with h5py.File(path) as f:
        assert f["pictures/post__pictures"][()].tolist() == [b"aGVsbG8=", b"d29ybGQ="]
        assert f["files/report"][()].tobytes() == b"abc"
        assert (f["files/report"].attrs["size"], f["files/report"].attrs["mime"]) == (3, "application/pdf")
        assert f["files/report"].attrs["original_name"] == "Report 1.pdf"

    again = DatasetBundle.from_hdf5(path)
    assert again.pictures == bundle.pictures and again.files == bundle.files


def test_a_bundle_without_them_has_no_groups(tmp_path: Path) -> None:
    path = str(tmp_path / "out.hdf5")
    DatasetBundle.from_hdf5(PACKETS).to_hdf5(path)
    assert version(path) == "2.0"
    with h5py.File(path) as f:
        assert "pictures" not in f and "files" not in f


def test_attachments_survive_every_with_method() -> None:
    bundle = DatasetBundle.from_hdf5(PACKETS).with_picture("p", ["x"]).with_file("f", b"1")
    changed = bundle.without_preprocessed().without_steps([str(step.node) for step in bundle.steps])
    assert changed.pictures == {"p": ["x"]} and changed.files["f"].content == b"1"
    assert changed.with_recording(bundle.recording).pictures == {"p": ["x"]}


def test_names_are_checked_and_duplicates_need_overwrite() -> None:
    bundle = DatasetBundle.from_hdf5(PACKETS).with_file("f", b"1").with_picture("p", ["x"])
    for bad in ("", "a/b", ".hidden"):
        with pytest.raises(ValueError, match="must be non-empty"):
            bundle.with_file(bad, b"")
        with pytest.raises(ValueError, match="must be non-empty"):
            bundle.with_picture(bad, [])
    with pytest.raises(ValueError, match="already exists"):
        bundle.with_file("f", b"2")
    with pytest.raises(ValueError, match="already exists"):
        bundle.with_picture("p", ["y"])
    assert bundle.with_file("f", b"2", overwrite=True).files["f"].content == b"2"
    assert bundle.without_file("f").files == {} and bundle.without_picture("p").pictures == {}
    with pytest.raises(ValueError, match="no such file"):
        bundle.without_file("nope")


def test_an_empty_file_and_an_empty_picture_set_round_trip(tmp_path: Path) -> None:
    path = str(tmp_path / "empty.hdf5")
    DatasetBundle.from_hdf5(PACKETS).with_file("empty", b"").with_picture("none", []).to_hdf5(path)
    again = DatasetBundle.from_hdf5(path)
    assert again.files["empty"] == EmbeddedFile(b"", "application/octet-stream", "empty")
    assert again.pictures["none"] == []


# ── in place ─────────────────────────────────────────────────────────────────


def test_a_file_is_changed_in_place(tmp_path: Path) -> None:
    path = copy(tmp_path, PACKETS)
    attachments.add_file(path, "notes", b"hello", mime="text/plain", original_name="my notes.txt")
    attachments.add_picture(path, "pre__pictures", ["aW1n"])
    assert version(path) == "2.0"

    assert attachments.list_files(path) == [attachments.EmbeddedFileInfo("notes", 5, "text/plain", "my notes.txt")]
    assert attachments.read_file(path, "notes") == EmbeddedFile(b"hello", "text/plain", "my notes.txt")
    assert attachments.read_pictures(path) == {"pre__pictures": ["aW1n"]}
    assert DatasetBundle.from_hdf5(path).files["notes"].content == b"hello"

    with pytest.raises(ValueError, match="already exists"):
        attachments.add_file(path, "notes", b"x")
    attachments.add_file(path, "notes", b"new", overwrite=True)
    assert attachments.read_file(path, "notes").content == b"new"

    attachments.remove_file(path, "notes")
    assert attachments.list_files(path) == []
    with pytest.raises(KeyError):
        attachments.remove_file(path, "notes")
    with pytest.raises(KeyError):
        attachments.read_file(path, "notes")


def test_in_place_leaves_the_recording_alone(tmp_path: Path) -> None:
    path = copy(tmp_path, MULTI)
    before = DatasetBundle.from_hdf5(path).recording
    attachments.add_file(path, "f", b"1")
    assert DatasetBundle.from_hdf5(path).recording.sources.keys() == before.sources.keys()
    assert DatasetBundle.from_hdf5(path).recording.sources["stu1"] == before.sources["stu1"]


def test_a_file_of_schema_version_1_is_refused_in_place(tmp_path: Path) -> None:
    legacy = copy(tmp_path, str(DATA_DIR.parent.parent / "v1" / "data" / "hdf5_legacy_1ch.hdf5"), "legacy.hdf5")
    with pytest.raises(ValueError, match="not a file of schema version 2"):
        attachments.add_file(legacy, "f", b"1")
    with pytest.raises(ValueError, match="not a file of schema version 2"):
        attachments.list_files(legacy)


# ── pictures and files where the data acquisition stored them ───────────────


def legacy_layout(path: str) -> None:
    """Add what a file from the data acquisition has: picture arrays at the root, `/embedded_files/`."""
    with h5py.File(path, "r+") as f:
        f.create_dataset("post__pictures", data=np.array([b"aGVsbG8=", b"d29ybGQ="], dtype="S8"))
        f.create_dataset("pre__tool_pictures", data=np.array([b"dG9vbA=="], dtype="S8"))
        group = f.create_group("embedded_files")
        data = group.create_dataset("report", data=np.frombuffer(b"%PDF", dtype=np.uint8))
        data.attrs["size"], data.attrs["mime"], data.attrs["original_name"] = 4, "application/pdf", "Report.pdf"


def test_old_places_are_read_and_saving_moves_them_into_the_groups(tmp_path: Path) -> None:
    path = copy(tmp_path, PACKETS)
    legacy_layout(path)
    bundle = DatasetBundle.from_hdf5(path)
    assert bundle.pictures == {"post__pictures": ["aGVsbG8=", "d29ybGQ="], "pre__tool_pictures": ["dG9vbA=="]}
    assert bundle.files == {"report": EmbeddedFile(b"%PDF", "application/pdf", "Report.pdf")}
    assert not bundle.preserved  # nothing is left over: all of it was understood

    saved = str(tmp_path / "saved.hdf5")
    bundle.to_hdf5(saved)
    assert version(saved) == "2.0"
    with h5py.File(saved) as f:
        assert "post__pictures" not in f and "embedded_files" not in f
        assert set(f["pictures"]) == {"post__pictures", "pre__tool_pictures"} and set(f["files"]) == {"report"}
    again = DatasetBundle.from_hdf5(saved)
    assert again.pictures == bundle.pictures and again.files == bundle.files


# ── nothing is dropped ───────────────────────────────────────────────────────


def with_extras(path: str) -> None:
    with h5py.File(path, "r+") as f:
        f.attrs["operator"] = "someone"
        f.attrs["vlen"] = ["a", "bb"]
        f[f.attrs["primary_table"]].attrs["tool_name"] = "Cutter 3"
        f[f.attrs["primary_table"]].attrs["start_supply_voltage"] = 4.12
        f[f.attrs["primary_table"]].attrs["flag"] = np.int8(1)
        notes = f.create_group("notes")
        notes.attrs["author"] = "me"
        notes.create_dataset("text", data="hello")
        notes.create_dataset("table", data=np.array([(1, 2.5), (2, 3.5)], dtype=[("a", "i4"), ("b", "f8")])).attrs["x"] = 1
        f.create_dataset("scratch", data=np.arange(100, dtype="<i2"))
        f["alias"] = h5py.SoftLink("/scratch")
        f[f.attrs["primary_table"]].attrs["empty"] = h5py.Empty("f")


def check_extras(path: str) -> None:
    with h5py.File(path) as f:
        assert f.attrs["operator"] == "someone" and list(f.attrs["vlen"]) == ["a", "bb"]
        table = f[f.attrs["primary_table"]]
        assert table.attrs["tool_name"] == "Cutter 3" and float(table.attrs["start_supply_voltage"]) == 4.12
        assert table.attrs["flag"] == 1 and table.attrs["flag"].dtype == np.int8
        assert isinstance(table.attrs["empty"], h5py.Empty)
        assert f["notes"].attrs["author"] == "me" and f["notes/text"][()] == b"hello"
        assert f["notes/table"][()].tolist() == [(1, 2.5), (2, 3.5)] and f["notes/table"].attrs["x"] == 1
        np.testing.assert_array_equal(f["scratch"][()], np.arange(100, dtype="<i2"))
        assert f["scratch"].dtype == np.dtype("<i2")
        assert isinstance(f.get("alias", getlink=True), h5py.SoftLink) and f.get("alias", getlink=True).path == "/scratch"


def test_unknown_attributes_and_nodes_survive_a_round_trip(tmp_path: Path, caplog) -> None:
    path = copy(tmp_path, PACKETS)
    with_extras(path)
    with caplog.at_level(logging.WARNING):
        bundle = DatasetBundle.from_hdf5(path)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert bundle.preserved

    out = str(tmp_path / "out.hdf5")
    bundle.to_hdf5(out)
    check_extras(out)
    # ... and again: what is written is read as it was
    again = str(tmp_path / "again.hdf5")
    DatasetBundle.from_hdf5(out).to_hdf5(again)
    check_extras(again)


def test_unknown_parts_of_a_multi_source_file_stay_in_their_source(tmp_path: Path) -> None:
    path = copy(tmp_path, MULTI)
    with h5py.File(path, "r+") as f:
        f["sources/stu2"].create_dataset("raw_log", data=np.array([b"a", b"b"]))
        f["sources/stu2/recording"].attrs["note"] = "second"
        f["sources"].create_group("unlisted").attrs["why"] = "not a source"
    out = str(tmp_path / "out.hdf5")
    DatasetBundle.from_hdf5(path).to_hdf5(out)
    with h5py.File(out) as f:
        assert f["sources/stu2/raw_log"][()].tolist() == [b"a", b"b"]
        assert f["sources/stu2/recording"].attrs["note"] == "second"
        assert f["sources/unlisted"].attrs["why"] == "not a source"
        assert "raw_log" not in f["sources/stu1"]


def test_a_malformed_computation_and_a_malformed_step_are_kept(tmp_path: Path, caplog) -> None:
    path = copy(tmp_path, PACKETS)
    with h5py.File(path, "r+") as f:
        f.require_group("computations").create_dataset("broken", data=np.zeros(3)).attrs["unit"] = np.zeros((2, 2))
        f.require_group("computations/deep/er").create_dataset("kept", data=np.arange(4))
        f.require_group("steps").create_dataset("not_a_step", data=np.arange(3))
        f["steps/not_a_step"].attrs["note"] = "x"
        f["computations/deep"].attrs["why"] = "grouped"
    # (the dataset `broken` is readable; make it malformed in the way the reader refuses)
    with caplog.at_level(logging.WARNING):
        bundle = DatasetBundle.from_hdf5(path)
    out = str(tmp_path / "out.hdf5")
    bundle.to_hdf5(out)
    with h5py.File(out) as f:
        assert f["steps/not_a_step"].attrs["note"] == "x"
        assert f["computations/deep"].attrs["why"] == "grouped"
        assert f["computations/deep/er/kept"][()].tolist() == [0, 1, 2, 3]


def test_a_sensors_table_with_more_columns_is_kept_next_to_the_new_one(tmp_path: Path) -> None:
    path = copy(tmp_path, PACKETS)
    with h5py.File(path, "r+") as f:
        old = f["sensors"][()]
        columns = [(name, old.dtype[name]) for name in old.dtype.names] + [("channel_number", "u1")]
        widened = np.zeros(old.shape, dtype=columns)
        for name in old.dtype.names:
            widened[name] = old[name]
        widened["channel_number"] = 7
        del f["sensors"]
        f.create_dataset("sensors", data=widened)
    out = str(tmp_path / "out.hdf5")
    DatasetBundle.from_hdf5(path).to_hdf5(out)
    with h5py.File(out) as f:
        assert "channel_number" not in f["sensors"].dtype.names
        assert f["sensors__original"]["channel_number"].tolist() == [7]


def test_a_name_that_is_taken_keeps_the_preserved_node_next_to_it(tmp_path: Path) -> None:
    path = copy(tmp_path, PACKETS)
    with h5py.File(path, "r+") as f:
        f.create_dataset("pictures", data=np.arange(3))  # not a picture set, but in the name the group needs
    out = str(tmp_path / "out.hdf5")
    DatasetBundle.from_hdf5(path).with_picture("p", ["x"]).to_hdf5(out)
    with h5py.File(out) as f:
        assert f["pictures/p"][()].tolist() == [b"x"]
        assert f["pictures__preserved"][()].tolist() == [0, 1, 2]


def test_pytables_bookkeeping_of_modelled_nodes_is_not_carried(tmp_path: Path) -> None:
    path = copy(tmp_path, PACKETS)
    with h5py.File(path, "r+") as f:
        f[f.attrs["primary_table"]].attrs["CLASS"] = "TABLE"
        f[f.attrs["primary_table"]].attrs["FIELD_0_NAME"] = "counter"
    bundle = DatasetBundle.from_hdf5(path)
    assert not bundle.preserved.attrs.get("{primary}", {})
