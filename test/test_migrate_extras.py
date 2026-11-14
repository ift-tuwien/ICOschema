"""Migrating a file of schema version 1 (as the data acquisition writes them) keeps everything it has."""

import shutil
from pathlib import Path

import h5py
import numpy as np
import pytest

import icoschema
from icoschema import migrate

V1_DATA = Path(__file__).parent / "v1" / "data"
LEGACY = str(V1_DATA / "hdf5_legacy_1ch.hdf5")
V14_MULTI = str(V1_DATA / "hdf5_1.4_1ch_multi.hdf5")


def acquisition_file(tmp_path: Path, source: str = LEGACY) -> str:
    """A copy of `source` with what the data acquisition adds: attributes of its own on the table, a sensors
    column, picture arrays at the root and embedded files."""
    path = str(tmp_path / "acquired.hdf5")
    shutil.copy(source, path)
    with h5py.File(path, "r+") as f:
        table = f["acceleration"]
        table.attrs["sth_mac_address"] = "14-2D-41-D7-77-7D"
        table.attrs["tool_name"] = "Cutter 3"
        table.attrs["start_supply_voltage"] = "4.12"
        old = f["sensors"][()]
        columns = [(name, old.dtype[name]) for name in old.dtype.names] + [("channel_number", "u1")]
        widened = np.zeros(old.shape, dtype=columns)
        for name in old.dtype.names:
            widened[name] = old[name]
        widened["channel_number"] = 3
        del f["sensors"]
        f.create_dataset("sensors", data=widened)
        f.create_dataset("post__pictures", data=np.array([b"aGVsbG8="], dtype="S8"))
        files = f.create_group("embedded_files")
        data = files.create_dataset("notes", data=np.frombuffer(b"text", dtype=np.uint8))
        data.attrs["size"], data.attrs["mime"], data.attrs["original_name"] = 4, "text/plain", "notes.txt"
        f.create_group("pre__custom").attrs["x"] = 1
    return path


def test_reading_a_legacy_file_as_the_latest_version_brings_everything_along(tmp_path: Path) -> None:
    path = acquisition_file(tmp_path)
    bundle = icoschema.read(path)
    assert bundle.pictures == {"post__pictures": ["aGVsbG8="]}
    assert bundle.files["notes"].content == b"text" and bundle.files["notes"].original_name == "notes.txt"
    assert bundle.preserved.attrs["{primary}"]["tool_name"].value == "Cutter 3"
    assert set(bundle.preserved.nodes) >= {"pre__custom", "sensors__original"}

    out = str(tmp_path / "out.hdf5")
    bundle.to_hdf5(out)
    with h5py.File(out) as f:
        assert f.attrs["icoschema_format_version"] == "2.0"
        table = f[f.attrs["primary_table"]]
        assert table.attrs["tool_name"] == "Cutter 3" and table.attrs["sth_mac_address"] == "14-2D-41-D7-77-7D"
        assert f["pictures/post__pictures"][()].tolist() == [b"aGVsbG8="]
        assert f["files/notes"][()].tobytes() == b"text"
        assert f["pre__custom"].attrs["x"] == 1
        assert f["sensors__original"]["channel_number"].tolist() == [3]
        assert "post__pictures" not in f and "embedded_files" not in f
    assert icoschema.read(out).files == bundle.files


def test_convert_file_does_the_same(tmp_path: Path) -> None:
    path = acquisition_file(tmp_path)
    out = str(tmp_path / "converted.hdf5")
    migrate.convert_file(path, out)
    again = icoschema.read(out)
    assert again.pictures == {"post__pictures": ["aGVsbG8="]} and "notes" in again.files
    with h5py.File(out) as f:
        assert f[f.attrs["primary_table"]].attrs["tool_name"] == "Cutter 3"


def test_what_the_migration_turns_into_something_else_is_not_carried(tmp_path: Path) -> None:
    """The table-wide `conversion` flag and the range columns become each channel's `LinearConversion`."""
    bundle = icoschema.read(acquisition_file(tmp_path))
    assert "conversion" not in bundle.preserved.attrs.get("{primary}", {})
    assert bundle.preserved.nodes["sensors__original"].kind == "dataset"


def test_a_file_without_anything_extra_is_converted_as_before(tmp_path: Path) -> None:
    bundle = icoschema.read(LEGACY)
    assert not bundle.pictures and not bundle.files
    out = str(tmp_path / "plain.hdf5")
    bundle.to_hdf5(out)
    with h5py.File(out) as f:
        assert f.attrs["icoschema_format_version"] == "2.0"


def test_a_multi_source_file_keeps_unknown_nodes_in_the_source_group(tmp_path: Path) -> None:
    path = str(tmp_path / "multi.hdf5")
    shutil.copy(V14_MULTI, path)
    with h5py.File(path, "r+") as f:
        names = [n.decode() if isinstance(n, bytes) else n for n in f.attrs["sources"]]
        f[f"sources/{names[1]}"].create_dataset("log", data=np.array([b"x"]))
        f.create_dataset("root_picture_set", data=np.array([b"cGlj"], dtype="S4"))
    bundle = icoschema.read(path)
    assert bundle.pictures == {"root_picture_set": ["cGlj"]}
    out = str(tmp_path / "out.hdf5")
    bundle.to_hdf5(out)
    with h5py.File(out) as f:
        assert f[f"sources/{names[1]}/log"][()].tolist() == [b"x"]


def test_a_tdms_file_has_nothing_extra() -> None:
    bundle = icoschema.read(str(V1_DATA / "tdms_legacy_1ch.tdms"))
    assert not bundle.pictures and not bundle.files and not bundle.preserved


def converted_acquisition_file(tmp_path: Path) -> str:
    """What the data acquisition writes: values converted to the unit of the sensor, the table-wide flag saying
    so, and the sensor's range and scaling in the `sensors` table."""
    path = str(tmp_path / "converted.hdf5")
    shutil.copy(LEGACY, path)
    with h5py.File(path, "r+") as f:
        f["acceleration"].attrs["conversion"] = "true"
        sensors = f["sensors"][()]
        for name, value in (
            ("phys_min", -50.0),
            ("phys_max", 50.0),
            ("volt_min", 0.0),
            ("volt_max", 3.3),
            ("scaling_factor", 100.0 / 3.3),
            ("offset", -50.0),
        ):
            sensors[name] = value
        f["sensors"][...] = sensors
    return path


def test_a_file_with_ranges_in_its_sensors_table_is_converted_already(tmp_path: Path) -> None:
    """Its values stay as they are; the conversion records what the acquisition did to the raw volts."""
    path = converted_acquisition_file(tmp_path)
    with h5py.File(path) as f:
        stored = f["acceleration"][()]
    channel_name = next(name for name in stored.dtype.names if name not in ("counter", "timestamp"))

    source = icoschema.read(path).recording.only_source()
    conversion = source.hardware_metadata.channel1_metadata.conversion
    assert isinstance(conversion, icoschema.v2.LinearConversion)
    assert conversion.gain == pytest.approx(100.0 / 3.3) and conversion.offset == pytest.approx(-50.0)
    np.testing.assert_array_equal(source.channel1, stored[channel_name].astype(np.float32))  # not converted again
