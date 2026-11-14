"""Write a bundle while it is recorded (`BundleWriter`), instead of from a `DatasetBundle` held in memory.

A `DatasetBundle` keeps every sample as a Python object, which for a long recording is far more memory than the
samples need. A `BundleWriter` takes the samples as they arrive and appends them to the file; the file it
produces is the one `DatasetBundle.to_hdf5` would write for the same data (format 2.0), so every reader reads it:

    from icoschema.v2 import BundleWriter, SourceSpec, ChannelMetadata, LinearConversion, Sensor

    spec = SourceSpec(
        name="sth1",
        channels=[ChannelMetadata(sensor=Sensor(sensor_id="acc100g", unit="g"), conversion=LinearConversion(gain=0.5, offset=-3.0))],
        start_time="2026-11-14T10:00:00.000000",
        stu_mac="08-6B-D7-0F-47-2C",
        sth_mac="14-2D-41-D7-77-7D",
        adc_prescaler=2, adc_acquisition_time=8, adc_oversample_rate=64,
    )
    with BundleWriter("measurement.hdf5", [spec]) as writer:
        source = writer["sth1"]
        source.append_row(timestamp=0, values=[1.0], counter=0)
        ...
        source.update(additional_data='{"dataloss": 0.0}')
        writer.add_file("report", pdf_bytes, mime="application/pdf")

Everything about a source that is known when the recording starts (its sensors and conversions, the ADC
settings, the start time, ...) is written when the file is opened, so a file that was not closed properly still
says what its data is; `update` changes the values that are only known later. A single source is stored at the
root of the file, several under `/sources/<name>/` (see `hdf5.py`).

Samples are collected in a buffer of `chunk_rows` rows and written to the file when it is full, on `flush()` and
on `close()`. The table is stored in chunks of `chunk_rows` rows, compressed. A writer is not thread-safe: use
one from a single thread (all sources of a bundle share one file).

This module is an internal implementation detail; use `icoschema.v2.BundleWriter`.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from dataclasses import dataclass
from types import TracebackType
from typing import Any, Self

import h5py
import numpy as np

from ..model.attachments import DEFAULT_MIME, EmbeddedFile
from ..schema.generated.dataset import ChannelMetadata, Provenance
from . import attachments
from .hdf5 import (
    _CHANNEL_SLOTS,
    _COMPRESSION,
    _SOURCE_NAME_ATTR,
    _SOURCES_GROUP,
    _create_dataset,
    _sensor_row,
    _write_primary_attrs,
    _write_provenance,
)

DEFAULT_CHUNK_ROWS = 8192
_FORMAT_VERSION = "2.0"


@dataclass
class SourceSpec:
    """What is known about a source before its first sample: everything of a `Source` except its data.

    `channels` has the metadata (sensor and conversion) of each channel column, in order: one to three.
    `has_counter` says whether samples come with a packet counter (as they do from the ICOtronic hardware).
    """

    name: str
    channels: Sequence[ChannelMetadata]
    start_time: str | None = None
    description: str | None = None
    stu_mac: str | None = None
    sth_mac: str | None = None
    adc_reference_voltage: float | str | None = None
    adc_prescaler: int | None = None
    adc_acquisition_time: int | None = None
    adc_oversample_rate: int | None = None
    sampling_frequency: float | None = None
    additional_data: str | None = None
    pre_metadata: str | None = None
    post_metadata: str | None = None
    has_counter: bool = True


_UPDATABLE = tuple(
    field.name
    for field in dataclasses.fields(SourceSpec)
    if field.name not in {"name", "channels", "has_counter"}
)


def _check_spec(spec: SourceSpec) -> None:
    name = str(spec.name)
    if not name or "/" in name or name.startswith("."):
        raise ValueError(f"source name {name!r} must be non-empty, contain no '/' and not start with '.'")
    if not 1 <= len(spec.channels) <= len(_CHANNEL_SLOTS):
        raise ValueError(f"source {name!r} needs one to three channels, got {len(spec.channels)}")


class SourceWriter:
    """Appends the samples of one source (see `BundleWriter`)."""

    def __init__(self, spec: SourceSpec, dataset: h5py.Dataset, dtype: np.dtype, chunk_rows: int) -> None:
        self.name = str(spec.name)
        self._dataset = dataset
        self._has_counter = spec.has_counter
        self._channels = len(spec.channels)
        self._buffer = np.zeros(chunk_rows, dtype=dtype)
        self._buffered = 0
        self._written = 0

    @property
    def rows(self) -> int:
        """The number of rows appended so far (written or still in the buffer)."""
        return self._written + self._buffered

    def append_row(self, timestamp: int, values: Sequence[float], counter: int | None = None) -> None:
        """Append one row: `timestamp` in integer microseconds since the source's start time, one value per
        channel, and the packet `counter` (0-255) if the source has one."""
        if len(values) != self._channels:
            raise ValueError(f"source {self.name!r} has {self._channels} channels, got {len(values)} values")
        row = self._buffer[self._buffered]
        if self._has_counter:
            if counter is None:
                raise ValueError(f"source {self.name!r} has a packet counter: pass `counter`")
            row["counter"] = counter
        row["timestamp"] = timestamp
        for slot, value in zip(_CHANNEL_SLOTS, values):
            row[slot] = value
        self._buffered += 1
        if self._buffered == len(self._buffer):
            self._write_buffer()

    def append(self, timestamp: Any, channels: Any, counter: Any = None) -> None:
        """Append many rows at once: `timestamp` (integer microseconds), `channels` (one array per channel, or
        an array of shape (rows, channels)) and `counter` if the source has one, all of the same length."""
        timestamps = np.asarray(timestamp)
        columns = np.asarray(channels, dtype=np.float64)
        if columns.ndim == 1 and self._channels == 1:
            columns = columns[:, None]
        elif columns.ndim == 2 and columns.shape[0] == self._channels and columns.shape[1] != self._channels:
            columns = columns.T  # one array per channel
        if columns.ndim != 2 or columns.shape[1] != self._channels or columns.shape[0] != len(timestamps):
            raise ValueError(
                f"source {self.name!r} has {self._channels} channels: expected {len(timestamps)} rows of "
                f"{self._channels} values, got shape {columns.shape}"
            )
        if self._has_counter:
            if counter is None:
                raise ValueError(f"source {self.name!r} has a packet counter: pass `counter`")
            counters = np.asarray(counter)
            if len(counters) != len(timestamps):
                raise ValueError("`counter` and `timestamp` must have the same length")
        self._write_buffer()
        rows = np.zeros(len(timestamps), dtype=self._buffer.dtype)
        if self._has_counter:
            rows["counter"] = counters
        rows["timestamp"] = timestamps
        for index, slot in enumerate(_CHANNEL_SLOTS[: self._channels]):
            rows[slot] = columns[:, index]
        self._write_rows(rows)

    def update(self, **values: Any) -> None:
        """Set attributes of the source that are only known later (or change): any of `start_time`,
        `description`, `stu_mac`, `sth_mac`, `adc_reference_voltage`, `adc_prescaler`, `adc_acquisition_time`,
        `adc_oversample_rate`, `sampling_frequency`, `additional_data`, `pre_metadata`, `post_metadata`."""
        unknown = sorted(set(values) - set(_UPDATABLE))
        if unknown:
            raise TypeError(f"cannot update {unknown}; updatable: {list(_UPDATABLE)}")
        _write_primary_attrs(self._dataset, **{name: value for name, value in values.items() if value is not None})

    def flush(self) -> None:
        """Write the buffered rows to the file."""
        self._write_buffer()

    def _write_buffer(self) -> None:
        if self._buffered:
            self._write_rows(self._buffer[: self._buffered])
            self._buffered = 0

    def _write_rows(self, rows: np.ndarray) -> None:
        if not len(rows):
            return
        self._dataset.resize((self._written + len(rows),))
        self._dataset[self._written : self._written + len(rows)] = rows
        self._written += len(rows)


class BundleWriter:
    """Writes a bundle with one or more sources to `path` while it is recorded (see the module docstring).

    Use it as a context manager, or call `close()`. The file is created (and replaced if it exists) when the
    writer is.
    """

    def __init__(
        self,
        path: str,
        sources: Sequence[SourceSpec],
        *,
        provenance: Provenance | None = None,
        table_name: str = "recording",
        chunk_rows: int = DEFAULT_CHUNK_ROWS,
    ) -> None:
        specs = list(sources)
        if not specs:
            raise ValueError("a bundle needs at least one source")
        names = [str(spec.name) for spec in specs]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate source names: {names}")
        for spec in specs:
            _check_spec(spec)
        if chunk_rows < 1:
            raise ValueError("chunk_rows must be positive")

        self.path = str(path)
        self._file: h5py.File | None = h5py.File(self.path, "w")
        self._sources: dict[str, SourceWriter] = {}
        try:
            f = self._file
            f.attrs["primary_table"] = table_name
            multiple = len(specs) > 1
            if multiple:
                f.attrs.create("sources", names, dtype=h5py.string_dtype())
                parent_group = f.create_group(_SOURCES_GROUP)
            for spec in specs:
                group = parent_group.create_group(str(spec.name)) if multiple else f
                self._sources[str(spec.name)] = self._create_source(group, spec, table_name, chunk_rows, multiple)
            _write_provenance(f, provenance)
            f.attrs[attachments.FORMAT_VERSION_ATTR] = _FORMAT_VERSION
            f.flush()
        except BaseException:
            self._file.close()
            self._file = None
            raise

    @staticmethod
    def _create_source(
        group: h5py.Group, spec: SourceSpec, table_name: str, chunk_rows: int, in_group: bool
    ) -> SourceWriter:
        slots = _CHANNEL_SLOTS[: len(spec.channels)]
        dtype = np.dtype(
            ([("counter", "u1")] if spec.has_counter else []) + [("timestamp", "<u8")] + [(s, "<f4") for s in slots]
        )
        dataset = group.create_dataset(
            table_name, shape=(0,), maxshape=(None,), dtype=dtype, chunks=(chunk_rows,), **_COMPRESSION
        )
        _write_primary_attrs(
            dataset,
            **{name: getattr(spec, name) for name in _UPDATABLE if getattr(spec, name) is not None},
        )
        # A single source's name is always stored; a source in a group has its name from the group.
        if not in_group:
            dataset.attrs[_SOURCE_NAME_ATTR] = str(spec.name)
        _create_dataset(group, "sensors", np.concatenate([_sensor_row(channel) for channel in spec.channels]))
        return SourceWriter(spec, dataset, dtype, chunk_rows)

    def __getitem__(self, name: str) -> SourceWriter:
        return self._sources[name]

    @property
    def sources(self) -> dict[str, SourceWriter]:
        return dict(self._sources)

    def _open(self) -> h5py.File:
        if self._file is None:
            raise ValueError("the writer is closed")
        return self._file

    def add_picture(self, name: str, images: list[str], *, overwrite: bool = False) -> None:
        """Add the picture set `name` (a list of base64 images); see `icoschema.v2.attachments`."""
        attachments.add_picture_to_open_file(self._open(), name, images, overwrite=overwrite)

    def add_file(
        self,
        name: str,
        content: bytes,
        *,
        mime: str | None = None,
        original_name: str | None = None,
        overwrite: bool = False,
    ) -> None:
        """Add an embedded file stored as `name`; see `icoschema.v2.attachments`."""
        attachments.add_file_to_open_file(
            self._open(),
            name,
            EmbeddedFile(bytes(content), mime or DEFAULT_MIME, original_name),
            overwrite=overwrite,
        )

    def flush(self) -> None:
        """Write the buffered rows of every source and flush the file to disk."""
        f = self._open()
        for source in self._sources.values():
            source.flush()
        f.flush()

    def close(self) -> None:
        """Write what is buffered and close the file. Closing twice is fine."""
        if self._file is None:
            return
        try:
            for source in self._sources.values():
                source.flush()
        finally:
            self._file.close()
            self._file = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
