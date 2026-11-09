"""The software identity written into a file's provenance."""

from importlib.metadata import PackageNotFoundError, version


def software_id() -> str:
    """`"icoschema <version>"` (just the name when not installed as a package)."""
    try:
        return f"icoschema {version('icoschema')}"
    except PackageNotFoundError:
        return "icoschema"
