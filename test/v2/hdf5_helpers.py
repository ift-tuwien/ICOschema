"""Shared helpers for building synthetic PyTables-style HDF5 files (format 2.0) in tests."""

import h5py
import numpy as np

SENSOR_DTYPE = [
    ("dimension", "S100"),
    ("name", "S100"),
    ("sensor_id", "S100"),
    ("sensor_type", "S100"),
    ("unit", "S10"),
    ("conversion", "S10"),
    ("gain", "<f8"),
    ("offset", "<f8"),
]


def make_sensor_row(
    *,
    dimension=b"Voltage",
    name=b"Test Voltage Sensor",
    sensor_id=b"volt_01",
    sensor_type=b"TESTSENSOR",
    unit=b"V",
    conversion=b"linear",
    gain=2.0,
    offset=-10.0,
):
    row = np.zeros(1, dtype=SENSOR_DTYPE)
    row["dimension"] = dimension
    row["name"] = name
    row["sensor_id"] = sensor_id
    row["sensor_type"] = sensor_type
    row["unit"] = unit
    row["conversion"] = conversion
    row["gain"] = gain
    row["offset"] = offset
    return row


def write_file(
    path,
    *,
    table_name="vibration",
    rows,
    conversion="linear",
    start_time="2026-02-02T00:00:00",
    adc_reference_voltage="5.0",
    sensor_row=None,
):
    """Write a format 2.0 HDF5 file with one source of a single channel.

    `rows` is a list of (counter, timestamp, value) tuples. `conversion` ("linear" with gain 2 and offset -10, or
    "none") is the channel's conversion, unless `sensor_row` is given.
    """
    if sensor_row is None:
        sensor_row = make_sensor_row(conversion=conversion.encode())

    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "2.0"
        f.attrs["primary_table"] = table_name

        table = np.array(rows, dtype=[("counter", "u1"), ("timestamp", "<u8"), ("v", "<f4")])
        ds = f.create_dataset(table_name, data=table)
        ds.attrs["Start_Time"] = start_time
        ds.attrs["adc_reference_voltage"] = adc_reference_voltage

        f.create_dataset("sensors", data=sensor_row)
