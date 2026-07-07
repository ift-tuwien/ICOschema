"""Verbose end-to-end test of the (internal) HDF5 storage adapter against the
real fixture in test/test_with_sensors.hdf5, checking every level of the
schema it touches: MeasurementMetadata, HardwareMetadata, Sensor,
Compensation and MeasurementData.

This tests ICOschema.storage directly, which is an internal implementation
detail -- other codebases should go through ICOschema.model instead (see
test_model.py). Testing storage directly here still earns its keep: it lets
us assert on the exact plain-generated-class shape storage produces, without
the model layer's upgrade step in the way.
"""

from pathlib import Path

import h5py
import numpy as np
import pytest
from hdf5_helpers import write_v1_file

from ICOschema.schema.generated.python.measurement import LinearConversion, NoConversion
from ICOschema.storage.python.hdf5 import load_measurement

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"


def test_load_measurement_from_hdf5():
    assert FIXTURE.exists(), f"fixture not found at {FIXTURE}"

    measurement = load_measurement(str(FIXTURE))

    # --- MeasurementMetadata: read from the acceleration table's Start_Time attr ---
    assert measurement.measurement_metadata.start_time == "2026-07-07T11:01:15.141594"

    # --- HardwareMetadata: adc_reference_voltage attr, only channel1 is populated ---
    assert measurement.hardware_metadata.adc_reference_voltage == "3.3"
    assert measurement.hardware_metadata.channel2_metadata is None
    assert measurement.hardware_metadata.channel3_metadata is None

    channel1_metadata = measurement.hardware_metadata.channel1_metadata
    assert channel1_metadata is not None

    # --- Sensor: the single row in the sensors table ---
    sensor = channel1_metadata.sensor
    assert sensor.sensor_id == "acc100g_01"
    assert sensor.sensor_type == "ADXL1001"
    assert sensor.name == "Acceleration 100g"
    assert sensor.unit == "g"
    assert sensor.dimension == "Acceleration"
    assert sensor.phys_min == pytest.approx(-100.0)
    assert sensor.phys_max == pytest.approx(100.0)
    assert sensor.volt_min == pytest.approx(0.33)
    assert sensor.volt_max == pytest.approx(2.97)

    # --- Compensation: the file's `conversion` attr is "true", meaning the
    # stored channel values are already physical, so no conversion should be
    # applied on read -- the adapter must pick NoConversion, not LinearConversion.
    compensations = channel1_metadata.compensations
    assert len(compensations) == 1
    assert isinstance(compensations[0], NoConversion)
    assert compensations[0].order == 0

    # --- MeasurementData: columnar arrays aligned by index, one row per sample ---
    data = measurement.measurement_data
    assert len(data.timestamp) == 48027
    assert len(data.counter) == 48027
    assert len(data.channel1) == 48027
    assert data.channel2 == []
    assert data.channel3 == []

    # First 5 rows, read directly off the fixture with h5py for this test.
    assert data.counter[:5] == [0, 0, 0, 1, 1]
    assert data.timestamp[:5] == [0, 0, 0, 1237, 1237]
    assert data.channel1[:3] == pytest.approx([87.85954284667969, 87.86335754394531, 87.87098693847656])

    # Last row.
    assert data.counter[-1] == 136
    assert data.timestamp[-1] == 5118172
    assert data.channel1[-1] == pytest.approx(87.91676330566406)

    # counter is stored as an 8-bit field on the wire, so packet-loss
    # detection relies on wraparound at 255 -- assert that this fixture
    # actually exercises that, otherwise the wraparound handling in any
    # downstream counter code would go untested.
    assert min(data.counter) == 0
    assert max(data.counter) == 255


def test_load_measurement_rejects_channel_sensor_count_mismatch(tmp_path):
    bad_file = tmp_path / "mismatched.hdf5"
    with h5py.File(bad_file, "w") as f:
        table = np.zeros(1, dtype=[("counter", "u1"), ("timestamp", "<u8"), ("x", "<f4"), ("y", "<f4")])
        ds = f.create_dataset("acceleration", data=table)
        ds.attrs["Start_Time"] = "2026-01-01T00:00:00"
        ds.attrs["adc_reference_voltage"] = "3.3"
        ds.attrs["conversion"] = "true"
        # Two channel columns (x, y) but only one sensor row: should be rejected.
        sensors = np.zeros(1, dtype=[("sensor_id", "S10")])
        f.create_dataset("sensors", data=sensors)

    with pytest.raises(ValueError, match="sensor row per channel column"):
        load_measurement(str(bad_file))


def test_load_measurement_v1_uses_declared_primary_table_name(tmp_path):
    # A "current" (v1) file: no assumption that the primary table is called
    # "acceleration", and the raw values are NOT pre-converted, exercising
    # the LinearConversion branch that the legacy fixture never hits.
    v1_file = tmp_path / "v1.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 512.0), (1, 100, 600.0)], already_converted=False)

    measurement = load_measurement(str(v1_file))

    assert measurement.measurement_metadata.start_time == "2026-02-02T00:00:00"
    assert measurement.hardware_metadata.adc_reference_voltage == "5.0"
    assert measurement.measurement_data.channel1 == pytest.approx([512.0, 600.0])

    sensor = measurement.hardware_metadata.channel1_metadata.sensor
    assert sensor.sensor_id == "volt_01"
    assert sensor.unit == "V"

    compensations = measurement.hardware_metadata.channel1_metadata.compensations
    assert len(compensations) == 1
    assert isinstance(compensations[0], LinearConversion)
    assert compensations[0].gain == pytest.approx(2.0)
    assert compensations[0].offset == pytest.approx(-10.0)


def test_load_measurement_rejects_unknown_format_version(tmp_path):
    bad_file = tmp_path / "unknown_version.hdf5"
    with h5py.File(bad_file, "w") as f:
        f.attrs["icoschema_format_version"] = "99.0"

    with pytest.raises(ValueError, match="Unsupported icoschema_format_version"):
        load_measurement(str(bad_file))
