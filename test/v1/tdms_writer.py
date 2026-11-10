"""A minimal TDMS writer for the tests (the package only reads TDMS files).

It writes what the tests need and nothing more: a root object, groups and channels with properties, and
contiguous little-endian data, as one segment per `write_segment`. Where a test used another library's
writer, the names are the same (`RootObject`, `GroupObject`, `ChannelObject`, `TdmsWriter`).
"""

from __future__ import annotations

import datetime
import struct
from typing import Any, Self

import numpy as np

_DATA_TYPES = {"i1": 1, "i2": 2, "i4": 3, "i8": 4, "u1": 5, "u2": 6, "u4": 7, "u8": 8, "f4": 9, "f8": 10}
_STRUCT = {1: "b", 2: "h", 3: "i", 4: "q", 5: "B", 6: "H", 7: "I", 8: "Q", 9: "f", 10: "d"}
_EPOCH = datetime.datetime(1904, 1, 1)


def _string(text: str) -> bytes:
    raw = text.encode("utf-8")
    return struct.pack("<I", len(raw)) + raw


def _escape(name: str) -> str:
    return name.replace("'", "''")


def _property(name: str, value: Any) -> bytes:
    if isinstance(value, bool | np.bool_):
        return _string(name) + struct.pack("<IB", 0x21, int(value))
    if isinstance(value, np.generic) and value.dtype.kind in "iuf":
        code = _DATA_TYPES[value.dtype.str[1:]]
        return _string(name) + struct.pack("<I" + _STRUCT[code], code, value.item())
    if isinstance(value, int):
        return _string(name) + struct.pack("<Ii", 3, value)
    if isinstance(value, float):
        return _string(name) + struct.pack("<Id", 10, value)
    if isinstance(value, str):
        return _string(name) + struct.pack("<I", 0x20) + _string(value)
    if isinstance(value, datetime.datetime):
        delta = value - _EPOCH
        seconds, microseconds = delta.days * 86_400 + delta.seconds, delta.microseconds
        fraction = ((microseconds << 64) + 999_999) // 1_000_000  # rounded up so that microseconds read back exactly
        return _string(name) + struct.pack("<IQq", 0x44, fraction, seconds)
    raise TypeError(f"cannot write a property of type {type(value).__name__}")


class _Object:
    def __init__(self, path: str, properties: dict[str, Any] | None) -> None:
        self.path = path
        self.properties = dict(properties or {})


class RootObject(_Object):
    def __init__(self, properties: dict[str, Any] | None = None) -> None:
        super().__init__("/", properties)


class GroupObject(_Object):
    def __init__(self, group: str, properties: dict[str, Any] | None = None) -> None:
        super().__init__(f"/'{_escape(group)}'", properties)


class ChannelObject(_Object):
    def __init__(self, group: str, channel: str, data: Any, properties: dict[str, Any] | None = None) -> None:
        super().__init__(f"/'{_escape(group)}'/'{_escape(channel)}'", properties)
        self.data = np.asarray(data)


class TdmsWriter:
    def __init__(self, path: str) -> None:
        self._file = open(path, "wb")  # noqa: SIM115 -- closed by __exit__

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self._file.close()

    def write_segment(self, objects: list[_Object]) -> None:
        metadata = bytearray(struct.pack("<I", len(objects)))
        raw = bytearray()
        for obj in objects:
            metadata += _string(obj.path)
            data = getattr(obj, "data", None)
            if data is None:
                metadata += struct.pack("<I", 0xFFFF_FFFF)
            else:
                code = _DATA_TYPES[data.dtype.newbyteorder("<").str[1:]]
                metadata += struct.pack("<IIIQ", 20, code, 1, len(data))
                raw += data.astype(data.dtype.newbyteorder("<")).tobytes()
            metadata += struct.pack("<I", len(obj.properties))
            for name, value in obj.properties.items():
                metadata += _property(name, value)
        toc = 2 | 4 | (8 if raw else 0)
        lead_in = b"TDSm" + struct.pack("<IIQQ", toc, 4713, len(metadata) + len(raw), len(metadata))
        self._file.write(lead_in + metadata + raw)
