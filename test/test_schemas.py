"""What holds for every schema version (`icoschema.v1`, `icoschema.v2`, ...) and for the pointer to the latest.

Nothing here names a particular version: adding one to `icoschema._schemas.SCHEMA_MODULES` puts it under these
tests. The tests of one version's behaviour are in `test/vN/`."""

import ast
import importlib
from pathlib import Path

import h5py
import pytest

import icoschema
from icoschema import _schemas

PACKAGE_DIR = Path(icoschema.__file__).resolve().parent
VERSIONS = sorted(_schemas.SCHEMA_MODULES)
V1_DATA = Path(__file__).resolve().parent / "v1" / "data"


def test_every_schema_version_is_registered_and_the_other_way_round() -> None:
    on_disk = sorted(
        int(p.name[1:])
        for p in PACKAGE_DIR.iterdir()
        if p.is_dir() and p.name[0] == "v" and p.name[1:].isdigit()
    )
    assert on_disk == VERSIONS
    assert {v: f"icoschema.v{v}" for v in VERSIONS} == _schemas.SCHEMA_MODULES


@pytest.mark.parametrize("version", VERSIONS)
def test_a_schema_version_is_importable_from_the_package(version: int) -> None:
    module = _schemas.schema(version)
    assert module is importlib.import_module(f"icoschema.v{version}")
    assert getattr(icoschema, f"v{version}") is module


# ── the pointer to the latest ────────────────────────────────────────────────


def test_the_latest_is_the_newest_version() -> None:
    assert _schemas.LATEST == max(VERSIONS)


def test_the_top_level_names_are_those_of_the_latest_schema_version() -> None:
    latest = _schemas.schema(_schemas.LATEST)
    names = [
        name
        for name in icoschema.__all__
        if not (name[0] == "v" and name[1:].isdigit())
    ]
    assert names  # not vacuous
    for name in names:
        assert getattr(icoschema, name) is getattr(latest, name), name


# ── each version is self-contained, so that the next one can start as a copy ─


def _imports(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            yield node.level, node.module or "", node.lineno
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield 0, alias.name, node.lineno


@pytest.mark.parametrize("version", VERSIONS)
def test_a_schema_version_only_imports_itself_relatively(version: int) -> None:
    root = PACKAGE_DIR / f"v{version}"
    allowed_absolute = {"icoschema._version"}  # version-neutral
    problems = []
    for path in root.rglob("*.py"):
        depth = len(
            path.relative_to(root).parent.parts
        )  # how far below the version's package
        for level, module, line in _imports(path):
            where = f"{path.relative_to(PACKAGE_DIR.parent)}:{line}"
            if (
                level == 0
                and (module == "icoschema" or module.startswith("icoschema."))
                and module not in allowed_absolute
            ):
                problems.append(f"{where}: absolute import of {module}")
            if level - 1 > depth:
                problems.append(
                    f"{where}: relative import leaves the version's package"
                )
    assert not problems, "\n".join(problems)


# ── which schema version a file is of ────────────────────────────────────────


@pytest.mark.parametrize(
    ("format_version", "expected"),
    [(None, 1), ("legacy", 1), ("1.0", 1), ("1.4", 1), ("2.0", 2), ("10.3", 10)],
)
def test_the_schema_version_of_a_format_version(
    format_version: str | None, expected: int
) -> None:
    assert _schemas.schema_version_of(format_version) == expected


def test_a_nonsense_format_version_is_refused() -> None:
    with pytest.raises(ValueError, match="Not an icoschema format version"):
        _schemas.schema_version_of("latest")


@pytest.mark.parametrize("path", sorted(V1_DATA.iterdir()), ids=lambda p: p.name)
def test_the_stored_files_are_of_schema_version_1(path: Path) -> None:
    assert _schemas.file_schema_version(str(path)) == 1


def test_a_file_of_an_unknown_schema_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "f.hdf5"
    path.write_bytes((V1_DATA / "hdf5_1.0_1ch.hdf5").read_bytes())
    unknown = max(VERSIONS) + 1
    with h5py.File(path, "r+") as f:
        f.attrs["icoschema_format_version"] = f"{unknown}.0"
    with pytest.raises(ValueError, match=f"Unsupported schema version {unknown}"):
        _schemas.file_schema_version(str(path))


def test_a_file_that_is_neither_hdf5_nor_tdms_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "f.txt"
    path.write_text("hello world")
    with pytest.raises(ValueError, match="neither an HDF5 nor a TDMS file"):
        _schemas.file_schema_version(str(path))


def test_an_unknown_schema_version_has_no_module() -> None:
    with pytest.raises(ValueError, match="Unsupported schema version 99"):
        _schemas.schema(99)
