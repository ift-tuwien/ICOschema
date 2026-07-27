"""Adapter that reads/writes PyTables-style HDF5 files for the generated
`dataset` schema classes (see ICOschema/schema/generated/python/dataset.py).

Read dispatches on the root-level `icoschema_format_version` attribute:

- Absent: the "legacy" format that predates this versioning scheme (e.g.
  test/test_with_sensors.hdf5). The primary table is hardcoded to
  "acceleration".
- Present: parsed by the version-specific parser registered in _PARSERS.
  Version "1.0" records the primary table's name explicitly (root attribute
  `primary_table`), since it is no longer assumed to be "acceleration".

Every version's primary table has `counter`/`timestamp` columns plus one to
three channel columns, a `sensors` table with one row per channel column *in
the same order* (nothing else records which sensor row belongs to which
column), and `Start_Time`/`adc_reference_voltage`/`conversion` attributes on
the primary table.

Writing always produces the current (v1) format. `DerivedDataset` arrays are
stored under a `/computations/` group in their true N-D shape -- flattening
to a plain list only exists at the schema/Python level (see dataset.yaml).
`shape`/`dtype` are never stored as separate HDF5 attributes since
`h5py.Dataset.shape`/`.dtype` already provide them intrinsically; only
`unit`/`produced_by`/`produced_at`/`params`/`description` become dataset
attributes.

This module is an internal implementation detail. Don't import it directly
-- use ICOschema.model.python.recording.Recording.from_hdf5()/.to_hdf5() and
ICOschema.model.python.dataset_bundle.DatasetBundle.from_hdf5()/.to_hdf5()
instead.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import h5py
import numpy as np

from ICOschema.schema.generated.python.dataset import (
    ChannelMetadata,
    DatasetBundle,
    DerivedDataset,
    HardwareMetadata,
    LinearConversion,
    NoConversion,
    Recording,
    RecordingData,
    RecordingMetadata,
    Sensor,
)

logger = logging.getLogger(__name__)

_NON_CHANNEL_COLUMNS = {"counter", "timestamp"}
_CHANNEL_SLOTS = ("channel1", "channel2", "channel3")
_CHANNEL_METADATA_SLOTS = ("channel1_metadata", "channel2_metadata", "channel3_metadata")

_LEGACY_PRIMARY_TABLE = "acceleration"
_CURRENT_FORMAT_VERSION = "1.0"
_COMPUTATIONS_GROUP = "computations"

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


# ── read: Recording ──────────────────────────────────────────────────────────

def _load_sensor(row) -> Sensor:
    return Sensor(
        sensor_id=row["sensor_id"].decode(),
        sensor_type=row["sensor_type"].decode(),
        name=row["name"].decode(),
        unit=row["unit"].decode(),
        dimension=row["dimension"].decode(),
        phys_min=float(row["phys_min"]),
        phys_max=float(row["phys_max"]),
        volt_min=float(row["volt_min"]),
        volt_max=float(row["volt_max"]),
    )


def _load_channel_metadata(sensor_row, already_converted: bool) -> ChannelMetadata:
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


def _load_recording_from_table(f: h5py.File, table_name: str) -> Recording:
    """Build a Recording from f[table_name] and f["sensors"].

    Shared by every format version; the only thing that differs between
    versions (so far) is how `table_name` itself is determined.
    """
    table_ds = f[table_name]
    table = table_ds[:]
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

    already_converted = _decode(table_ds.attrs["conversion"]) == "true"

    recording_data_kwargs = {
        "timestamp": table["timestamp"].tolist(),
        "counter": table["counter"].tolist(),
    }
    hardware_metadata_kwargs = {
        "adc_reference_voltage": _decode(table_ds.attrs["adc_reference_voltage"]),
    }
    for channel_slot, metadata_slot, column, sensor_row in zip(
        _CHANNEL_SLOTS, _CHANNEL_METADATA_SLOTS, channel_columns, sensor_rows
    ):
        recording_data_kwargs[channel_slot] = table[column].tolist()
        hardware_metadata_kwargs[metadata_slot] = _load_channel_metadata(sensor_row, already_converted)

    return Recording(
        recording_metadata=RecordingMetadata(
            start_time=_decode(table_ds.attrs["Start_Time"]),
        ),
        hardware_metadata=HardwareMetadata(**hardware_metadata_kwargs),
        recording_data=RecordingData(**recording_data_kwargs),
    )


def _load_recording_legacy(f: h5py.File) -> Recording:
    return _load_recording_from_table(f, _LEGACY_PRIMARY_TABLE)


def _load_recording_v1(f: h5py.File) -> Recording:
    table_name = _decode(f.attrs["primary_table"])
    return _load_recording_from_table(f, table_name)


_PARSERS = {
    "1.0": _load_recording_v1,
}


def load_recording(path: str) -> Recording:
    with h5py.File(path, "r") as f:
        version = f.attrs.get("icoschema_format_version")
        if version is None:
            return _load_recording_legacy(f)

        version = _decode(version)
        try:
            parser = _PARSERS[version]
        except KeyError:
            raise ValueError(
                f"Unsupported icoschema_format_version {version!r} in {path!r}; "
                f"supported versions: {sorted(_PARSERS)}"
            ) from None
        return parser(f)


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


def _write_recording_table(f: h5py.File, recording: Recording, table_name: str) -> None:
    data = recording.recording_data
    hardware = recording.hardware_metadata

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

    dtype = [("counter", "u1"), ("timestamp", "<u8")] + [(slot, "<f4") for slot, _ in present_channels]
    table = np.zeros(len(data.timestamp), dtype=dtype)
    table["counter"] = data.counter
    table["timestamp"] = data.timestamp
    for channel_slot, _metadata_slot in present_channels:
        table[channel_slot] = getattr(data, channel_slot)

    ds = f.create_dataset(table_name, data=table)
    ds.attrs["Start_Time"] = recording.recording_metadata.start_time or ""
    ds.attrs["adc_reference_voltage"] = hardware.adc_reference_voltage or ""
    ds.attrs["conversion"] = "true" if (not conversion_flags or conversion_flags == {True}) else "false"

    if sensor_rows:
        f.create_dataset("sensors", data=np.concatenate(sensor_rows))


def save_recording(recording: Recording, path: str, *, table_name: str = "recording") -> None:
    """Write a Recording to a fresh HDF5 file in the current (v1) format."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = _CURRENT_FORMAT_VERSION
        f.attrs["primary_table"] = table_name
        _write_recording_table(f, recording, table_name)


# ── read/write: DerivedDataset / DatasetBundle ──────────────────────────────

def _write_derived_dataset(computations_group: h5py.Group, key: str, derived: DerivedDataset) -> None:
    array = np.asarray(derived.values, dtype=derived.dtype).reshape(derived.shape)
    ds = computations_group.create_dataset(key, data=array)
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


def save_dataset_bundle(bundle: DatasetBundle, path: str, *, table_name: str = "recording") -> None:
    """Write a DatasetBundle: the recording as the primary table, every
    DerivedDataset under a `/computations/` group, each in its true N-D
    shape."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = _CURRENT_FORMAT_VERSION
        f.attrs["primary_table"] = table_name
        _write_recording_table(f, bundle.recording, table_name)

        if bundle.computations:
            computations_group = f.create_group(_COMPUTATIONS_GROUP)
            for key, derived in bundle.computations.items():
                _write_derived_dataset(computations_group, key, derived)


def load_dataset_bundle(path: str, *, on_error: Literal["skip", "raise"] = "skip") -> DatasetBundle:
    """Read a DatasetBundle: the recording, plus every DerivedDataset found
    under `/computations/` (empty if the file has none).

    A malformed computation entry is logged and skipped by default
    (`on_error="skip"`); pass `on_error="raise"` to fail the whole read
    instead.
    """
    recording = load_recording(path)
    computations: dict[str, DerivedDataset] = {}

    with h5py.File(path, "r") as f:
        group = f.get(_COMPUTATIONS_GROUP)
        if group is not None:
            def _visit(name: str, obj: object) -> None:
                if not isinstance(obj, h5py.Dataset):
                    return
                try:
                    computations[name] = _read_derived_dataset(obj, name)
                except Exception:
                    if on_error == "raise":
                        raise
                    logger.warning("Skipping malformed computation %r in %r", name, path, exc_info=True)

            group.visititems(_visit)

    return DatasetBundle(recording=recording, computations=computations)
