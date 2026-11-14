"""The pictures and embedded files of an HDF5 file .

Layout: `/pictures/<name>` is a one-dimensional array of byte strings (one image each, base64 text) and
`/files/<name>` a one-dimensional `uint8` array with the content of a file, and the attributes `size` (bytes),
`mime` and `original_name`.

Files of format 2.0 and files of schema version 1 from the data acquisition have them elsewhere: picture sets as
arrays at the root with "picture" in their name, embedded files under `/embedded_files/` (same layout as
`/files/`). `load_attachments` finds them there too. Anything in these places that doesn't have the layout is
preserved as it is (see `preserved.py`), never dropped.

The functions that take a `path` change a file in place without loading the rest of it (a measurement can be
large) and need a file of schema version 2. They only look at `/pictures/` and `/files/`.

This module is an internal implementation detail; use `DatasetBundle.with_picture`/`with_file`, or the
functions below, via `icoschema.v2.attachments`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import h5py
import numpy as np

from ..model.attachments import (
    DEFAULT_MIME,
    EmbeddedFile,
    EmbeddedFileInfo,
    check_attachment_name,
)
from .preserved import (
    COMPRESSION,
    Preserved,
    RawNode,
    capture_attrs,
    capture_group_attrs,
    capture_node,
)

logger = logging.getLogger(__name__)

PICTURES_GROUP = "pictures"
FILES_GROUP = "files"
LEGACY_FILES_GROUP = "embedded_files"
FORMAT_VERSION_ATTR = "icoschema_format_version"

_FILE_ATTRS = ("size", "mime", "original_name")


def _text(attrs: h5py.AttributeManager, name: str) -> str | None:
    if name not in attrs:
        return None
    value = attrs[name]
    return value.decode() if isinstance(value, bytes) else str(value)


# ── pictures and files <-> datasets ──────────────────────────────────────────


def picture_images(obj: object) -> list[str] | None:
    """The images of `obj` if it is a picture set (a one-dimensional array of byte strings), else `None`."""
    if not isinstance(obj, h5py.Dataset) or obj.ndim != 1:
        return None
    if obj.dtype.kind == "S":
        values = obj[()]
    elif h5py.check_string_dtype(obj.dtype) is not None:
        values = [v if isinstance(v, bytes) else str(v).encode() for v in obj[()]]
    else:
        return None
    try:
        return [bytes(value).decode("utf-8") for value in values]
    except UnicodeDecodeError:
        return None


def picture_array(images: list[str]) -> np.ndarray:
    encoded = [image.encode("utf-8") for image in images]
    width = max((len(value) for value in encoded), default=1) or 1
    return np.array(encoded, dtype=f"S{width}")


def embedded_file(obj: object) -> EmbeddedFile | None:
    """The file `obj` holds if it is an embedded file (a one-dimensional `uint8` array), else `None`."""
    if not isinstance(obj, h5py.Dataset) or obj.ndim != 1 or obj.dtype != np.uint8:
        return None
    return EmbeddedFile(
        content=obj[()].tobytes(),
        mime=_text(obj.attrs, "mime") or DEFAULT_MIME,
        original_name=_text(obj.attrs, "original_name"),
    )


def _create(parent: h5py.Group, name: str, data: np.ndarray) -> h5py.Dataset:
    return parent.create_dataset(name, data=data, **(COMPRESSION if data.size > 1 else {}))


def _store_picture(group: h5py.Group, name: str, images: list[str]) -> None:
    _create(group, name, picture_array(images))


def _store_file(group: h5py.Group, name: str, file: EmbeddedFile) -> None:
    dataset = _create(group, name, np.frombuffer(file.content, dtype=np.uint8))
    dataset.attrs["size"] = len(file.content)
    dataset.attrs["mime"] = file.mime
    dataset.attrs["original_name"] = file.original_name if file.original_name is not None else name


def write_attachments(
    f: h5py.File, pictures: dict[str, list[str]], files: dict[str, EmbeddedFile]
) -> None:
    """Write the `/pictures/` and `/files/` groups of a bundle (a group only if there is something in it)."""
    if pictures:
        group = f.create_group(PICTURES_GROUP)
        for name, images in pictures.items():
            _store_picture(group, check_attachment_name(name, "picture"), list(images))
    if files:
        group = f.create_group(FILES_GROUP)
        for name, file in files.items():
            _store_file(group, check_attachment_name(name, "file"), file)


# ── read: bundle ─────────────────────────────────────────────────────────────


@dataclass
class Attachments:
    pictures: dict[str, list[str]] = field(default_factory=dict)
    files: dict[str, EmbeddedFile] = field(default_factory=dict)
    claimed: set[str] = field(default_factory=set)
    """The names at the root of the file that hold attachments (so they are not also preserved as unknown)."""
    preserved: Preserved = field(default_factory=Preserved)


def _load_group(f: h5py.File, group_name: str, result: Attachments, *, legacy: bool, take: str) -> None:
    group = f.get(group_name)
    if not isinstance(group, h5py.Group):
        return
    result.claimed.add(group_name)
    target = result.pictures if take == "pictures" else result.files
    new_group = PICTURES_GROUP if take == "pictures" else FILES_GROUP
    known_attrs = _FILE_ATTRS if take == "files" else ()
    leftovers: dict[str, RawNode] = {}
    for name in group:
        obj = group[name]
        value = picture_images(obj) if take == "pictures" else embedded_file(obj)
        if value is None or name in target:
            node = capture_node(group, name)
            if node is not None:
                leftovers[name] = node
            continue
        target[name] = value  # type: ignore[assignment]
        # attributes the layout doesn't know stay with the dataset, in its place in the new layout
        capture_group_attrs(obj, f"{new_group}/{name}", known_attrs, result.preserved)
    own = capture_attrs(group, bookkeeping=True)
    if legacy:
        # what is left of the old group (it may be nothing, then it is not written again)
        if own or leftovers:
            result.preserved.nodes[group_name] = RawNode("group", attrs=own, children=leftovers)
    else:
        for name, node in leftovers.items():
            result.preserved.nodes[f"{group_name}/{name}"] = node
        if own:
            result.preserved.attrs.setdefault(group_name, {}).update(own)


def load_attachments(f: h5py.File, known_root: set[str]) -> Attachments:
    """The pictures and embedded files of `f`, wherever they are stored, and what was found with them that
    isn't one (preserved). `known_root` are the root names that belong to something else."""
    result = Attachments()
    _load_group(f, PICTURES_GROUP, result, legacy=False, take="pictures")
    _load_group(f, FILES_GROUP, result, legacy=False, take="files")
    _load_group(f, LEGACY_FILES_GROUP, result, legacy=True, take="files")
    for name in list(f):
        if name in known_root or name in result.claimed or "picture" not in name.lower():
            continue
        images = picture_images(f[name])
        if images is None or name in result.pictures:
            continue
        result.pictures[name] = images
        result.claimed.add(name)
        capture_group_attrs(f[name], f"{PICTURES_GROUP}/{name}", (), result.preserved)
    return result


# ── in place ─────────────────────────────────────────────────────────────────


def _open(path: str, mode: str) -> h5py.File:
    f = h5py.File(path, mode)
    version = f.attrs.get(FORMAT_VERSION_ATTR)
    text = version.decode() if isinstance(version, bytes) else version
    if text is None or not str(text).startswith("2."):
        f.close()
        raise ValueError(
            f"{path!r} is not a file of schema version 2 (format version {text!r}); "
            "migrate it first (icoschema.migrate.convert_file)"
        )
    return f


def _group_for_write(f: h5py.File, group_name: str, name: str, kind: str, overwrite: bool) -> h5py.Group:
    check_attachment_name(name, kind)
    group = f.require_group(group_name)
    if name in group:
        if not overwrite:
            raise ValueError(f"{kind} {name!r} already exists (pass overwrite=True to replace it)")
        del group[name]
    return group


def add_picture_to_open_file(f: h5py.File, name: str, images: list[str], *, overwrite: bool = False) -> None:
    group = _group_for_write(f, PICTURES_GROUP, name, "picture", overwrite)
    _store_picture(group, name, list(images))


def add_file_to_open_file(f: h5py.File, name: str, file: EmbeddedFile, *, overwrite: bool = False) -> None:
    group = _group_for_write(f, FILES_GROUP, name, "file", overwrite)
    _store_file(group, name, file)


def add_picture(path: str, name: str, images: list[str], *, overwrite: bool = False) -> None:
    """Add the picture set `name` (a list of base64 images) to the file `path`, in place. Raises `ValueError`
    if there is one with that name already, unless `overwrite`."""
    with _open(path, "a") as f:
        add_picture_to_open_file(f, name, images, overwrite=overwrite)


def add_file(
    path: str,
    name: str,
    content: bytes,
    *,
    mime: str | None = None,
    original_name: str | None = None,
    overwrite: bool = False,
) -> None:
    """Add an embedded file stored as `name` to the file `path`, in place. `name` has to be a single HDF5 path
    segment; `original_name` (default `name`) is what the file was called. Raises `ValueError` if there is
    one with that name already, unless `overwrite`."""
    with _open(path, "a") as f:
        add_file_to_open_file(
            f, name, EmbeddedFile(bytes(content), mime or DEFAULT_MIME, original_name), overwrite=overwrite
        )


def read_pictures(path: str) -> dict[str, list[str]]:
    """The picture sets in `/pictures/` of the file `path`, by name."""
    with _open(path, "r") as f:
        group = f.get(PICTURES_GROUP)
        if not isinstance(group, h5py.Group):
            return {}
        return {name: images for name in group if (images := picture_images(group[name])) is not None}


def list_files(path: str) -> list[EmbeddedFileInfo]:
    """The embedded files in `/files/` of the file `path`, without their content."""
    with _open(path, "r") as f:
        group = f.get(FILES_GROUP)
        if not isinstance(group, h5py.Group):
            return []
        infos = []
        for name in group:
            dataset = group[name]
            if not isinstance(dataset, h5py.Dataset) or dataset.ndim != 1 or dataset.dtype != np.uint8:
                continue
            size = dataset.attrs.get("size")
            infos.append(
                EmbeddedFileInfo(
                    name=name,
                    size=int(size) if size is not None else int(dataset.shape[0]),
                    mime=_text(dataset.attrs, "mime") or DEFAULT_MIME,
                    original_name=_text(dataset.attrs, "original_name") or name,
                )
            )
        return infos


def read_file(path: str, name: str) -> EmbeddedFile:
    """The embedded file `name` of the file `path`. Raises `KeyError` if there is none."""
    with _open(path, "r") as f:
        group = f.get(FILES_GROUP)
        found = embedded_file(group[name]) if isinstance(group, h5py.Group) and name in group else None
        if found is None:
            raise KeyError(name)
        return found


def remove_file(path: str, name: str) -> None:
    """Remove the embedded file `name` from the file `path`. Raises `KeyError` if there is none."""
    with _open(path, "a") as f:
        group = f.get(FILES_GROUP)
        if not isinstance(group, h5py.Group) or name not in group:
            raise KeyError(name)
        del group[name]
