"""Everything a file has that this package has no model for, kept so that saving it again drops nothing.

A `DatasetBundle` read from HDF5 carries a `Preserved`: the attributes and nodes (groups, datasets, links) of
the file that are not part of the layout described in `hdf5.py`, by their path in the file. Saving the bundle
writes them back where they were. They are opaque: nothing here interprets them.

Two things are deliberately not preserved: PyTables bookkeeping attributes (`CLASS`, `TITLE`, `VERSION`,
`FLAVOR`, `NROWS`, `PYTABLES_FORMAT_VERSION`, `FIELD_n_NAME`, `FIELD_n_FILL`) of nodes this package models, since they describe the
PyTables container of a table and not its content, and attributes a migration consumed (see `icoschema.migrate`).
Nodes that are preserved keep all of their attributes as they are.

Limitations: a preserved dataset is held in memory while the bundle lives, HDF5 references and committed
datatypes can not be copied between files (they are logged, not silently skipped), and a dataset is written back
compressed with the package's usual settings, not with the chunking it had.

This module is an internal implementation detail.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

import h5py
import numpy as np

logger = logging.getLogger(__name__)

PYTABLES_ATTR = re.compile(r"^(CLASS|TITLE|VERSION|FLAVOR|NROWS|PYTABLES_FORMAT_VERSION|FIELD_\d+_(NAME|FILL))$")
"""Attributes PyTables writes on every node it creates."""

COMPRESSION = {"compression": "gzip", "compression_opts": 4, "shuffle": True}
"""Applied to every dataset with more than one element."""


@dataclass(frozen=True)
class RawAttr:
    """An attribute as stored: its value and its HDF5 datatype."""

    value: Any
    dtype: np.dtype | None


@dataclass
class RawNode:
    """A node of a file, copied as it is: a group (with its children), a dataset, or a link."""

    kind: Literal["group", "dataset", "soft_link", "external_link"]
    attrs: dict[str, RawAttr] = field(default_factory=dict)
    children: dict[str, RawNode] = field(default_factory=dict)
    data: Any = None
    dtype: np.dtype | None = None
    target: str | None = None  # the path of a soft link, or the path in the file of an external link
    filename: str | None = None  # the file of an external link


@dataclass
class Preserved:
    """What a bundle keeps from its file without understanding it, by path in the file ("" is the root).

    `attrs` are attributes of nodes this package models (the root, a primary table, ...). `nodes` are whole
    nodes it doesn't."""

    attrs: dict[str, dict[str, RawAttr]] = field(default_factory=dict)
    nodes: dict[str, RawNode] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.attrs or self.nodes)

    def merged(self, other: Preserved) -> Preserved:
        """A new `Preserved` with what `other` has added to this one (`other` wins for the same path)."""
        attrs = {path: dict(values) for path, values in self.attrs.items()}
        for path, values in other.attrs.items():
            attrs.setdefault(path, {}).update(values)
        return Preserved(attrs=attrs, nodes={**self.nodes, **other.nodes})


# ── read ─────────────────────────────────────────────────────────────────────


def capture_attrs(
    obj: h5py.HLObject, *, known: Iterable[str] = (), bookkeeping: bool = False
) -> dict[str, RawAttr]:
    """The attributes of `obj` that are not in `known`. PyTables bookkeeping is left out when `bookkeeping`
    says the node is one this package models."""
    known = set(known)
    captured: dict[str, RawAttr] = {}
    for name in obj.attrs:
        if name in known or (bookkeeping and PYTABLES_ATTR.match(name)):
            continue
        try:
            captured[name] = RawAttr(obj.attrs[name], obj.attrs.get_id(name).dtype)
        except Exception:
            logger.warning("Cannot keep attribute %r of %r (unsupported HDF5 type)", name, obj.name, exc_info=True)
    return captured


def capture_node(parent: h5py.Group, name: str) -> RawNode | None:
    """A copy of the child `name` of `parent`, with everything below it. `None` if it can't be copied
    (logged)."""
    link = parent.get(name, getlink=True)
    if isinstance(link, h5py.SoftLink):
        return RawNode("soft_link", target=link.path)
    if isinstance(link, h5py.ExternalLink):
        return RawNode("external_link", target=link.path, filename=link.filename)
    obj = parent[name]
    try:
        attrs = capture_attrs(obj)
        if isinstance(obj, h5py.Group):
            node = RawNode("group", attrs=attrs)
            for child in obj:
                captured = capture_node(obj, child)
                if captured is not None:
                    node.children[child] = captured
            return node
        if isinstance(obj, h5py.Dataset):
            return RawNode("dataset", attrs=attrs, data=obj[()], dtype=obj.dtype)
    except Exception:
        logger.warning("Cannot keep %r (unsupported HDF5 type)", obj.name, exc_info=True)
        return None
    logger.warning("Cannot keep %r (a datatype or unknown object)", obj.name)
    return None


def capture_children(
    group: h5py.Group, path: str, known: Callable[[str], bool], preserved: Preserved
) -> None:
    """Preserve every child of `group` (at `path` in the file) that `known` doesn't claim."""
    for name in group:
        if known(name):
            continue
        node = capture_node(group, name)
        if node is not None:
            preserved.nodes[f"{path}/{name}" if path else name] = node


def capture_group_attrs(
    obj: h5py.HLObject, path: str, known: Iterable[str], preserved: Preserved
) -> None:
    """Preserve the attributes of a modelled node `obj` (at `path`) that are not in `known`."""
    attrs = capture_attrs(obj, known=known, bookkeeping=True)
    if attrs:
        preserved.attrs.setdefault(path, {}).update(attrs)


# ── write ────────────────────────────────────────────────────────────────────


def write_attrs(obj: h5py.HLObject, attrs: dict[str, RawAttr], *, overwrite: bool = True) -> None:
    for name, attr in attrs.items():
        if not overwrite and name in obj.attrs:
            continue
        if isinstance(attr.value, h5py.Empty):
            obj.attrs.create(name, data=attr.value)
        else:
            obj.attrs.create(name, data=attr.value, dtype=attr.dtype)


def write_node(parent: h5py.Group, name: str, node: RawNode) -> None:
    if node.kind == "soft_link":
        parent[name] = h5py.SoftLink(node.target)
        return
    if node.kind == "external_link":
        parent[name] = h5py.ExternalLink(node.filename, node.target)
        return
    if node.kind == "group":
        group = parent.create_group(name)
        write_attrs(group, node.attrs)
        for child, raw in node.children.items():
            write_node(group, child, raw)
        return
    data = node.data
    size = int(np.prod(np.shape(data))) if np.shape(data) else 1
    dataset = parent.create_dataset(name, data=data, dtype=node.dtype, **(COMPRESSION if size > 1 else {}))
    write_attrs(dataset, node.attrs)


def _free_name(parent: h5py.Group, name: str) -> str:
    candidate, number = f"{name}__preserved", 1
    while candidate in parent:
        number += 1
        candidate = f"{name}__preserved{number}"
    return candidate


def _resolve(path: str, names: dict[str, str]) -> str:
    return "/".join(names.get(part, part) for part in path.split("/")) if path else path


def write_preserved(f: h5py.File, preserved: Preserved, names: dict[str, str] | None = None) -> None:
    """Write what `preserved` holds back into `f`, after the rest of the file is written.

    `names` replaces path segments that stand for a name the writer chooses (the primary table is saved as
    `recording`, whatever it was called in the file it was read from).

    Attributes never replace one the writer set. A node whose path is already taken (e.g. the file now
    models something under that name) is written next to it as `<name>__preserved`, so nothing is lost."""
    names = names or {}
    for path, attrs in preserved.attrs.items():
        path = _resolve(path, names)
        node = f if path == "" else f.get(path)
        if node is None:
            logger.warning("Cannot restore attributes %s: %r is not in the file", sorted(attrs), path)
            continue
        write_attrs(node, attrs, overwrite=False)
    for path, node in preserved.nodes.items():
        path = _resolve(path, names)
        parent_path, _, name = path.rpartition("/")
        parent = f.require_group(parent_path) if parent_path else f
        if name in parent:
            free = _free_name(parent, name)
            logger.warning("%r is taken in the file: keeping the preserved node as %r", path, free)
            name = free
        write_node(parent, name, node)
