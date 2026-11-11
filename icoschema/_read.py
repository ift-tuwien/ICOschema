"""Open a file of any schema version as the latest one (`icoschema.read`).

Version-neutral, like `_schemas.py`: it knows which schema version a file is of and how to bring an older one to
the latest. When a schema version becomes the latest (see doc/adding-a-schema-version.md), add the migration from
its predecessor to `_MIGRATIONS`.
"""

from collections.abc import Callable
from typing import Any

from . import _schemas, migrate, v1


def schema_version_of_file(path: str) -> int:
    """The schema version (1, 2, ...) of the HDF5 or TDMS file at `path`, without reading its data. Raises
    `ValueError` for another kind of file or a schema version this package doesn't have."""
    return _schemas.file_schema_version(path)


def _v1_file_as_v2(path: str) -> Any:
    bundle = v1.DatasetBundle.from_file(path)
    try:
        stored = migrate.stored_scalings_of(path, bundle)
    except OSError:  # not an HDF5 file (TDMS): nothing stored
        stored = {}
    return migrate.v1_to_v2(bundle, stored_scalings=stored)


# (schema version of the file, latest schema version) -> reads the file as the latest
_MIGRATIONS: dict[tuple[int, int], Callable[[str], Any]] = {
    (1, 2): _v1_file_as_v2,
}


def read(path: str) -> Any:
    """The `DatasetBundle` of the HDF5 or TDMS file at `path`, whatever schema version it was written with, as
    the latest schema version's (`icoschema.DatasetBundle`). A file of an older schema version is migrated by
    `icoschema.migrate` (for v1 -> v2: every channel becomes a `LinearConversion`, see there), so its conversions
    follow those rules, not the original ones. To keep a file's own version, use
    `icoschema.schema_version_of_file` and that version's namespace (`icoschema.v1`, ...)."""
    version = _schemas.file_schema_version(path)
    if version == _schemas.LATEST:
        return _schemas.schema(version).DatasetBundle.from_file(path)
    try:
        migration = _MIGRATIONS[(version, _schemas.LATEST)]
    except KeyError:
        raise ValueError(
            f"No migration from schema version {version} to {_schemas.LATEST}; read it with "
            f"icoschema.v{version}"
        ) from None
    return migration(path)
