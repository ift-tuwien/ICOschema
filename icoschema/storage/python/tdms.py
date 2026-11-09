"""Adapter that reads NI TDMS files (read-only) into the generated `dataset`
schema classes (see ICOschema/schema/generated/python/dataset.py).

Like the HDF5 adapter, read dispatches on a format version, here the root
property `icoschema_format_version` of the TDMS file:

- Absent: the "legacy" layout of the files written before TDMS files were
  versioned. This is the reader that used to live in `icocompute.tdms`,
  moved here unchanged (see below).
- Present: parsed by the version-specific parser registered in `_PARSERS`
  (none yet). Any other version is rejected, so an older reader never
  silently misreads a newer file.

**Legacy layout.** The deliberately simple mapping:

- The `rawdata` group's channels (1 to 3, file order) become `channel1..3`,
  values as stored. Channels of unequal length are cut to the shortest
  (`dropped_rows` in the metadata says how much).
- The sampling frequency is `1 / wf_increment` of those channels (they must
  agree). It, and the loss below, are stored as JSON in
  `recording_metadata.post_metadata` under `TDMS_METADATA_KEY` (`"tdms"`).
- A TDMS waveform is gap-free by construction, so `timestamp` is
  `round(i * 1e6 / fs)` and `counter` is `i % 256` (no gaps). Packet loss is
  therefore NOT visible in `counter`; it comes from the `signalQuality`
  channels (100 = nothing lost): a `system` group's channel applies to the
  whole file, otherwise every other group holding a `signalQuality` channel
  is paired with a `rawdata` channel (by name prefix, else by file order).
  Loss per channel is `100 - mean(quality)`, the recording's the worst of
  them. Without usable quality data the loss is an assumed 0
  (`signal_loss_measured` is `False`).
- No sensors or conversions: every channel gets an empty `Sensor` and
  `NoConversion`.
- **Several STUs**: when no `system` group holds a `signalQuality` channel,
  two or more other groups do, and every `rawdata` channel name starts with
  exactly one of those groups' names (the longest match, e.g. `STU1_Channel1`
  belongs to group `STU1`), each such group is its own `Source` named after
  the group, with `stu_id` set to it. The sources don't share anything: each
  has its own channels (file order, at most 3), `wf_increment` (hence rate),
  length (`dropped_rows` is per source), start time and signal loss (100 - mean
  of its group's `signalQuality`), all in that source's `post_metadata`. Any
  other file is one source, as above (named `source1`).

TDMS is read-only: there is no writer. Needs `nptdms` (the `tdms` extra).

This module is an internal implementation detail. Don't import it directly
-- use ICOschema.model.python.recording.Recording.from_tdms() and
ICOschema.model.python.dataset_bundle.DatasetBundle.from_tdms() instead.
"""

from __future__ import annotations

import json
import warnings
from collections.abc import Callable
from typing import Any

import numpy as np

from icoschema.schema.generated.python import dataset as generated

TDMS_METADATA_KEY = "tdms"
"""Key in `recording_metadata.post_metadata` (a JSON object) under which the
legacy reader stores the sampling frequency and signal loss of the file."""

FORMAT_VERSION_PROPERTY = "icoschema_format_version"

RAW_GROUP = "rawdata"
SYSTEM_GROUP = "system"
QUALITY_CHANNEL = "signalQuality"
MAX_CHANNELS = 3

_DEFAULT_SOURCE_NAME = "source1"


def _quality_loss(channel: Any) -> float | None:
    """`100 - mean(quality)` of one `signalQuality` channel, `None` if it holds
    no numeric data (e.g. the empty void-typed channel some files have)."""
    try:
        data = np.asarray(channel[:])
    except Exception:  # noqa: BLE001 -- unreadable -> unknown
        return None
    if data.size == 0 or not np.issubdtype(data.dtype, np.number):
        return None
    finite = data[np.isfinite(data)].astype(np.float64)
    if finite.size == 0:
        return None
    return float(np.clip(100.0 - finite.mean(), 0.0, 100.0))


def _channel_losses(tdms: Any, raw_names: list[str]) -> tuple[str, list[float | None]]:
    """`(source, loss per raw channel)`; `source` is `system`, `groups` or `none`."""
    groups = {group.name: group for group in tdms.groups()}
    system = groups.get(SYSTEM_GROUP)
    if system is not None and QUALITY_CHANNEL in system:
        return "system", [_quality_loss(system[QUALITY_CHANNEL])] * len(raw_names)
    holders = [g for g in groups.values() if g.name != RAW_GROUP and QUALITY_CHANNEL in g]
    if not holders:
        return "none", [None] * len(raw_names)
    if len(holders) != len(raw_names):
        warnings.warn(
            f"{len(holders)} groups hold {QUALITY_CHANNEL} but {RAW_GROUP} has {len(raw_names)} channel(s); "
            "signal loss is assumed 0",
            stacklevel=4,
        )
        return "none", [None] * len(raw_names)
    by_prefix = [[g for g in holders if name.startswith(g.name)] for name in raw_names]
    if all(len(match) == 1 for match in by_prefix) and len({m[0].name for m in by_prefix}) == len(holders):
        ordered = [match[0] for match in by_prefix]
    else:
        ordered = holders
    return "groups", [_quality_loss(group[QUALITY_CHANNEL]) for group in ordered]


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
    """What `_read_channels` found: the rate, the values cut to the shortest
    channel, how many rows that dropped and the first channel's start time."""

    def __init__(self, fs: float, columns: list[list[float]], rows: int, dropped: int, start_time: str | None) -> None:
        self.fs, self.columns, self.rows, self.dropped, self.start_time = fs, columns, rows, dropped, start_time


def _read_channels(path: str, where: str, channels: list[Any]) -> _Read:
    """Reads waveform `channels` (all of one STU) that must agree on
    `wf_increment`. `where` names them in error messages."""
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
    rows = min(len(values) for values in data)
    if rows == 0:
        raise ValueError(f"{path}: the {where!r} channels hold no data")
    dropped = sum(len(values) - rows for values in data)
    columns = [values[:rows].astype(np.float64).tolist() for values in data]

    start = channels[0].properties.get("wf_start_time")
    start_time = str(np.datetime_as_string(np.datetime64(start, "us"), unit="us")) if start is not None else None
    return _Read(fs, columns, rows, dropped, start_time)


def _build(
    read: _Read, section: dict[str, Any]
) -> tuple[generated.HardwareMetadata, generated.RecordingMetadata, generated.RecordingData]:
    """The three parts of a `Source` for one STU's `read`."""

    def metadata() -> generated.ChannelMetadata:
        return generated.ChannelMetadata(sensor=generated.Sensor(), compensations=[generated.NoConversion(order=0)])

    count = len(read.columns)
    return (
        generated.HardwareMetadata(**{f"channel{i + 1}_metadata": metadata() for i in range(count)}),
        generated.RecordingMetadata(start_time=read.start_time, post_metadata=json.dumps({TDMS_METADATA_KEY: section})),
        generated.RecordingData(
            timestamp=np.rint(np.arange(read.rows) * 1e6 / read.fs).astype(np.int64).tolist(),
            counter=(np.arange(read.rows) % 256).tolist(),
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


def _load_stus(path: str, tdms: Any, members: dict[str, list[Any]]) -> generated.Recording:
    """One `Source` per STU group (see the module docstring)."""
    groups = {g.name: g for g in tdms.groups()}
    sources = []
    taken: set[str] = set()
    for group, channels in members.items():
        read = _read_channels(path, f"{RAW_GROUP} ({group})", channels)
        loss = _quality_loss(groups[group][QUALITY_CHANNEL])
        section = {
            "sampling_frequency": read.fs,
            "signal_loss_percentage": loss if loss is not None else 0.0,
            "signal_loss_measured": loss is not None,
            "signal_quality_source": "group",
            "channel_signal_loss_percentage": [loss] * len(channels),
            "channels": [channel.name for channel in channels],
            "dropped_rows": read.dropped,
            "group": group,
        }
        hardware, recording_metadata, recording_data = _build(read, section)
        sources.append(
            generated.Source(
                name=_source_name(group, taken),
                stu_id=group,
                hardware_metadata=hardware,
                recording_metadata=recording_metadata,
                recording_data=recording_data,
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
    source, losses = _channel_losses(tdms, [channel.name for channel in channels])
    known = [loss for loss in losses if loss is not None]
    section = {
        "sampling_frequency": read.fs,
        "signal_loss_percentage": max(known) if known else 0.0,
        "signal_loss_measured": bool(known),
        "signal_quality_source": source,
        "channel_signal_loss_percentage": losses,
        "channels": [channel.name for channel in channels],
        "dropped_rows": read.dropped,
    }
    hardware, recording_metadata, recording_data = _build(read, section)
    return generated.Recording(
        sources=[
            generated.Source(
                name=_DEFAULT_SOURCE_NAME,
                hardware_metadata=hardware,
                recording_metadata=recording_metadata,
                recording_data=recording_data,
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


def load_recording(path: str) -> generated.Recording:
    """The recording in the TDMS file at `path`. Raises `ValueError` for a
    file without a usable `rawdata` group or with an unknown format version,
    and `ImportError` if `nptdms` isn't installed."""
    try:
        from nptdms import TdmsFile  # type: ignore[import-untyped]
    except ImportError as error:
        raise ImportError("reading TDMS files needs nptdms: pip install icoschema[tdms]") from error

    tdms = TdmsFile.read(path)
    version = _format_version(tdms, path)
    if version is None:
        return _load_recording_legacy(path, tdms)
    return _PARSERS[version](path, tdms)
