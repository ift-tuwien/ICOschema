"""Adapter that reads/writes PyTables-style HDF5 files for the generated
`dataset` schema classes (see icoschema/v2/schema/generated/dataset.py).

This is schema version 2. Files of schema version 1 (`icoschema_format_version` "1.x", or none) are read with
`icoschema.v1`: their layouts, and the `sensors` table with physical/voltage ranges and a table-wide `conversion`
flag, are not read here.

Format versions of schema version 2 are registered in `_FORMATS` (the part before the dot of
`icoschema_format_version` is the schema version). Version "2.0" stores:

- the root attributes `icoschema_format_version`, `primary_table` (the name of every source's primary table),
  `writer`, and if the bundle has a provenance `source_format`, `source_format_version`, `reader`, which say
  where the data was originally read from; plus `preprocessed_table` (the name of the preprocessed tables) if it
  has any, and `sources` (the names of the sources, in order) with several sources;
- one source at the root, or several under `/sources/<name>/` (the root attribute `sources` lists their names in
  order; the name comes from the group). A source (at the root or in its group) is its primary table, a
  `sensors` table, and optionally a `quality` dataset (the source's signal quality in percent, attribute
  `sampling_frequency`) and a preprocessed table;
- the primary table: `counter` (optional: a source without one is a gap-free waveform, see
  dataset.yaml) and `timestamp` columns plus one to three channel columns. Attributes, all optional: `Start_Time`,
  `adc_reference_voltage`, `description`, `stu_mac`, `sth_mac`, `source_name` (always stored for a
  single source), `sampling_frequency` (Hz, per channel), `additional_data` (opaque JSON), `pre_metadata`/
  `post_metadata` (opaque JSON strings) and the ADC settings `adc_prescaler`/`adc_acquisition_time`/
  `adc_oversample_rate`. Any other attribute that isn't PyTables bookkeeping is kept (see `preserved.py`);
- the `sensors` table, one row per channel column *in the same order* (nothing else records which row belongs to
  which column): the text columns `dimension`, `name`, `sensor_id`, `sensor_type`, `unit` (empty = not set), and
  the channel's conversion: `conversion` ("none" or "linear") with, for "linear", `gain` and `offset`;
- the preprocessed table: a `timestamp` column (`<u8`) and the channel columns `channel1`..`channel3`
  (`<f4`), with `channel_sampling_frequency`/`sampling_frequency_source`/`fill_method`/`producer` attributes.
  It shares the `sensors` table (see dataset.yaml);
- `/computations/`: every `DerivedDataset` in its true N-D shape (`shape`/`dtype` are never stored as attributes
  since `h5py.Dataset.shape`/`.dtype` provide them); only `source`/`unit`/`produced_by`/`produced_at`/`params`/
  `description` become dataset attributes. A `DerivedDataset` that belongs to one source has a `source`
  attribute (the source's name); without one it belongs to the recording as a whole;
- `/pictures/<name>` (a set of images, each one base64 text) and `/files/<name>` (an embedded file with its
  `size`, `mime` and `original_name`), see `attachments.py`; the data acquisition's older places for them (root
  arrays with "picture" in their name, `/embedded_files/`) are read too;
- `/steps/`: an empty group per `ComputationStep` named by its `node`, with every field as an attribute (lists as
  string arrays, absent fields omitted), read back ordered by `step_index` and renumbered 0, 1, 2, ...

Everything a file has that is not described here is kept, not dropped, and written back where it was (see
`preserved.py`). Every dataset with more than one element is stored gzip-compressed (with shuffle). An unknown version is
rejected, so an older reader never silently drops parts of a newer file.

This module is an internal implementation detail. Don't import it directly
-- use icoschema.v2.model.recording.Recording.from_hdf5()/.to_hdf5() and
icoschema.v2.model.dataset_bundle.DatasetBundle.from_hdf5()/.to_hdf5()
instead.
"""

import dataclasses
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import h5py
import numpy as np

from icoschema._version import software_id

from ..model.attachments import EmbeddedFile
from ..schema.generated.dataset import (
    ChannelMetadata,
    ComputationStep,
    Conversion,
    DatasetBundle,
    DerivedDataset,
    HardwareMetadata,
    LinearConversion,
    NoConversion,
    PreprocessedRecording,
    Provenance,
    QualityChannel,
    Recording,
    RecordingData,
    RecordingMetadata,
    Sensor,
    Source,
)
from . import attachments
from .preserved import (
    COMPRESSION as _COMPRESSION,
)
from .preserved import (
    Preserved,
    capture_children,
    capture_group_attrs,
    capture_node,
    write_preserved,
)

logger = logging.getLogger(__name__)

_NON_CHANNEL_COLUMNS = {"counter", "timestamp"}
_CHANNEL_SLOTS = ("channel1", "channel2", "channel3")
_CHANNEL_METADATA_SLOTS = ("channel1_metadata", "channel2_metadata", "channel3_metadata")

_QUALITY_DATASET = "quality"
_PROVENANCE_ATTRS = ("source_format", "source_format_version", "reader")
_COMPUTATIONS_GROUP = "computations"
_STEPS_GROUP = "steps"
_SOURCES_GROUP = "sources"
_STEP_STRING_ATTRS = (
    "producer",
    "params",
    "resolved_params",
    "status",
    "error",
    "summary",
    "started_at",
    "environment",
    "source_node",
)
_STEP_LIST_ATTRS = ("inputs", "output_keys")
_PREPROCESSED_TABLE = "preprocessed"

_METADATA_ATTRS = ("pre_metadata", "post_metadata")
_SOURCE_ATTRS = ("description", "stu_mac", "sth_mac")
_SOURCE_DATA_ATTRS = ("sampling_frequency", "additional_data")
# Written on the primary table only when set; a file without it reads as the default source name.
_SOURCE_NAME_ATTR = "source_name"
_DEFAULT_SOURCE_NAME = "source1"
_ADC_SETTING_ATTRS = ("adc_prescaler", "adc_acquisition_time", "adc_oversample_rate")
_PREPROCESSED_ATTRS = ("channel_sampling_frequency", "sampling_frequency_source", "fill_method", "producer")
_KNOWN_PRIMARY_ATTRS = {
    "Start_Time",
    "adc_reference_voltage",
    *_METADATA_ATTRS,
    *_ADC_SETTING_ATTRS,
    *_SOURCE_ATTRS,
    *_SOURCE_DATA_ATTRS,
    _SOURCE_NAME_ATTR,
}
_CONVERSION_NONE = "none"
_CONVERSION_LINEAR = "linear"

_SENSOR_DTYPE = [
    ("dimension", "S100"),
    ("name", "S100"),
    ("sensor_id", "S100"),
    ("sensor_type", "S100"),
    ("unit", "S10"),
    ("conversion", "S10"),
    ("gain", "<f8"),
    ("offset", "<f8"),
]


def _decode(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


def _create_dataset(parent: h5py.Group, name: str, data: np.ndarray) -> h5py.Dataset:
    """Create a dataset, compressed unless it's too small to benefit."""
    return parent.create_dataset(name, data=data, **(_COMPRESSION if data.size > 1 else {}))


def _optional_str(attrs: h5py.AttributeManager, name: str) -> str | None:
    return _decode(attrs[name]) if name in attrs else None


def _optional_int(attrs: h5py.AttributeManager, name: str) -> int | None:
    if name not in attrs:
        return None
    value = attrs[name]
    try:
        return int(_decode(value)) if isinstance(value, (bytes, str)) else int(value)
    except (TypeError, ValueError):
        raise ValueError(f"primary table attribute {name!r} must be an integer, got {value!r}") from None


def _optional_float(attrs: h5py.AttributeManager, name: str) -> float | None:
    return float(attrs[name]) if name in attrs else None


# ── read: Recording ──────────────────────────────────────────────────────────

def _row_str(row, column: str) -> str | None:
    """A text column of a sensors row; an empty one is a value that was not set."""
    return row[column].decode() or None


def _load_sensor(row) -> Sensor:
    return Sensor(
        sensor_id=_row_str(row, "sensor_id"),
        sensor_type=_row_str(row, "sensor_type"),
        name=_row_str(row, "name"),
        unit=_row_str(row, "unit"),
        dimension=_row_str(row, "dimension"),
    )


def _load_conversion(row) -> Conversion:
    kind = row["conversion"].decode()
    if kind == _CONVERSION_NONE:
        return NoConversion()
    if kind == _CONVERSION_LINEAR:
        return LinearConversion(gain=float(row["gain"]), offset=float(row["offset"]))
    raise ValueError(f"unknown conversion {kind!r} in the sensors table (known: 'none', 'linear')")


def _load_source_from_table(f: h5py.Group, table_name: str, name: str | None = None) -> Source:
    """Build a Source from f[table_name] and f["sensors"] (`f` is the file
    or a source group). `name` overrides the stored `source_name` attribute.

    Shared by every layout of a format version; the only thing that differs
    between them is how `table_name` itself is determined and where the
    source is.
    """
    table_ds = f[table_name]
    table = table_ds[:]
    if "sensors" not in f:
        raise ValueError(f"{f.name!r} has a table {table_name!r} but no `sensors` table")
    sensor_rows = f["sensors"][:]

    channel_columns = [name for name in table.dtype.names if name not in _NON_CHANNEL_COLUMNS]
    if len(channel_columns) != len(sensor_rows):
        raise ValueError(
            f"Expected one sensor row per channel column, got "
            f"{len(channel_columns)} channel column(s) and {len(sensor_rows)} sensor row(s)."
        )
    if len(channel_columns) > len(_CHANNEL_SLOTS):
        raise ValueError(
            f"Recording supports at most {len(_CHANNEL_SLOTS)} channels, "
            f"got {len(channel_columns)}."
        )

    recording_data_kwargs = {
        "timestamp": table["timestamp"].tolist(),
        "counter": table["counter"].tolist() if "counter" in table.dtype.names else [],
    }
    quality = None
    if _QUALITY_DATASET in f:
        quality_ds = f[_QUALITY_DATASET]
        quality = QualityChannel(
            values=quality_ds[:].astype(np.float64).tolist(),
            sampling_frequency=_optional_float(quality_ds.attrs, "sampling_frequency"),
        )
    hardware_metadata_kwargs = {
        "adc_reference_voltage": _optional_str(table_ds.attrs, "adc_reference_voltage"),
        **{name: _optional_int(table_ds.attrs, name) for name in _ADC_SETTING_ATTRS},
    }
    for channel_slot, metadata_slot, column, sensor_row in zip(
        _CHANNEL_SLOTS, _CHANNEL_METADATA_SLOTS, channel_columns, sensor_rows
    ):
        recording_data_kwargs[channel_slot] = table[column].tolist()
        hardware_metadata_kwargs[metadata_slot] = ChannelMetadata(
            sensor=_load_sensor(sensor_row), conversion=_load_conversion(sensor_row)
        )

    return Source(
        name=name or _optional_str(table_ds.attrs, _SOURCE_NAME_ATTR) or _DEFAULT_SOURCE_NAME,
        **{name: _optional_str(table_ds.attrs, name) for name in _SOURCE_ATTRS},
        sampling_frequency=_optional_float(table_ds.attrs, "sampling_frequency"),
        additional_data=_optional_str(table_ds.attrs, "additional_data"),
        quality=quality,
        recording_metadata=RecordingMetadata(
            start_time=_optional_str(table_ds.attrs, "Start_Time"),
            **{name: _optional_str(table_ds.attrs, name) for name in _METADATA_ATTRS},
        ),
        hardware_metadata=HardwareMetadata(**hardware_metadata_kwargs),
        recording_data=RecordingData(**recording_data_kwargs),
    )


def _load_recording_root(f: h5py.File) -> Recording:
    return Recording(sources=[_load_source_from_table(f, _decode(f.attrs["primary_table"]))])


def _load_recording_sources(f: h5py.File) -> Recording:
    table_name = _decode(f.attrs["primary_table"])
    if "sources" not in f.attrs or _SOURCES_GROUP not in f:
        raise ValueError("a file with several sources needs a `sources` attribute and a /sources/ group")
    names = [_decode(name) for name in np.atleast_1d(f.attrs["sources"])]
    if not names:
        raise ValueError("a file with a `sources` attribute must list at least one source")
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate source names in `sources` attribute: {names}")
    group = f[_SOURCES_GROUP]
    missing = [name for name in names if name not in group]
    if missing:
        raise ValueError(f"sources {missing} are listed but have no group under /{_SOURCES_GROUP}/")
    unlisted = sorted(set(group) - set(names))
    if unlisted:
        logger.warning("Groups under /%s/ that are not listed as sources are ignored: %s", _SOURCES_GROUP, unlisted)
    return Recording(sources=[_load_source_from_table(group[name], table_name, name) for name in names])


def _load_recording(f: h5py.File) -> Recording:
    return _load_recording_sources(f) if "sources" in f.attrs else _load_recording_root(f)


FormatVersion = Literal["2.0"]
"""The versions `save_*`/`to_hdf5` can write (a test keeps this in step with `_FORMATS`)."""


@dataclasses.dataclass(frozen=True)
class FormatSpec:
    """One file format version: how to read it and what it can hold. The writer needs nothing else, so a new
    version is one more entry in `_FORMATS` (plus its reader)."""

    version: str
    read: Callable[[h5py.File], Recording]
    preprocessed: bool = False  # an optional preprocessed table
    steps: bool = False  # an optional /steps/ group
    # Where the sources are: "root" (one source, the primary table at the root), "sources" (always under
    # /sources/<name>/, so several are possible) or "either" (at the root for one source, else under /sources/).
    sources: Literal["root", "sources", "either"] = "root"
    source_features: bool = False  # sources without a counter, or with a rate, quality or additional data
    writable: bool = True


_FORMATS: dict[str, FormatSpec] = {
    spec.version: spec
    for spec in (
        FormatSpec("2.0", _load_recording, preprocessed=True, steps=True, sources="either", source_features=True),
    )
}  # in the order the versions appeared: the writer picks the first that fits


def readable_versions() -> tuple[str, ...]:
    """Every format version `load_*` reads."""
    return tuple(_FORMATS)


def writable_versions() -> tuple[str, ...]:
    """Every format version `save_*` can write, oldest first."""
    return tuple(version for version, spec in _FORMATS.items() if spec.writable)


def _file_format(f: h5py.File, path: str) -> FormatSpec:
    """The format of the file: its `icoschema_format_version`; raises `ValueError` for a version this reader
    doesn't know, naming the schema version that reads it if it is another one."""
    version = f.attrs.get("icoschema_format_version")
    if version is None:
        raise ValueError(
            f"{path!r} has no icoschema_format_version: it is a file of schema version 1, read with icoschema.v1"
        )
    version = _decode(version)
    if version not in _FORMATS:
        major = version.partition(".")[0]
        hint = f" (schema version {major}: read it with icoschema.v{major})" if major.isdigit() and major != "2" else ""
        raise ValueError(
            f"Unsupported icoschema_format_version {version!r} in {path!r}{hint}; supported versions: {sorted(_FORMATS)}"
        )
    return _FORMATS[version]


def load_recording(path: str) -> Recording:
    with h5py.File(path, "r") as f:
        return _file_format(f, path).read(f)


# ── read: PreprocessedRecording ─────────────────────────────────────────────

def _read_preprocessed_table(
    parent: h5py.Group, table_name: str, path: str, source: str
) -> PreprocessedRecording:
    """The preprocessed table `table_name` in `parent` (the file, or a source
    group), built from `source`. Raises `ValueError` if the table is missing
    or lacks a required attribute -- it's primary data, so it's never skipped
    silently."""
    if table_name not in parent:
        raise ValueError(f"preprocessed table {table_name!r} declared in {path!r} does not exist")
    ds = parent[table_name]
    missing = [name for name in _PREPROCESSED_ATTRS if name not in ds.attrs]
    if missing:
        raise ValueError(f"preprocessed table {table_name!r} in {path!r} lacks attributes {missing}")
    table = ds[:]
    columns = set(table.dtype.names or ())
    if "timestamp" not in columns or "channel1" not in columns:
        raise ValueError(f"preprocessed table {table_name!r} in {path!r} needs timestamp and channel1 columns")
    return PreprocessedRecording(
        source=source,
        timestamp=table["timestamp"].tolist(),
        **{name: table[name].tolist() for name in _CHANNEL_SLOTS if name in columns},
        channel_sampling_frequency=float(ds.attrs["channel_sampling_frequency"]),
        sampling_frequency_source=_decode(ds.attrs["sampling_frequency_source"]),
        fill_method=_decode(ds.attrs["fill_method"]),
        producer=_decode(ds.attrs["producer"]),
    )


def _has_sources_layout(f: h5py.File, spec: FormatSpec) -> bool:
    """Whether the file stores its sources under `/sources/` (several, or a format that always does)."""
    return spec.sources == "sources" or (spec.sources == "either" and "sources" in f.attrs)


def _load_preprocessed(f: h5py.File, path: str, recording: Recording) -> list[PreprocessedRecording]:
    """The preprocessed tables of a file (none for a file without any): the
    one at the root for a single source, one per source group that has one
    for several. Each gets its source's name."""
    spec = _file_format(f, path)
    if not spec.preprocessed or "preprocessed_table" not in f.attrs:
        return []
    table_name = _decode(f.attrs["preprocessed_table"])
    if not _has_sources_layout(f, spec):
        return [_read_preprocessed_table(f, table_name, path, str(next(iter(recording.sources))))]
    tables = [
        _read_preprocessed_table(f[_SOURCES_GROUP][str(name)], table_name, path, str(name))
        for name in recording.sources
        if table_name in f[_SOURCES_GROUP][str(name)]
    ]
    if not tables:
        raise ValueError(f"preprocessed table {table_name!r} declared in {path!r} does not exist")
    return tables


# ── write: Recording ─────────────────────────────────────────────────────────

def _sensor_row(channel_metadata: ChannelMetadata) -> np.ndarray:
    """The `sensors` row of a channel: its sensor and its conversion."""
    sensor = channel_metadata.sensor
    conversion = channel_metadata.conversion
    if isinstance(conversion, LinearConversion):
        kind, gain, offset = _CONVERSION_LINEAR, conversion.gain, conversion.offset
    elif isinstance(conversion, NoConversion):
        kind, gain, offset = _CONVERSION_NONE, 1.0, 0.0
    else:
        raise TypeError(f"Cannot write a conversion of type {type(conversion).__name__}")
    row = np.zeros(1, dtype=_SENSOR_DTYPE)
    row["dimension"] = (sensor.dimension or "").encode()
    row["name"] = (sensor.name or "").encode()
    row["sensor_id"] = (sensor.sensor_id or "").encode()
    row["sensor_type"] = (sensor.sensor_type or "").encode()
    row["unit"] = (sensor.unit or "").encode()
    row["conversion"] = kind.encode()
    row["gain"] = gain
    row["offset"] = offset
    return row


def _write_primary_attrs(
    ds: h5py.Dataset,
    *,
    start_time: str | None = None,
    adc_reference_voltage: object = None,
    pre_metadata: str | None = None,
    post_metadata: str | None = None,
    description: str | None = None,
    stu_mac: str | None = None,
    sth_mac: str | None = None,
    sampling_frequency: float | None = None,
    additional_data: str | None = None,
    adc_prescaler: int | None = None,
    adc_acquisition_time: int | None = None,
    adc_oversample_rate: int | None = None,
) -> None:
    """Set the attributes of a source's primary table that are not None (shared by `save_*` and the
    `BundleWriter`, so both write them the same way)."""
    texts = {
        "Start_Time": start_time,
        "adc_reference_voltage": None if adc_reference_voltage is None else str(adc_reference_voltage),
        "pre_metadata": pre_metadata,
        "post_metadata": post_metadata,
        "description": description,
        "stu_mac": stu_mac,
        "sth_mac": sth_mac,
        "additional_data": additional_data,
    }
    for name, value in texts.items():
        if value is not None:
            ds.attrs[name] = value
    if sampling_frequency is not None:
        ds.attrs["sampling_frequency"] = float(sampling_frequency)
    for name, value in (
        ("adc_prescaler", adc_prescaler),
        ("adc_acquisition_time", adc_acquisition_time),
        ("adc_oversample_rate", adc_oversample_rate),
    ):
        if value is not None:
            ds.attrs[name] = int(value)


def _write_recording_table(
    f: h5py.Group, source: Source, table_name: str, *, store_name: bool = True, always_name: bool = False
) -> None:
    data = source.recording_data
    hardware = source.hardware_metadata

    present_channels = [
        (channel_slot, metadata_slot)
        for channel_slot, metadata_slot in zip(_CHANNEL_SLOTS, _CHANNEL_METADATA_SLOTS)
        if getattr(data, channel_slot)
    ]
    sensor_rows = []
    for channel_slot, metadata_slot in present_channels:
        channel_metadata = getattr(hardware, metadata_slot)
        if channel_metadata is None:
            raise ValueError(f"source {str(source.name)!r} has {channel_slot} data but no {metadata_slot}")
        sensor_rows.append(_sensor_row(channel_metadata))

    has_counter = bool(data.counter)
    dtype = (
        ([("counter", "u1")] if has_counter else [])
        + [("timestamp", "<u8")]
        + [(slot, "<f4") for slot, _ in present_channels]
    )
    table = np.zeros(len(data.timestamp), dtype=dtype)
    if has_counter:
        table["counter"] = data.counter
    table["timestamp"] = data.timestamp
    for channel_slot, _metadata_slot in present_channels:
        table[channel_slot] = getattr(data, channel_slot)

    ds = _create_dataset(f, table_name, table)
    _write_primary_attrs(
        ds,
        start_time=source.recording_metadata.start_time,
        adc_reference_voltage=hardware.adc_reference_voltage,
        pre_metadata=source.recording_metadata.pre_metadata,
        post_metadata=source.recording_metadata.post_metadata,
        description=source.description,
        stu_mac=source.stu_mac,
        sth_mac=source.sth_mac,
        sampling_frequency=source.sampling_frequency,
        additional_data=source.additional_data,
        adc_prescaler=hardware.adc_prescaler,
        adc_acquisition_time=hardware.adc_acquisition_time,
        adc_oversample_rate=hardware.adc_oversample_rate,
    )
    if store_name and (always_name or str(source.name) != _DEFAULT_SOURCE_NAME):
        ds.attrs[_SOURCE_NAME_ATTR] = str(source.name)
    if source.quality is not None and source.quality.values:
        quality_ds = _create_dataset(f, _QUALITY_DATASET, np.asarray(source.quality.values, dtype="<f4"))
        if source.quality.sampling_frequency is not None:
            quality_ds.attrs["sampling_frequency"] = float(source.quality.sampling_frequency)

    _create_dataset(f, "sensors", np.concatenate(sensor_rows))


def _write_preprocessed_table(f: h5py.Group, preprocessed: PreprocessedRecording, table_name: str) -> None:
    present_channels = [slot for slot in _CHANNEL_SLOTS if getattr(preprocessed, slot)]
    dtype = [("timestamp", "<u8")] + [(slot, "<f4") for slot in present_channels]
    table = np.zeros(len(preprocessed.timestamp), dtype=dtype)
    table["timestamp"] = preprocessed.timestamp
    for slot in present_channels:
        table[slot] = getattr(preprocessed, slot)

    ds = _create_dataset(f, table_name, table)
    ds.attrs["channel_sampling_frequency"] = float(preprocessed.channel_sampling_frequency)
    # LinkML enums render as a str subclass h5py can't store; encode/decode yields a plain str.
    ds.attrs["sampling_frequency_source"] = str(preprocessed.sampling_frequency_source).encode().decode()
    ds.attrs["fill_method"] = preprocessed.fill_method
    ds.attrs["producer"] = preprocessed.producer


def _write_steps(f: h5py.File, steps: list[ComputationStep]) -> None:
    group = f.create_group(_STEPS_GROUP)
    for step in steps:
        step_group = group.create_group(str(step.node))
        step_group.attrs["step_index"] = int(step.step_index)
        for name in _STEP_STRING_ATTRS:
            value = getattr(step, name)
            if value is not None:
                # LinkML enums render as a str subclass h5py can't store; encode/decode yields a plain str.
                step_group.attrs[name] = str(value).encode().decode()
        if step.duration_s is not None:
            step_group.attrs["duration_s"] = float(step.duration_s)
        for name in _STEP_LIST_ATTRS:
            step_group.attrs.create(name, [str(v) for v in getattr(step, name)], dtype=h5py.string_dtype())


# ── read: ComputationStep ───────────────────────────────────────────────────

def _read_step(step_group: h5py.Group, node: str) -> ComputationStep:
    attrs = step_group.attrs
    return ComputationStep(
        node=node,
        step_index=int(attrs["step_index"]),
        **{name: _decode(attrs[name]) for name in _STEP_STRING_ATTRS if name in attrs},
        **({"duration_s": float(attrs["duration_s"])} if "duration_s" in attrs else {}),
        **{name: [_decode(v) for v in attrs[name]] for name in _STEP_LIST_ATTRS if name in attrs},
    )


def _load_steps(
    f: h5py.File, path: str, computations: dict[str, DerivedDataset], on_error: Literal["skip", "raise"]
) -> list[ComputationStep]:
    """The steps of a file, ordered by `step_index` and renumbered 0, 1,
    2, ... A malformed step, or one whose `output_keys` aren't all in
    `computations` (e.g. because a malformed computation was skipped), is
    logged and dropped -- or raises with `on_error="raise"`."""
    if not _file_format(f, path).steps or _STEPS_GROUP not in f:
        return []
    steps: list[ComputationStep] = []
    for node, step_group in f[_STEPS_GROUP].items():
        try:
            if not isinstance(step_group, h5py.Group):
                raise TypeError(f"step {node!r} is not a group")
            step = _read_step(step_group, node)
            missing = [key for key in step.output_keys if key not in computations]
            if missing:
                raise ValueError(f"step {node!r} lists output_keys missing from computations: {missing}")
        except Exception:
            if on_error == "raise":
                raise
            logger.warning("Skipping malformed step %r in %r", node, path, exc_info=True)
            continue
        steps.append(step)
    steps.sort(key=lambda step: (step.step_index, str(step.node)))
    return [dataclasses.replace(step, step_index=i) for i, step in enumerate(steps)]


def _source_features(source: Source) -> list[str]:
    """What a source has that only formats with `source_features` can store."""
    features = []
    if not source.recording_data.counter:
        features.append("no packet counter")
    if source.sampling_frequency is not None:
        features.append("a sampling_frequency")
    if source.quality is not None:
        features.append("quality")
    if source.additional_data is not None:
        features.append("additional_data")
    return features


def _unrepresentable(bundle: DatasetBundle, spec: FormatSpec) -> list[str]:
    """Why `spec` can't hold `bundle` (empty if it can)."""
    if not spec.writable:
        return [f"format {spec.version!r} can only be read"]
    reasons = []
    if bundle.preprocessed_tables and not spec.preprocessed:
        reasons.append("it has a preprocessed table")
    if bundle.steps and not spec.steps:
        reasons.append("it has computation steps")
    if len(bundle.recording.sources) > 1 and spec.sources == "root":
        reasons.append(f"it has {len(bundle.recording.sources)} sources")
    if not spec.source_features:
        for source in bundle.recording.sources.values():
            if features := _source_features(source):
                reasons.append(f"source {str(source.name)!r} has {', '.join(features)}")
    return reasons


def _choose_format(bundle: DatasetBundle, format_version: str | None) -> FormatSpec:
    """The format to write `bundle` in: `format_version`, or (if `None`) the oldest version that can hold it,
    so files without the newer parts stay readable by older readers. Raises `ValueError` if the version is
    unknown, or can't hold the bundle -- nothing is dropped silently."""
    if format_version is None:
        return next(spec for spec in _FORMATS.values() if not _unrepresentable(bundle, spec))
    spec = _FORMATS.get(format_version)
    if spec is None or not spec.writable:
        raise ValueError(f"Cannot write format_version {format_version!r}; writable versions: {list(writable_versions())}")
    if reasons := _unrepresentable(bundle, spec):
        raise ValueError(f"Cannot write format {format_version!r}: " + "; ".join(reasons))
    return spec


def _write_provenance(f: h5py.File, provenance: Provenance | None) -> None:
    f.attrs["writer"] = software_id()
    if provenance is not None:
        for name in _PROVENANCE_ATTRS:
            value = getattr(provenance, name)
            if value is not None:
                f.attrs[name] = str(value)


def _read_provenance(f: h5py.File, version: str) -> Provenance:
    """What the file says about where its data came from; a file that says nothing
    is data read from HDF5 of its own format version."""
    if "source_format" in f.attrs:
        origin = {name: _optional_str(f.attrs, name) for name in _PROVENANCE_ATTRS}
    else:
        origin = {"source_format": "hdf5", "source_format_version": version, "reader": software_id()}
    return Provenance(**origin, writer=_optional_str(f.attrs, "writer"))


def _write_recording(f: h5py.File, recording: Recording, table_name: str, spec: FormatSpec) -> bool:
    """Write the sources of `recording` as `spec` lays them out; returns whether it used the `/sources/`
    layout. A single source is the primary table at the root unless the format always uses `/sources/`
    (a format with `sources="sources"`). With `source_features` a single source's name is always stored."""
    sources = list(recording.sources.values())
    f.attrs["primary_table"] = table_name
    if len(sources) == 1 and spec.sources != "sources":
        _write_recording_table(f, sources[0], table_name, always_name=spec.source_features)
        return False
    f.attrs.create("sources", [str(source.name) for source in sources], dtype=h5py.string_dtype())
    group = f.create_group(_SOURCES_GROUP)
    for source in sources:
        _write_recording_table(group.create_group(str(source.name)), source, table_name, store_name=False)
    return True


def save_recording(
    recording: Recording, path: str, *, table_name: str = "recording", format_version: FormatVersion | None = None
) -> None:
    """Write a Recording to a fresh HDF5 file: in `format_version`, or (by default) the oldest version that
    can hold it. See `save_dataset_bundle`."""
    save_dataset_bundle(
        DatasetBundle(recording=recording), path, table_name=table_name, format_version=format_version
    )


# ── read/write: DerivedDataset / DatasetBundle ──────────────────────────────

def _write_derived_dataset(computations_group: h5py.Group, key: str, derived: DerivedDataset) -> None:
    array = np.asarray(derived.values, dtype=derived.dtype).reshape(derived.shape)
    ds = _create_dataset(computations_group, key, array)
    for attr_name in ("unit", "produced_by", "produced_at", "params", "description"):
        value = getattr(derived, attr_name)
        if value is not None:
            ds.attrs[attr_name] = value


def _read_derived_dataset(ds: h5py.Dataset, key: str) -> DerivedDataset:
    array = ds[()]
    return DerivedDataset(
        key=key,
        values=np.asarray(array).ravel().tolist(),
        shape=list(ds.shape),
        dtype=str(ds.dtype),
        unit=ds.attrs.get("unit"),
        produced_by=ds.attrs.get("produced_by"),
        produced_at=ds.attrs.get("produced_at"),
        params=ds.attrs.get("params"),
        description=ds.attrs.get("description"),
    )


def _tables_by_source(bundle: DatasetBundle) -> dict[str, PreprocessedRecording]:
    """The bundle's preprocessed tables by source name. A table without a
    `source` belongs to the recording's only source."""
    names = [str(name) for name in bundle.recording.sources]
    tables: dict[str, PreprocessedRecording] = {}
    for table in bundle.preprocessed_tables:
        name = table.source if table.source is not None else (names[0] if len(names) == 1 else None)
        if name is None:
            raise ValueError(f"a preprocessed table has no source, and the recording has several: {names}")
        if str(name) not in names:
            raise ValueError(f"preprocessed table for unknown source {str(name)!r}")
        if str(name) in tables:
            raise ValueError(f"more than one preprocessed table for source {str(name)!r}")
        tables[str(name)] = table
    return tables


def save_dataset_bundle(
    bundle: DatasetBundle,
    path: str,
    *,
    table_name: str = "recording",
    format_version: FormatVersion | None = None,
) -> None:
    """Write a DatasetBundle: the recording as the primary table (or one per
    source), the preprocessed tables if any, every DerivedDataset under a
    `/computations/` group, each in its true N-D shape, and the steps under
    `/steps/`. Writes `format_version`, or by default the oldest format that
    can hold the bundle (see `_FORMATS`). Raises `ValueError` (before
    anything is written) if `format_version` is unknown
    or can't hold the bundle.

    Doesn't check that the preprocessed tables fit their sources or that the
    steps are consistent -- that's the model layer's job
    (`DatasetBundle.to_hdf5`)."""
    tables = _tables_by_source(bundle)
    spec = _choose_format(bundle, format_version)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        multiple = _write_recording(f, bundle.recording, table_name, spec)
        _write_provenance(f, bundle.provenance)
        f.attrs["icoschema_format_version"] = spec.version
        if tables:
            f.attrs["preprocessed_table"] = _PREPROCESSED_TABLE
            for name, table in tables.items():
                parent = f[_SOURCES_GROUP][name] if multiple else f
                _write_preprocessed_table(parent, table, _PREPROCESSED_TABLE)
        if bundle.steps:
            _write_steps(f, list(bundle.steps))

        if bundle.computations:
            computations_group = f.create_group(_COMPUTATIONS_GROUP)
            for key, derived in bundle.computations.items():
                _write_derived_dataset(computations_group, key, derived)

        attachments.write_attachments(f, dict(getattr(bundle, "pictures", {}) or {}), dict(getattr(bundle, "files", {}) or {}))
        preserved = getattr(bundle, "preserved", None)
        if preserved:
            write_preserved(f, preserved, {PRIMARY_TOKEN: table_name, PREPROCESSED_TOKEN: _PREPROCESSED_TABLE})


PRIMARY_TOKEN = "{primary}"
PREPROCESSED_TOKEN = "{preprocessed}"
"""Stand for the names of the primary and the preprocessed table in the paths of `Preserved` (a file is saved
with the names of the writer, not those of the file it was read from)."""

_STEP_KNOWN_ATTRS = {"step_index", "duration_s", *_STEP_STRING_ATTRS, *_STEP_LIST_ATTRS}
_DERIVED_KNOWN_ATTRS = {"unit", "produced_by", "produced_at", "params", "description"}
_ROOT_KNOWN_ATTRS = frozenset(
    {"icoschema_format_version", "primary_table", "writer", "preprocessed_table", "sources", *_PROVENANCE_ATTRS}
)


@dataclasses.dataclass(frozen=True)
class Layout:
    """Where a file keeps what this package models, to tell what it doesn't (schema version 2, or the layouts
    of schema version 1 when `icoschema.migrate` brings their pictures, files and unknown parts along)."""

    table_name: str
    multiple: bool  # the sources are under /sources/<name>/
    source_names: tuple[str, ...]
    preprocessed_name: str = _PREPROCESSED_TABLE
    known_primary_attrs: frozenset[str] = frozenset(_KNOWN_PRIMARY_ATTRS)
    known_root_attrs: frozenset[str] = _ROOT_KNOWN_ATTRS
    known_sensor_columns: frozenset[str] = frozenset(name for name, _ in _SENSOR_DTYPE)

    @property
    def source_children(self) -> set[str]:
        return {self.table_name, "sensors", _QUALITY_DATASET, self.preprocessed_name}


@dataclasses.dataclass
class Extras:
    """What a file has next to the recording, the preprocessed tables, the computations and the steps."""

    pictures: dict[str, list[str]] = dataclasses.field(default_factory=dict)
    files: dict[str, EmbeddedFile] = dataclasses.field(default_factory=dict)
    preserved: Preserved = dataclasses.field(default_factory=Preserved)


def _join(*parts: str) -> str:
    return "/".join(part for part in parts if part)


def _is_group(f: h5py.Group, name: str) -> bool:
    return isinstance(f.get(name), h5py.Group)


def _root_known(f: h5py.File, layout: Layout) -> set[str]:
    """The names at the root of the file that belong to the layout (not the attachments, see `Extras`)."""
    known = {name for name in (_COMPUTATIONS_GROUP, _STEPS_GROUP) if _is_group(f, name)}
    known |= {_SOURCES_GROUP} if layout.multiple else layout.source_children
    return known


def _absorb(into: Preserved, other: Preserved) -> None:
    for path, attrs in other.attrs.items():
        into.attrs.setdefault(path, {}).update(attrs)
    into.nodes.update(other.nodes)


def _collect_source(group: h5py.Group, path: str, layout: Layout, in_group: bool, preserved: Preserved) -> None:
    children = layout.source_children
    if layout.table_name in group:
        capture_group_attrs(group[layout.table_name], _join(path, PRIMARY_TOKEN), layout.known_primary_attrs, preserved)
    if "sensors" in group:
        sensors = group["sensors"]
        capture_group_attrs(sensors, _join(path, "sensors"), (), preserved)
        extra_columns = sorted(set(getattr(sensors.dtype, "names", None) or ()) - layout.known_sensor_columns)
        if extra_columns:
            # The sensors table has no place for these columns: keep the table as it was, next to the new one
            logger.info("Keeping the original sensors table of %r (it has the columns %s)", path or "/", extra_columns)
            node = capture_node(group, "sensors")
            if node is not None:
                preserved.nodes[_join(path, "sensors__original")] = node
    if _QUALITY_DATASET in group:
        capture_group_attrs(group[_QUALITY_DATASET], _join(path, _QUALITY_DATASET), ("sampling_frequency",), preserved)
    if layout.preprocessed_name in group:
        capture_group_attrs(
            group[layout.preprocessed_name], _join(path, PREPROCESSED_TOKEN), _PREPROCESSED_ATTRS, preserved
        )
    if in_group:
        capture_group_attrs(group, path, (), preserved)
        capture_children(group, path, lambda name: name in children, preserved)


def _collect_computations(group: h5py.Group, path: str, prefix: str, keys: set[str], preserved: Preserved) -> bool:
    """Preserve what is in `/computations/` and isn't one of `keys`. Returns whether anything below is one."""
    found = False
    local = Preserved()
    for name in group:
        child_path = f"{path}/{name}"
        obj = group.get(name) if isinstance(group.get(name, getlink=True), h5py.HardLink) else None
        if isinstance(obj, h5py.Dataset) and f"{prefix}{name}" in keys:
            found = True
            capture_group_attrs(obj, child_path, _DERIVED_KNOWN_ATTRS, local)
        elif isinstance(obj, h5py.Group):
            below = Preserved()
            if _collect_computations(obj, child_path, f"{prefix}{name}/", keys, below):
                found = True
                capture_group_attrs(obj, child_path, (), below)
                _absorb(local, below)
                continue
            node = capture_node(group, name)
            if node is not None:
                local.nodes[child_path] = node
        else:
            node = capture_node(group, name)
            if node is not None:
                local.nodes[child_path] = node
    _absorb(preserved, local)
    return found


def collect_preserved(
    f: h5py.File, layout: Layout, computations: set[str], step_nodes: set[str], found: attachments.Attachments
) -> Preserved:
    """Everything in `f` that the layout, the loaded computations and steps, and the attachments don't claim."""
    preserved = Preserved()
    _absorb(preserved, found.preserved)
    capture_group_attrs(f, "", layout.known_root_attrs, preserved)
    root_known = _root_known(f, layout) | found.claimed
    capture_children(f, "", lambda name: name in root_known, preserved)

    if layout.multiple:
        group = f[_SOURCES_GROUP]
        capture_group_attrs(group, _SOURCES_GROUP, (), preserved)
        for name in group:
            if name in layout.source_names:
                _collect_source(group[name], f"{_SOURCES_GROUP}/{name}", layout, True, preserved)
            else:  # a group that isn't listed as a source
                node = capture_node(group, name)
                if node is not None:
                    preserved.nodes[f"{_SOURCES_GROUP}/{name}"] = node
    else:
        _collect_source(f, "", layout, False, preserved)

    if _is_group(f, _COMPUTATIONS_GROUP):
        group = f[_COMPUTATIONS_GROUP]
        capture_group_attrs(group, _COMPUTATIONS_GROUP, (), preserved)
        _collect_computations(group, _COMPUTATIONS_GROUP, "", computations, preserved)
    if _is_group(f, _STEPS_GROUP):
        group = f[_STEPS_GROUP]
        capture_group_attrs(group, _STEPS_GROUP, (), preserved)
        for node in group:
            path = f"{_STEPS_GROUP}/{node}"
            step = group.get(node) if isinstance(group.get(node, getlink=True), h5py.HardLink) else None
            if node in step_nodes and isinstance(step, h5py.Group):
                capture_group_attrs(step, path, _STEP_KNOWN_ATTRS, preserved)
                capture_children(step, path, lambda _name: False, preserved)
            else:  # a step that was malformed or didn't fit its computations, or not a step at all
                raw = capture_node(group, node)
                if raw is not None:
                    preserved.nodes[path] = raw
    return preserved


def extras_of(f: h5py.File, layout: Layout, computations: set[str], step_nodes: set[str]) -> Extras:
    """The pictures and embedded files of `f` (wherever it stores them) and everything else it has that the
    layout doesn't model."""
    found = attachments.load_attachments(f, _root_known(f, layout))
    preserved = collect_preserved(f, layout, computations, step_nodes, found)
    return Extras(pictures=found.pictures, files=found.files, preserved=preserved)


def load_bundle_with_extras(
    path: str, *, on_error: Literal["skip", "raise"] = "skip"
) -> tuple[DatasetBundle, Extras]:
    """`load_dataset_bundle`, and with it the `Extras` of the file: its pictures and embedded files and
    everything it has that this package doesn't model."""
    bundle = load_dataset_bundle(path, on_error=on_error)
    with h5py.File(path, "r") as f:
        spec = _file_format(f, path)
        layout = Layout(
            table_name=_decode(f.attrs["primary_table"]),
            multiple=_has_sources_layout(f, spec),
            source_names=tuple(str(name) for name in bundle.recording.sources),
            preprocessed_name=_decode(f.attrs["preprocessed_table"])
            if "preprocessed_table" in f.attrs
            else _PREPROCESSED_TABLE,
        )
        extras = extras_of(f, layout, set(bundle.computations), {str(step.node) for step in bundle.steps})
    return bundle, extras


def load_dataset_bundle(path: str, *, on_error: Literal["skip", "raise"] = "skip") -> DatasetBundle:
    """Read a DatasetBundle: the recording, its preprocessed tables (none if
    the file has none), every DerivedDataset found under `/computations/`
    and every ComputationStep under `/steps/` (empty if the file has none).

    A malformed computation entry or step is logged and skipped by default
    (`on_error="skip"`); pass `on_error="raise"` to fail the whole read
    instead. A malformed preprocessed table always raises.
    """
    recording = load_recording(path)
    computations: dict[str, DerivedDataset] = {}

    with h5py.File(path, "r") as f:
        preprocessed_tables = _load_preprocessed(f, path, recording)
        group = f.get(_COMPUTATIONS_GROUP)
        if group is not None:
            def _visit(name: str, obj: object) -> None:
                if not isinstance(obj, h5py.Dataset):
                    return
                try:
                    derived = _read_derived_dataset(obj, name)
                    computations[name] = derived
                except Exception:
                    if on_error == "raise":
                        raise
                    logger.warning("Skipping malformed computation %r in %r", name, path, exc_info=True)

            group.visititems(_visit)

        steps = _load_steps(f, path, computations, on_error)
        provenance = _read_provenance(f, _file_format(f, path).version)

    return DatasetBundle(
        recording=recording,
        preprocessed_tables=preprocessed_tables,
        computations=computations,
        steps=steps,
        provenance=provenance,
    )
