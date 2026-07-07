"""Adapter that reads a PyTables-style HDF5 measurement file into the
generated `measurement` schema classes (see ICOschema/schema/generated/python).

Dispatches on the root-level `icoschema_format_version` attribute:

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

This module is an internal implementation detail. Don't import it directly
-- use ICOschema.model.python.measurement.Measurement.from_hdf5() instead.
"""

from __future__ import annotations

import h5py

from ICOschema.schema.generated.python.measurement import (
    ChannelMetadata,
    HardwareMetadata,
    LinearConversion,
    Measurement,
    MeasurementData,
    MeasurementMetadata,
    NoConversion,
    Sensor,
)

_NON_CHANNEL_COLUMNS = {"counter", "timestamp"}
_CHANNEL_SLOTS = ("channel1", "channel2", "channel3")
_CHANNEL_METADATA_SLOTS = ("channel1_metadata", "channel2_metadata", "channel3_metadata")

_LEGACY_PRIMARY_TABLE = "acceleration"


def _decode(value) -> str:
    return value.decode() if isinstance(value, bytes) else str(value)


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


def _load_measurement_from_table(f: h5py.File, table_name: str) -> Measurement:
    """Build a Measurement from f[table_name] and f["sensors"].

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
            f"Measurement supports at most {len(_CHANNEL_SLOTS)} channels, "
            f"got {len(channel_columns)}."
        )

    already_converted = _decode(table_ds.attrs["conversion"]) == "true"

    measurement_data_kwargs = {
        "timestamp": table["timestamp"].tolist(),
        "counter": table["counter"].tolist(),
    }
    hardware_metadata_kwargs = {
        "adc_reference_voltage": _decode(table_ds.attrs["adc_reference_voltage"]),
    }
    for channel_slot, metadata_slot, column, sensor_row in zip(
        _CHANNEL_SLOTS, _CHANNEL_METADATA_SLOTS, channel_columns, sensor_rows
    ):
        measurement_data_kwargs[channel_slot] = table[column].tolist()
        hardware_metadata_kwargs[metadata_slot] = _load_channel_metadata(sensor_row, already_converted)

    return Measurement(
        measurement_metadata=MeasurementMetadata(
            start_time=_decode(table_ds.attrs["Start_Time"]),
        ),
        hardware_metadata=HardwareMetadata(**hardware_metadata_kwargs),
        measurement_data=MeasurementData(**measurement_data_kwargs),
    )


def _load_measurement_legacy(f: h5py.File) -> Measurement:
    return _load_measurement_from_table(f, _LEGACY_PRIMARY_TABLE)


def _load_measurement_v1(f: h5py.File) -> Measurement:
    table_name = _decode(f.attrs["primary_table"])
    return _load_measurement_from_table(f, table_name)


_PARSERS = {
    "1.0": _load_measurement_v1,
}


def load_measurement(path: str) -> Measurement:
    with h5py.File(path, "r") as f:
        version = f.attrs.get("icoschema_format_version")
        if version is None:
            return _load_measurement_legacy(f)

        version = _decode(version)
        try:
            parser = _PARSERS[version]
        except KeyError:
            raise ValueError(
                f"Unsupported icoschema_format_version {version!r} in {path!r}; "
                f"supported versions: {sorted(_PARSERS)}"
            ) from None
        return parser(f)
