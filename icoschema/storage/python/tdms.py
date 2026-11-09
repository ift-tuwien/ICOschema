"""Adapter that reads NI TDMS files (read-only) into the generated `dataset`
schema classes (see ICOschema/schema/generated/python/dataset.py).

Like the HDF5 adapter, read dispatches on a format version, here the root
property `icoschema_format_version` of the TDMS file:

- Absent: the "legacy" layout of the files written before TDMS files were
  versioned (below).
- Present: parsed by the version-specific parser registered in `_PARSERS`
  (none yet). Any other version is rejected, so an older reader never
  silently misreads a newer file.

**Legacy layout.** The deliberately simple mapping:

- The `rawdata` group's channels (1 to 3, file order) become `channel1..3`,
  values as nptdms returns them (scaled by the channel's NI scaling, if it
  has one, so they are already in `unit_string`; hence `NoConversion`; the
  original scaling stays in `additional_data`). Channels of one source must
  have the same length (an error otherwise: nothing is cut).
- Each channel's `Sensor` has `name` = the TDMS channel name and `unit` =
  its `unit_string`, nothing else.
- The sampling frequency is `1 / wf_increment` of those channels (they must
  agree); it is the source's `sampling_frequency`. A TDMS waveform has no
  packet counter and is gap-free, so the source has none, and `timestamp` is
  `round(i * 1e6 / fs)`.
- Packet loss comes from the `signalQuality` channels (100 = nothing lost),
  which become the source's `quality` (with its own `wf_increment` as
  sampling frequency): a `system` group's channel applies to the whole file,
  otherwise every other group holding a `signalQuality` channel is paired
  with a `rawdata` channel and the worst of them is kept. `Source` derives
  the loss as `100 - mean(quality)`. Without usable quality data the source
  has no `quality` and its loss is an assumed 0 (`signal_loss_measured` is
  `False`).
- `start_time` is the first channel's `wf_start_time` plus its
  `wf_start_offset`.
- **Several STUs**: when no `system` group holds a `signalQuality` channel,
  two or more other groups do, and every `rawdata` channel name starts with
  exactly one of those groups' names (the longest match, e.g. `STU1_Channel1`
  belongs to group `STU1`), each such group is its own `Source` named after
  the group, with `stu_id` set to it. The sources don't share anything: each
  has its own channels (file order, at most 3), rate, length, start time and
  quality. Any other file is one source (named `source1`).
- `additional_data` (JSON) of every source holds the properties nothing else
  keeps: `file` (root), `group` (the source's `system` or STU group),
  `channels` (by name) and `other_groups` (e.g. `info`).

TDMS is read-only: there is no writer. Needs `nptdms` (the `tdms` extra).

This module is an internal implementation detail. Don't import it directly
-- use ICOschema.model.python.recording.Recording.from_tdms() and
ICOschema.model.python.dataset_bundle.DatasetBundle.from_tdms() instead.
"""

from __future__ import annotations

import datetime
import json
import warnings
from collections.abc import Callable
from typing import Any

import numpy as np

from icoschema.schema.generated.python import dataset as generated

FORMAT_VERSION_PROPERTY = "icoschema_format_version"
LEGACY_VERSION = "legacy"

RAW_GROUP = "rawdata"
SYSTEM_GROUP = "system"
QUALITY_CHANNEL = "signalQuality"
MAX_CHANNELS = 3

_DEFAULT_SOURCE_NAME = "source1"


def _jsonable(value: Any) -> Any:
    """`value` as something `json.dumps` accepts (timestamps as ISO text)."""
    if isinstance(value, np.datetime64):
        return str(np.datetime_as_string(value, unit="us"))
    if isinstance(value, datetime.datetime | datetime.date):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple | np.ndarray):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _properties(obj: Any) -> dict[str, Any]:
    return {str(key): _jsonable(value) for key, value in obj.properties.items()}


def _quality(channel: Any) -> generated.QualityChannel | None:
    """The `signalQuality` channel as a `QualityChannel`, `None` if it holds
    no numeric data (e.g. the empty void-typed channel some files have)."""
    try:
        data = np.asarray(channel[:])
    except Exception:  # noqa: BLE001 -- unreadable -> unknown
        return None
    if data.size == 0 or not np.issubdtype(data.dtype, np.number) or not np.isfinite(data.astype(np.float64)).any():
        return None
    increment = channel.properties.get("wf_increment")
    rate = 1.0 / float(increment) if increment is not None and float(increment) > 0 else None
    return generated.QualityChannel(values=data.astype(np.float64).tolist(), sampling_frequency=rate)


def _mean_quality(quality: generated.QualityChannel) -> float:
    values = np.asarray(quality.values, dtype=np.float64)
    return float(values[np.isfinite(values)].mean())


def _worst(candidates: list[generated.QualityChannel | None]) -> generated.QualityChannel | None:
    usable = [quality for quality in candidates if quality is not None]
    return min(usable, key=_mean_quality) if usable else None


def _file_quality(tdms: Any, raw_count: int) -> tuple[generated.QualityChannel | None, Any | None]:
    """`(quality, group it came from)` of a single-source file: the `system`
    group's, else the worst of the other groups' (one per raw channel)."""
    groups = {group.name: group for group in tdms.groups()}
    system = groups.get(SYSTEM_GROUP)
    if system is not None and QUALITY_CHANNEL in system:
        return _quality(system[QUALITY_CHANNEL]), system
    holders = [g for g in groups.values() if g.name != RAW_GROUP and QUALITY_CHANNEL in g]
    if not holders:
        return None, None
    if len(holders) != raw_count:
        warnings.warn(
            f"{len(holders)} groups hold {QUALITY_CHANNEL} but {RAW_GROUP} has {raw_count} channel(s); "
            "signal loss is assumed 0",
            stacklevel=4,
        )
        return None, None
    return _worst([_quality(group[QUALITY_CHANNEL]) for group in holders]), None


def _split_by_stu(tdms: Any, channels: list[Any]) -> dict[str, list[Any]] | None:
    """`{group name: its rawdata channels}` (in file order) if the file holds
    several STUs (see the module docstring), else `None`."""
    groups = list(tdms.groups())
    system = next((g for g in groups if g.name == SYSTEM_GROUP), None)
    if system is not None and QUALITY_CHANNEL in system:
        return None
    holders = [g.name for g in groups if g.name != RAW_GROUP and QUALITY_CHANNEL in g]
    if len(holders) < 2:
        return None
    members: dict[str, list[Any]] = {name: [] for name in holders}
    for channel in channels:
        matches = [name for name in holders if channel.name.startswith(name)]
        if not matches:
            return None
        members[max(matches, key=len)].append(channel)
    if any(not channels_ for channels_ in members.values()):
        return None
    return members


class _Read:
    """What `_read_channels` found: the rate, the channel values, the number
    of rows and the first channel's start time."""

    def __init__(self, fs: float, columns: list[list[float]], rows: int, start_time: str | None) -> None:
        self.fs, self.columns, self.rows, self.start_time = fs, columns, rows, start_time


def _read_channels(path: str, where: str, channels: list[Any]) -> _Read:
    """Reads waveform `channels` (all of one STU) that must agree on
    `wf_increment` and length. `where` names them in error messages."""
    if len(channels) > MAX_CHANNELS:
        raise ValueError(f"{path}: {len(channels)} channels in {where!r}, at most {MAX_CHANNELS} are supported")
    increments = []
    for channel in channels:
        increment = channel.properties.get("wf_increment")
        if increment is None or not float(increment) > 0:
            raise ValueError(f"{path}: channel {channel.name!r} has no positive wf_increment")
        increments.append(float(increment))
    if not np.allclose(increments, increments[0], rtol=1e-9):
        raise ValueError(f"{path}: {where!r} channels have different wf_increment values {increments}")
    fs = 1.0 / increments[0]

    data = [np.asarray(channel[:]) for channel in channels]
    lengths = [len(values) for values in data]
    if len(set(lengths)) != 1:
        raise ValueError(f"{path}: {where!r} channels have different lengths {lengths}")
    rows = lengths[0]
    if rows == 0:
        raise ValueError(f"{path}: the {where!r} channels hold no data")
    columns = [values.astype(np.float64).tolist() for values in data]

    start = channels[0].properties.get("wf_start_time")
    start_time = None
    if start is not None:
        begin = np.datetime64(start, "us")
        offset = channels[0].properties.get("wf_start_offset")
        if offset is not None and float(offset) != 0.0:
            begin = begin + np.timedelta64(round(float(offset) * 1e6), "us")
        start_time = str(np.datetime_as_string(begin, unit="us"))
    return _Read(fs, columns, rows, start_time)


def _source(
    name: str,
    stu_id: str | None,
    read: _Read,
    channels: list[Any],
    quality: generated.QualityChannel | None,
    additional_data: dict[str, Any],
) -> generated.Source:
    def metadata(channel: Any) -> generated.ChannelMetadata:
        unit = channel.properties.get("unit_string") or None
        return generated.ChannelMetadata(
            sensor=generated.Sensor(name=channel.name, unit=str(unit) if unit is not None else None),
            compensations=[generated.NoConversion(order=0)],
        )

    return generated.Source(
        name=name,
        stu_id=stu_id,
        sampling_frequency=read.fs,
        quality=quality,
        additional_data=json.dumps(additional_data),
        hardware_metadata=generated.HardwareMetadata(
            **{f"channel{i + 1}_metadata": metadata(channel) for i, channel in enumerate(channels)}
        ),
        recording_metadata=generated.RecordingMetadata(start_time=read.start_time),
        recording_data=generated.RecordingData(
            timestamp=np.rint(np.arange(read.rows) * 1e6 / read.fs).astype(np.int64).tolist(),
            **{f"channel{i + 1}": column for i, column in enumerate(read.columns)},
        ),
    )


def _source_name(group: str, taken: set[str]) -> str:
    """A TDMS group name as a `Source` name: one HDF5 path segment, unique."""
    name = group.replace("/", "_").lstrip(".") or "stu"
    unique, n = name, 1
    while unique in taken:
        n += 1
        unique = f"{name}_{n}"
    taken.add(unique)
    return unique


def _additional_data(tdms: Any, own_group: Any | None, channels: list[Any], data_groups: set[str]) -> dict[str, Any]:
    """The properties of the file, the source's group, its channels and the
    groups that hold no data (e.g. `info`), as `Source.additional_data`."""
    return {
        "file": _properties(tdms),
        "group": _properties(own_group) if own_group is not None else None,
        "channels": {channel.name: _properties(channel) for channel in channels},
        "other_groups": {g.name: _properties(g) for g in tdms.groups() if g.name not in data_groups},
    }


def _load_stus(path: str, tdms: Any, members: dict[str, list[Any]]) -> generated.Recording:
    """One `Source` per STU group (see the module docstring)."""
    groups = {g.name: g for g in tdms.groups()}
    data_groups = {RAW_GROUP, *members}
    sources = []
    taken: set[str] = set()
    for group, channels in members.items():
        read = _read_channels(path, f"{RAW_GROUP} ({group})", channels)
        quality = _quality(groups[group][QUALITY_CHANNEL])
        sources.append(
            _source(
                _source_name(group, taken),
                group,
                read,
                channels,
                quality,
                _additional_data(tdms, groups[group], channels, data_groups),
            )
        )
    return generated.Recording(sources=sources)


def _load_recording_legacy(path: str, tdms: Any) -> generated.Recording:
    if RAW_GROUP not in [g.name for g in tdms.groups()]:
        raise ValueError(f"{path}: no {RAW_GROUP!r} group (found {[g.name for g in tdms.groups()]})")
    channels = list(tdms[RAW_GROUP].channels())
    if not channels:
        raise ValueError(f"{path}: group {RAW_GROUP!r} has no channels")

    members = _split_by_stu(tdms, channels)
    if members is not None:
        return _load_stus(path, tdms, members)

    read = _read_channels(path, RAW_GROUP, channels)
    quality, own_group = _file_quality(tdms, len(channels))
    data_groups = {RAW_GROUP} | ({own_group.name} if own_group is not None else set())
    return generated.Recording(
        sources=[
            _source(
                _DEFAULT_SOURCE_NAME,
                None,
                read,
                channels,
                quality,
                _additional_data(tdms, own_group, channels, data_groups),
            )
        ]
    )


_PARSERS: dict[str, Callable[[str, Any], generated.Recording]] = {}


def _format_version(tdms: Any, path: str) -> str | None:
    """The file's format version (`None` for legacy files); raises
    `ValueError` for a version this reader doesn't know."""
    version = tdms.properties.get(FORMAT_VERSION_PROPERTY)
    if version is None:
        return None
    version = str(version)
    if version not in _PARSERS:
        raise ValueError(
            f"Unsupported {FORMAT_VERSION_PROPERTY} {version!r} in {path!r}; supported versions: {sorted(_PARSERS)}"
        )
    return version


def load(path: str) -> tuple[generated.Recording, str]:
    """The recording in the TDMS file at `path` and the format version it was
    read as (`LEGACY_VERSION` for a file without one). Raises `ValueError` for
    a file without a usable `rawdata` group or with an unknown format
    version, and `ImportError` if `nptdms` isn't installed."""
    try:
        from nptdms import TdmsFile  # type: ignore[import-untyped]
    except ImportError as error:
        raise ImportError("reading TDMS files needs nptdms: pip install icoschema[tdms]") from error

    tdms = TdmsFile.read(path)
    version = _format_version(tdms, path)
    if version is None:
        return _load_recording_legacy(path, tdms), LEGACY_VERSION
    return _PARSERS[version](path, tdms), version


def load_recording(path: str) -> generated.Recording:
    """`load(path)` without the version."""
    return load(path)[0]
