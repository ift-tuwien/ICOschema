"""`icoschema.read`: any file, of any schema version, as the latest schema version's bundle."""

from pathlib import Path

import pytest

import icoschema
from icoschema import _schemas, migrate, v1, v2

ROOT = Path(__file__).resolve().parent
V1_FILES = sorted((ROOT / "v1" / "data").iterdir()) + [ROOT / "v1" / "test_with_sensors.hdf5"]
# (a TDMS file has no format version, so it counts as schema version 1 whatever wrote it)
V2_FILES = sorted((ROOT / "v2" / "data").glob("*.hdf5")) + [ROOT / "v2" / "test_with_sensors.hdf5"]
TDMS_FILES = sorted((ROOT / "v2" / "data").glob("*.tdms"))


def test_the_schema_version_of_a_file() -> None:
    assert icoschema.schema_version_of_file(str(V1_FILES[0])) == 1
    assert icoschema.schema_version_of_file(str(V2_FILES[0])) == 2


def test_a_file_that_is_neither_hdf5_nor_tdms_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "x.txt"
    path.write_text("hello")
    with pytest.raises(ValueError, match="neither an HDF5 nor a TDMS file"):
        icoschema.read(str(path))


@pytest.mark.parametrize("path", V2_FILES, ids=lambda p: p.name)
def test_a_latest_file_is_read_as_it_is(path: Path) -> None:
    bundle = icoschema.read(str(path))
    assert type(bundle) is _schemas.schema(_schemas.LATEST).DatasetBundle
    assert bundle == _schemas.schema(_schemas.LATEST).DatasetBundle.from_file(str(path))


@pytest.mark.parametrize("path", V1_FILES, ids=lambda p: p.name)
def test_an_older_file_is_read_as_the_latest(path: Path) -> None:
    bundle = icoschema.read(str(path))
    assert type(bundle) is v2.DatasetBundle
    for source in bundle.recording.sources.values():
        for slot in ("channel1_metadata", "channel2_metadata", "channel3_metadata"):
            metadata = getattr(source.hardware_metadata, slot)
            if metadata is not None:
                assert isinstance(metadata.conversion, v2.LinearConversion)


def test_an_older_file_is_read_with_its_stored_scalings() -> None:
    path = str(ROOT / "v1" / "test_with_sensors.hdf5")  # says conversion = "true", has scaling 75.757576 / -125
    source = next(iter(icoschema.read(path).recording.sources.values()))
    conversion = source.hardware_metadata.channel1_metadata.conversion
    assert conversion.gain == pytest.approx(75.757576, rel=1e-6)
    assert conversion.offset == pytest.approx(-125.0, rel=1e-6)
    # the same as converting the file
    bundle = v1.DatasetBundle.from_file(path)
    stored = migrate.stored_scalings_of(path, bundle)
    assert migrate.v1_to_v2(bundle, stored_scalings=stored) == icoschema.read(path)


@pytest.mark.parametrize("path", TDMS_FILES, ids=lambda p: p.name)
def test_a_tdms_file_is_schema_version_one_and_read_as_the_latest(path: Path) -> None:
    assert icoschema.schema_version_of_file(str(path)) == 1
    bundle = icoschema.read(str(path))
    assert type(bundle) is v2.DatasetBundle
    assert list(bundle.recording.sources) == list(v1.DatasetBundle.from_file(str(path)).recording.sources)
