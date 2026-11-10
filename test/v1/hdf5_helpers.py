"""Shared helpers for building synthetic PyTables-style HDF5 files in tests."""

import h5py
import numpy as np

SENSOR_DTYPE = [
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


def make_sensor_row(
    *,
    dimension=b"Voltage",
    name=b"Test Voltage Sensor",
    offset=-10.0,
    phys_max=10.0,
    phys_min=-10.0,
    scaling_factor=2.0,
    sensor_id=b"volt_01",
    sensor_type=b"TESTSENSOR",
    unit=b"V",
    volt_max=3.3,
    volt_min=0.0,
):
    row = np.zeros(1, dtype=SENSOR_DTYPE)
    row["dimension"] = dimension
    row["name"] = name
    row["offset"] = offset
    row["phys_max"] = phys_max
    row["phys_min"] = phys_min
    row["scaling_factor"] = scaling_factor
    row["sensor_id"] = sensor_id
    row["sensor_type"] = sensor_type
    row["unit"] = unit
    row["volt_max"] = volt_max
    row["volt_min"] = volt_min
    return row


def write_v1_file(
    path,
    *,
    table_name="vibration",
    rows,
    already_converted: bool,
    start_time="2026-02-02T00:00:00",
    adc_reference_voltage="5.0",
    sensor_row=None,
):
    """Write a "current" (icoschema_format_version 1.0) HDF5 file.

    `rows` is a list of (counter, timestamp, value) tuples for a single channel.
    """
    if sensor_row is None:
        sensor_row = make_sensor_row()

    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "1.0"
        f.attrs["primary_table"] = table_name

        table = np.array(rows, dtype=[("counter", "u1"), ("timestamp", "<u8"), ("v", "<f4")])
        ds = f.create_dataset(table_name, data=table)
        ds.attrs["Start_Time"] = start_time
        ds.attrs["adc_reference_voltage"] = adc_reference_voltage
        ds.attrs["conversion"] = "true" if already_converted else "false"

        f.create_dataset("sensors", data=sensor_row)
