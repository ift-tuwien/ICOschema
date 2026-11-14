"""Pictures and embedded files of a `DatasetBundle`.

Both belong to the bundle as a whole (not to one source), and both are stored in a group of their own: the pictures under `/pictures/`, the embedded files under `/files/`.

    from icoschema import DatasetBundle

    bundle = bundle.with_picture("post__pictures", ["<base64 image>", ...])
    bundle = bundle.with_file("report", pdf_bytes, mime="application/pdf", original_name="Report 1.pdf")
    bundle.to_hdf5("some_file.hdf5")

A picture set is a list of images, each one a string (the base64 text of the image, as the API stores them). An
embedded file is `EmbeddedFile`: its bytes, its media type and the name it had when it was added.

Files written by the data acquisition before the groups existed have the picture sets as arrays at the root of
the file (a name with "picture" in it) and the embedded files under `/embedded_files/`. Reading finds them
there and the bundle has them as above, so saving moves them into the groups; whatever isn't one of these
stays where it was (see `icoschema.v2.storage.preserved`).

This file should never be imported directly, but rather only via a `DatasetBundle`.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MIME = "application/octet-stream"


def check_attachment_name(name: str, kind: str) -> str:
    """`name` if it can be the name of a picture set or an embedded file: a single HDF5 path segment
    (non-empty, no "/", not starting with ".")."""
    if not isinstance(name, str) or not name or "/" in name or name.startswith("."):
        raise ValueError(f"{kind} name {name!r} must be non-empty, contain no '/' and not start with '.'")
    return name


@dataclass(frozen=True)
class EmbeddedFile:
    """A file stored in a bundle."""

    content: bytes
    mime: str = DEFAULT_MIME
    original_name: str | None = None
    """The name the file had when it was added (the key it is stored under is made to fit HDF5)."""

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(frozen=True)
class EmbeddedFileInfo:
    """What a file says about an embedded file without its content (`icoschema.v2.storage.attachments`)."""

    name: str
    size: int
    mime: str
    original_name: str
