"""Start the next schema version as a copy of an existing one.

    uv run python scripts/new_schema_version.py            # copies the newest version to the next number
    uv run python scripts/new_schema_version.py --from 1

Copies `icoschema/vN/` and `test/vN/` to `vM` (M = N + 1 by default), rewriting `vN` to `vM` in the copied text
files, and registers the new package in `icoschema/_schemas.py`. It does not move the pointer to the latest
version: that is a step of its own (see doc/adding-a-schema-version.md), taken when the new version is ready.
"""

import argparse
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {".py", ".yaml", ".md"}


def versions(root: Path) -> list[int]:
    package = root / "icoschema"
    return sorted(
        int(p.name[1:])
        for p in package.iterdir()
        if p.is_dir() and re.fullmatch(r"v\d+", p.name)
    )


def copy_version(source: Path, target: Path, old: int, new: int) -> None:
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__"))
    for path in target.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            path.write_text(re.sub(rf"\bv{old}\b", f"v{new}", text), encoding="utf-8")


def register(schemas: Path, old: int, new: int) -> None:
    text = schemas.read_text(encoding="utf-8")
    entry = f'    {old}: "icoschema.v{old}",\n'
    if entry not in text:
        raise SystemExit(
            f"{schemas}: did not find the entry {entry.strip()!r} to add the new version after"
        )
    schemas.write_text(
        text.replace(entry, entry + f'    {new}: "icoschema.v{new}",\n'),
        encoding="utf-8",
    )


def scaffold(
    root: Path, old: int | None = None, new: int | None = None
) -> tuple[int, int]:
    existing = versions(root)
    old = old if old is not None else existing[-1]
    new = new if new is not None else max(existing) + 1
    for what in (root / "icoschema" / f"v{new}", root / "test" / f"v{new}"):
        if what.exists():
            raise SystemExit(f"{what} already exists")
    copy_version(
        root / "icoschema" / f"v{old}", root / "icoschema" / f"v{new}", old, new
    )
    if (root / "test" / f"v{old}").exists():
        copy_version(root / "test" / f"v{old}", root / "test" / f"v{new}", old, new)
    register(root / "icoschema" / "_schemas.py", old, new)
    return old, new


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--from", dest="old", type=int, help="the version to copy (default: the newest)"
    )
    parser.add_argument(
        "--to",
        dest="new",
        type=int,
        help="the new version number (default: the newest + 1)",
    )
    arguments = parser.parse_args()
    old, new = scaffold(ROOT, arguments.old, arguments.new)
    print(
        f"Copied v{old} to v{new} (package and tests) and registered it in icoschema/_schemas.py."
    )
    print(
        f"Next: edit icoschema/v{new}/schema/dataset.yaml and regenerate, see doc/adding-a-schema-version.md."
    )
