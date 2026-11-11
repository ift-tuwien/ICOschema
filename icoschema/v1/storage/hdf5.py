"""Adapter that reads/writes PyTables-style HDF5 files for the generated
`dataset` schema classes (see icoschema/v1/schema/generated/dataset.py).

Read dispatches on the root-level `icoschema_format_version` attribute:

- Absent: the "legacy" format that predates this versioning scheme (e.g.
  test/test_with_sensors.hdf5). The primary table is hardcoded to
  "acceleration".
- Present: parsed by the version-specific parser of that version's `FormatSpec`
  in `_FORMATS`, the registry that also says what each version can hold (the
  writer uses it too: `format_version=` picks a version, and a bundle the
  version can't hold is an error, not a silent loss).
  Version "1.0" records the primary table's name explicitly (root attribute
  `primary_table`), since it is no longer assumed to be "acceleration".
  Version "1.1" adds an optional preprocessed table, named by the root
  attribute `preprocessed_table`. Version "1.2" adds an optional `/steps/`
  group of ComputationSteps. Version "1.3" stores several sources (one per
  STU/STH combination): the root attribute `sources` lists their names in
  order and `primary_table` names the table inside each group, and
  `/sources/<name>/` holds that source's primary table and `sensors` table
  exactly as a 1.0 file holds them at the root (the name comes from the
  group, so no `source_name` attribute). It may also have `/steps/`
  and `/computations/`, and a preprocessed table per source inside that
  source's group (the root attribute `preprocessed_table` names it; sources
  without one simply don't have it). Version "1.4" is a superset of the
  others for sources that carry what a plain packet recording does not (a
  TDMS file's): the primary table may have no `counter` column, and the
  primary table may have the attributes `sampling_frequency` (Hz, per channel)
  and `additional_data` (opaque JSON) and a sibling dataset `quality` (the
  source's signal quality in percent, attribute `sampling_frequency`); a
  single source's name is always stored (`source_name`). It has `sources` or
  not like 1.3 resp. 1.0-1.2 and may have `/steps/` and `/computations/`. Any
  other version is rejected, so an older reader never silently drops parts of
  a newer file.

Every file written by this module also gets the root attribute `writer`
(`"icoschema <version>"`), and, if the bundle has a provenance, the root
attributes `source_format`, `source_format_version` and `reader`, which say
where the data was originally read from; older readers ignore them.

Every version's primary table has `counter`/`timestamp` columns plus one to
three channel columns, a `sensors` table with one row per channel column *in
the same order* (nothing else records which sensor row belongs to which
column; old files from before sensors were described have an empty or no
table, which reads as unspecified sensors, or as the sensor of a legacy
`Sensor_Range` -- see `_load_recording_from_table`),
and `Start_Time`/`adc_reference_voltage`/`conversion` attributes on the
primary table. Optional primary-table attributes: `pre_metadata`/
`post_metadata` (opaque JSON strings) and the ADC settings
`adc_prescaler`/`adc_acquisition_time`/`adc_oversample_rate`. Any other
attribute that isn't PyTables bookkeeping is logged as dropped on read.

The preprocessed table (1.1) has a `timestamp` column (`<u8`) and the
channel columns `channel1`..`channel3` (`<f4`), with
`channel_sampling_frequency`/`sampling_frequency_source`/`fill_method`/
`producer` attributes. It shares the `sensors` table and the primary table's
`conversion` flag (see dataset.yaml). With sources (1.3) each source has its
own, next to its primary table.

A `DerivedDataset` that belongs to one source has a `source` attribute (the
source's name); without one it belongs to the recording as a whole.

Steps (1.2) are stored as `/steps/<node>`: an empty group per step with
every field as an attribute (lists as string arrays, absent fields
omitted), read back ordered by `step_index` and renumbered 0, 1, 2, ...

Writing produces, unless `format_version` is given, the lowest version that can represent the data: "1.0",
"1.1" with a preprocessed table, "1.2" with steps, "1.3" with more than one
source (a single source always uses the 1.0-1.2 layout), "1.4" if a source
has no counter or has a `sampling_frequency`, `quality` or `additional_data`
-- so files without the newer parts stay readable by older readers. Every dataset with more than one element is
stored gzip-compressed (with shuffle). `DerivedDataset` arrays are stored
under a `/computations/` group in their true N-D shape -- flattening to a
plain list only exists at the schema/Python level (see dataset.yaml).
`shape`/`dtype` are never stored as separate HDF5 attributes since
`h5py.Dataset.shape`/`.dtype` already provide them intrinsically; only
`source`/`unit`/`produced_by`/`produced_at`/`params`/`description` become
dataset attributes.

This module is an internal implementation detail. Don't import it directly
-- use icoschema.v1.model.recording.Recording.from_hdf5()/.to_hdf5() and
icoschema.v1.model.dataset_bundle.DatasetBundle.from_hdf5()/.to_hdf5()
instead.
"""

from __future__ import annotations

import dataclasses
import logging
import re
from collections.abc import Callable
from pathlib import Path
from typing import Literal

import h5py
import numpy as np

from icoschema._version import software_id

from ..schema.generated.dataset import (
    ChannelMetadata,
    ComputationStep,
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

logger = logging.getLogger(__name__)

_NON_CHANNEL_COLUMNS = {"counter", "timestamp"}
_CHANNEL_SLOTS = ("channel1", "channel2", "channel3")
_CHANNEL_METADATA_SLOTS = ("channel1_metadata", "channel2_metadata", "channel3_metadata")

_LEGACY_PRIMARY_TABLE = "acceleration"
LEGACY_VERSION = "legacy"
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
_SOURCE_ATTRS = ("stu_id", "sth_id")
_SOURCE_DATA_ATTRS = ("sampling_frequency", "additional_data")  # 1.4
# Written on the primary table only when set; a file without it reads as the default source name.
_SOURCE_NAME_ATTR = "source_name"
_DEFAULT_SOURCE_NAME = "source1"
_ADC_SETTING_ATTRS = ("adc_prescaler", "adc_acquisition_time", "adc_oversample_rate")
_PREPROCESSED_ATTRS = ("channel_sampling_frequency", "sampling_frequency_source", "fill_method", "producer")
_KNOWN_PRIMARY_ATTRS = {
    "Start_Time",
    "adc_reference_voltage",
    "conversion",
    *_METADATA_ATTRS,
    *_ADC_SETTING_ATTRS,
    *_SOURCE_ATTRS,
    *_SOURCE_DATA_ATTRS,
    _SOURCE_NAME_ATTR,
}
# Attributes PyTables writes on every table it creates.
_PYTABLES_ATTR = re.compile(r"^(CLASS|TITLE|VERSION|NROWS|FIELD_\d+_(NAME|FILL))$")

# Applied to every dataset with more than one element.
_COMPRESSION = {"compression": "gzip", "compression_opts": 4, "shuffle": True}

_SENSOR_DTYPE = [
    ("dimension", "S100"),
    ("name", "S100"),
    ("offset", "<f4"),
    ("phys_max", "<f4"),
    ("phys_min", "<f4"),
    ("scaling_factor", "<f4"),
    ("sensor_id", "S100"),
    ("sensor_type", "S100"),
    ("unit", "S10"),
    ("volt_max", "<f4"),
    ("volt_min", "<f4"),
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
    """A text column of a sensors row, `None` if the table was written without that column."""
    return row[column].decode() if column in row.dtype.names else None


def _row_float(row, column: str) -> float | None:
    return float(row[column]) if column in row.dtype.names else None


def _load_sensor(row) -> Sensor:
    """Every column is optional: sensors tables written by older tools lack some (e.g. `dimension`), and a
    missing column is an unknown value (`None`), not an error."""
    return Sensor(
        sensor_id=_row_str(row, "sensor_id"),
        sensor_type=_row_str(row, "sensor_type"),
        name=_row_str(row, "name"),
        unit=_row_str(row, "unit"),
        dimension=_row_str(row, "dimension"),
        phys_min=_row_float(row, "phys_min"),
        phys_max=_row_float(row, "phys_max"),
        volt_min=_row_float(row, "volt_min"),
        volt_max=_row_float(row, "volt_max"),
    )


# e.g. "± 100.0 g₀": what the original acquisition tools wrote as `Sensor_Range`
_SENSOR_RANGE = re.compile(r"^\s*[±+-]?\s*(\d+(?:\.\d+)?)\s*(\S+)\s*$")


def _sensor_from_range(attrs: h5py.AttributeManager) -> Sensor | None:
    """The `Sensor` described by a legacy table's `Sensor_Range` attribute
    (`"± 100.0 g₀"` -> unit `g`, range -100..100), or `None` if there is none
    or it can't be read. Nothing else about the sensor was recorded."""
    if "Sensor_Range" not in attrs:
        return None
    match = _SENSOR_RANGE.match(_decode(attrs["Sensor_Range"]))
    if match is None:
        return None
    limit = float(match.group(1))
    return Sensor(unit=match.group(2).replace("₀", ""), phys_min=-limit, phys_max=limit)


def _load_channel_metadata(sensor_row, already_converted: bool, fallback_sensor: Sensor | None = None) -> ChannelMetadata:
    """`sensor_row` is `None` for a file without a sensor table: the channel
    then gets `fallback_sensor` (a copy) if there is one, else an unspecified
    `Sensor()` (every field `None`), and, as there is no scaling to read, can
    only be already converted."""
    if sensor_row is None:
        sensor = dataclasses.replace(fallback_sensor) if fallback_sensor is not None else Sensor()
        return ChannelMetadata(sensor=sensor, compensations=[NoConversion(order=0)])
    if already_converted:
        # The stored channel values are already in sensor.unit; nothing left to apply.
        compensations = [NoConversion(order=0)]
    else:
        compensations = [
            LinearConversion(
                order=0,
                gain=float(sensor_row["scaling_factor"]),
                offset=float(sensor_row["offset"]),
            )
        ]
    return ChannelMetadata(sensor=_load_sensor(sensor_row), compensations=compensations)


def _load_source_from_table(f: h5py.Group, table_name: str, name: str | None = None) -> Source:
    """Build a Source from f[table_name] and f["sensors"] (`f` is the file
    or a source group). `name` overrides the stored `source_name` attribute.

    Shared by every format version; the only thing that differs between
    versions (so far) is how `table_name` itself is determined.

    A file written before sensors were described has no sensor rows (the
    table is empty or absent): its channels get the sensor described by a
    `Sensor_Range` attribute if there is one (unit and range only), else an
    unspecified `Sensor()`, and no conversion. That is only possible when the
    table's `conversion` flag says the values are already converted, since an
    unconverted file needs each channel's `scaling_factor`/`offset` from its
    sensor row. The very first acquisition tools wrote neither sensor rows nor
    a `conversion` flag nor `adc_reference_voltage`, only physical values (in
    g) with `Start_Time` and `Sensor_Range`: a missing flag reads as converted
    when there are no sensor rows, and a missing reference voltage as `None`.
    """
    table_ds = f[table_name]
    table = table_ds[:]
    sensor_rows = f["sensors"][:] if "sensors" in f else []

    channel_columns = [name for name in table.dtype.names if name not in _NON_CHANNEL_COLUMNS]
    fallback_sensor = None
    if "conversion" in table_ds.attrs:
        already_converted = _decode(table_ds.attrs["conversion"]) == "true"
    elif len(sensor_rows) == 0:
        already_converted = True
    else:
        raise ValueError(
            f"Table {table_name!r} has sensor rows but no `conversion` attribute to say whether to apply their "
            f"scaling_factor/offset."
        )
    if channel_columns and len(sensor_rows) == 0:
        if not already_converted:
            raise ValueError(
                f"Table {table_name!r} is not converted (its `conversion` attribute is not 'true') but the file "
                f"has no sensor rows to take each channel's scaling_factor/offset from."
            )
        logger.info("Table %r has no sensor rows; its channels get an unspecified sensor", table_name)
        sensor_rows = [None] * len(channel_columns)
        fallback_sensor = _sensor_from_range(table_ds.attrs)
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

    known_attrs = _KNOWN_PRIMARY_ATTRS | ({"Sensor_Range"} if fallback_sensor is not None else set())
    dropped = sorted(name for name in table_ds.attrs if name not in known_attrs and not _PYTABLES_ATTR.match(name))
    if dropped:
        logger.warning("Primary table %r has unknown attributes that won't be preserved: %s", table_name, dropped)

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
        hardware_metadata_kwargs[metadata_slot] = _load_channel_metadata(sensor_row, already_converted, fallback_sensor)

    source = Source(
        name=name or _optional_str(table_ds.attrs, _SOURCE_NAME_ATTR) or _DEFAULT_SOURCE_NAME,
        **{name: _optional_str(table_ds.attrs, name) for name in _SOURCE_ATTRS},
        sampling_frequency=_optional_float(table_ds.attrs, "sampling_frequency"),
        additional_data=_optional_str(table_ds.attrs, "additional_data"),
        quality=quality,
        recording_metadata=RecordingMetadata(
            start_time=_decode(table_ds.attrs["Start_Time"]),
            **{name: _optional_str(table_ds.attrs, name) for name in _METADATA_ATTRS},
        ),
        hardware_metadata=HardwareMetadata(**hardware_metadata_kwargs),
        recording_data=RecordingData(**recording_data_kwargs),
    )
    return source


def _load_recording_from_table(f: h5py.Group, table_name: str) -> Recording:
    return Recording(sources=[_load_source_from_table(f, table_name)])


def _load_recording_legacy(f: h5py.File) -> Recording:
    return _load_recording_from_table(f, _LEGACY_PRIMARY_TABLE)


def _load_recording_v1(f: h5py.File) -> Recording:
    table_name = _decode(f.attrs["primary_table"])
    return _load_recording_from_table(f, table_name)


def _load_recording_v13(f: h5py.File) -> Recording:
    table_name = _decode(f.attrs["primary_table"])
    if "sources" not in f.attrs or _SOURCES_GROUP not in f:
        raise ValueError("a 1.3 file needs a `sources` attribute and a /sources/ group")
    names = [_decode(name) for name in np.atleast_1d(f.attrs["sources"])]
    if not names:
        raise ValueError("a 1.3 file must list at least one source")
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


def _load_recording_v14(f: h5py.File) -> Recording:
    return _load_recording_v13(f) if "sources" in f.attrs else _load_recording_v1(f)


FormatVersion = Literal["1.0", "1.1", "1.2", "1.3", "1.4"]
"""The versions `save_*`/`to_hdf5` can write (a test keeps this in step with `_FORMATS`)."""


@dataclasses.dataclass(frozen=True)
class FormatSpec:
    """One file format version: how to read it and what it can hold. The writer needs nothing else, so a new
    version is one more entry in `_FORMATS` (plus its reader)."""

    version: str
    read: Callable[[h5py.File], Recording]
    preprocessed: bool = False  # an optional preprocessed table (1.1)
    steps: bool = False  # an optional /steps/ group (1.2)
    # Where the sources are: "root" (one source, the primary table at the root), "sources" (always under
    # /sources/<name>/, so several are possible) or "either" (at the root for one source, else under /sources/).
    sources: Literal["root", "sources", "either"] = "root"
    source_features: bool = False  # sources without a counter, or with a rate, quality or additional data (1.4)
    writable: bool = True


_FORMATS: dict[str, FormatSpec] = {
    spec.version: spec
    for spec in (
        FormatSpec(LEGACY_VERSION, _load_recording_legacy, writable=False),
        FormatSpec("1.0", _load_recording_v1),
        FormatSpec("1.1", _load_recording_v1, preprocessed=True),
        FormatSpec("1.2", _load_recording_v1, preprocessed=True, steps=True),
        FormatSpec("1.3", _load_recording_v13, preprocessed=True, steps=True, sources="sources"),
        FormatSpec("1.4", _load_recording_v14, preprocessed=True, steps=True, sources="either", source_features=True),
    )
}  # in the order the versions appeared: the writer picks the first that fits


def readable_versions() -> tuple[str, ...]:
    """Every format version `load_*` reads (the unversioned layout is called "legacy")."""
    return tuple(_FORMATS)


def writable_versions() -> tuple[str, ...]:
    """Every format version `save_*` can write, oldest first."""
    return tuple(version for version, spec in _FORMATS.items() if spec.writable)


def _file_format(f: h5py.File, path: str) -> FormatSpec:
    """The format of the file: its `icoschema_format_version`, or the legacy one if it has none; raises
    `ValueError` for a version this reader doesn't know."""
    version = f.attrs.get("icoschema_format_version")
    if version is None:
        return _FORMATS[LEGACY_VERSION]
    version = _decode(version)
    if version == LEGACY_VERSION or version not in _FORMATS:
        raise ValueError(
            f"Unsupported icoschema_format_version {version!r} in {path!r}; "
            f"supported versions: {sorted(v for v in _FORMATS if v != LEGACY_VERSION)}"
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
    """Whether the file stores its sources under `/sources/` (1.3, or 1.4 with several)."""
    return spec.sources == "sources" or (spec.sources == "either" and "sources" in f.attrs)


def _load_preprocessed(f: h5py.File, path: str, recording: Recording) -> list[PreprocessedRecording]:
    """The preprocessed tables of a file (none for a file without any): the
    one at the root for a 1.1/1.2 file, one per source group that has one for
    a 1.3 file. Each gets its source's name."""
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

def _channel_conversion(channel_metadata: ChannelMetadata | None) -> tuple[bool, float, float]:
    """Returns (already_converted, scaling_factor, offset) for one channel's
    compensations. Only NoConversion/LinearConversion round-trip through
    this format (matching what the reader above understands)."""
    if channel_metadata is None:
        return True, 1.0, 0.0
    compensation = channel_metadata.compensations[0]
    if isinstance(compensation, LinearConversion):
        return False, compensation.gain, compensation.offset
    return True, 1.0, 0.0


def _is_unspecified(sensor: Sensor) -> bool:
    """Whether every field of `sensor` is `None` (what a file without sensor rows is read as)."""
    return all(getattr(sensor, field.name) is None for field in dataclasses.fields(sensor))


def _sensor_row(channel_metadata: ChannelMetadata, *, scaling_factor: float, offset: float) -> np.ndarray:
    sensor = channel_metadata.sensor
    row = np.zeros(1, dtype=_SENSOR_DTYPE)
    row["dimension"] = (sensor.dimension or "").encode()
    row["name"] = (sensor.name or "").encode()
    row["offset"] = offset
    row["phys_max"] = sensor.phys_max if sensor.phys_max is not None else 0.0
    row["phys_min"] = sensor.phys_min if sensor.phys_min is not None else 0.0
    row["scaling_factor"] = scaling_factor
    row["sensor_id"] = (sensor.sensor_id or "").encode()
    row["sensor_type"] = (sensor.sensor_type or "").encode()
    row["unit"] = (sensor.unit or "").encode()
    row["volt_max"] = sensor.volt_max if sensor.volt_max is not None else 0.0
    row["volt_min"] = sensor.volt_min if sensor.volt_min is not None else 0.0
    return row


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

    conversion_flags = set()
    sensor_rows = []
    for channel_slot, metadata_slot in present_channels:
        channel_metadata = getattr(hardware, metadata_slot)
        already_converted, scaling_factor, offset = _channel_conversion(channel_metadata)
        conversion_flags.add(already_converted)
        sensor_rows.append(_sensor_row(channel_metadata, scaling_factor=scaling_factor, offset=offset))
    if len(conversion_flags) > 1:
        raise ValueError(
            "Cannot write a Recording whose channels have different "
            "already-converted states -- the v1 HDF5 format has a single "
            "table-level `conversion` flag shared by every channel."
        )
    if conversion_flags <= {True} and all(
        _is_unspecified(getattr(hardware, metadata_slot).sensor) for _, metadata_slot in present_channels
    ):
        # Nothing to record about the sensors (a file read without sensor rows): write no table instead
        # of rows of empty strings and zeros, so the file reads back the same way.
        sensor_rows = []

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
    ds.attrs["Start_Time"] = source.recording_metadata.start_time or ""
    ds.attrs["adc_reference_voltage"] = hardware.adc_reference_voltage or ""
    ds.attrs["conversion"] = "true" if (not conversion_flags or conversion_flags == {True}) else "false"
    for name in _METADATA_ATTRS:
        value = getattr(source.recording_metadata, name)
        if value is not None:
            ds.attrs[name] = value
    for name in _SOURCE_ATTRS:
        value = getattr(source, name)
        if value is not None:
            ds.attrs[name] = value
    if store_name and (always_name or str(source.name) != _DEFAULT_SOURCE_NAME):
        ds.attrs[_SOURCE_NAME_ATTR] = str(source.name)
    if source.sampling_frequency is not None:
        ds.attrs["sampling_frequency"] = float(source.sampling_frequency)
    if source.additional_data is not None:
        ds.attrs["additional_data"] = source.additional_data
    if source.quality is not None and source.quality.values:
        quality_ds = _create_dataset(f, _QUALITY_DATASET, np.asarray(source.quality.values, dtype="<f4"))
        if source.quality.sampling_frequency is not None:
            quality_ds.attrs["sampling_frequency"] = float(source.quality.sampling_frequency)
    for name in _ADC_SETTING_ATTRS:
        value = getattr(hardware, name)
        if value is not None:
            ds.attrs[name] = int(value)

    if sensor_rows:
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
    """The steps of a 1.2 file, ordered by `step_index` and renumbered 0, 1,
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
    """What a source has that only formats with `source_features` (1.4) can store."""
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
    (1.3). With `source_features` (1.4) a single source's name is always stored."""
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
    `/steps/`. Writes `format_version`, or by default the lowest sufficient
    format: 1.4 if a source needs it (see the module docstring), 1.3 with
    several sources (preprocessed tables go into their source's group), else
    1.2 with steps, else 1.1 with a preprocessed table, else 1.0. Raises
    `ValueError` (before anything is written) if `format_version` is unknown
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
