"""The schema versions in this package, and which one is the latest.

Every schema version is a self-contained package (`icoschema.v1`, `icoschema.v2`, ...): its LinkML schema, the
generated classes, the model classes and the file readers/writers, importing each other only relatively. This
module is the only version-neutral code that knows them, and holds the pointer to the latest one. To add a
version, see doc/adding-a-schema-version.md.

A file says which schema version it was written with in its `icoschema_format_version` (HDF5 root attribute, TDMS
root property): the part before the dot is the schema version ("1.4" is a layout of schema version 1), and a
file without one is of schema version 1. That attribute's name and meaning stay the same across schema versions,
as it is what picks the version to read a file with.
"""

import importlib
from pathlib import Path
from types import ModuleType

# The schema versions of this package: add the new one here (and nothing else about it).
SCHEMA_MODULES: dict[int, str] = {
    1: "icoschema.v1",
}

# The latest schema version: what the top-level `icoschema` names stand for. Move it together with the imports
# in icoschema/__init__.py (a test checks that they agree).
LATEST: int = 1

FORMAT_VERSION_NAME = "icoschema_format_version"
_HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"
_TDMS_SIGNATURE = b"TDSm"


def schema(version: int) -> ModuleType:
    """The module of schema version `version` (`icoschema.v1`, ...). Raises `ValueError` for one this package
    doesn't have, e.g. when a file was written by a newer `icoschema`."""
    if version not in SCHEMA_MODULES:
        raise ValueError(
            f"Unsupported schema version {version}; supported versions: {sorted(SCHEMA_MODULES)}"
        )
    return importlib.import_module(SCHEMA_MODULES[version])


def schema_version_of(format_version: str | None) -> int:
    """The schema version a file format version belongs to (`None`, a file without one, is schema version 1)."""
    if format_version is None or format_version == "legacy":
        return 1
    major = str(format_version).partition(".")[0]
    if not major.isdigit():
        raise ValueError(f"Not an icoschema format version: {format_version!r}")
    return int(major)


def file_schema_version(path: str) -> int:
    """The schema version of the HDF5 or TDMS file at `path`, told by the file's first bytes and its
    `icoschema_format_version`, without reading anything else. Raises `ValueError` for another kind of file or
    for a schema version this package doesn't have."""
    with Path(path).open("rb") as file:
        head = file.read(8)
    if head == _HDF5_SIGNATURE:
        import h5py

        with h5py.File(path, "r") as f:
            raw = f.attrs.get(FORMAT_VERSION_NAME)
        version = raw.decode() if isinstance(raw, bytes) else raw
    elif head.startswith(_TDMS_SIGNATURE):
        import tdmspy

        raw = tdmspy.read(path).properties.get(FORMAT_VERSION_NAME)
        version = None if raw is None else str(raw)
    else:
        raise ValueError(f"{path!r} is neither an HDF5 nor a TDMS file")
    found = schema_version_of(version)
    schema(found)  # raises if this package doesn't know it
    return found
