# Adding a schema version

Every schema version is a self-contained package, `icoschema/vN/`, with its own LinkML schema, generated classes,
model classes and file readers/writers; its tests are in `test/vN/`. A version imports only from itself (relative
imports) and from the version-neutral `icoschema/_version.py`, so the next version starts as a copy, and an old
version is never touched by work on a new one. `icoschema/_schemas.py` is the one place that lists the versions and
points to the latest.

```
icoschema/
  __init__.py       the latest version's names (+ every version as `icoschema.vN`)
  _schemas.py       SCHEMA_MODULES, LATEST, which version a file is of
  _version.py       software id (version-neutral)
  v1/
    __init__.py     the public API of this version
    schema/dataset.yaml, schema/generated/dataset.py
    model/          Recording, Source, DatasetBundle, ...
    storage/        hdf5.py, tdms.py (the file format versions of this schema version)
test/
  test_schemas.py   what holds for every version, and the latest pointer
  v1/               tests of version 1, with its stored synthetic files in data/
```

## Steps

1. **Copy the newest version:** `uv run python scripts/new_schema_version.py`. It creates `icoschema/v2/` and `test/v2/`
   (renaming `v1` to `v2` in the copies) and registers `2: "icoschema.v2"` in `SCHEMA_MODULES`. From here on the tests
   in `test/test_schemas.py` run for `v2` too (self-contained imports, `icoschema.v2` importable).
2. **Change the schema** in `icoschema/v2/schema/dataset.yaml`, then regenerate the classes:
   `uv run gen-python icoschema/v2/schema/dataset.yaml > icoschema/v2/schema/generated/dataset.py`.
3. **Adapt the code of `v2` only:** the model classes in `v2/model/`, the readers/writers in `v2/storage/`. The file
   format versions of `v2` start at `2.0`: the part before the dot of `icoschema_format_version` *is* the schema
   version (that is how `_schemas.file_schema_version` picks the version a file is read with). Replace the registry
   in `v2/storage/hdf5.py` (`_FORMATS`) with the `2.x` layouts, and the `FormatVersion` literal with it; the same for
   TDMS if it changes.
4. **Adapt `test/v2/`:** regenerate the stored files (`cd test && uv run python -m v2.synthetic_files`) after
   changing the generator in `test/v2/synthetic_files.py`, and update the tests to the new schema.
5. **Migrations** between versions (a v1 file read as v2, a v2 bundle written as v1) belong to neither version:
   put them in `icoschema/migrate.py` (v1 -> v2 is there).
6. **Move the latest pointer** when `v2` is ready to be what `from icoschema import Recording` means (not before
   there is a way to read the files of the old version with it, as the top-level names then read only the new one):
   - `LATEST = 2` in `icoschema/_schemas.py`,
   - in `icoschema/__init__.py`: `from icoschema import v1, v2` and `from icoschema.v2 import (...)` instead of
     `v1`. (`test/test_schemas.py` fails until the two agree.)
7. Release a version that reads both before changing what is written by default.

`v1` is not touched by any of this.
