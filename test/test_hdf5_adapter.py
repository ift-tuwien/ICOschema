"""Verbose end-to-end test of the (internal) HDF5 storage adapter against the
real fixture in test/test_with_sensors.hdf5, checking every level of the
schema it touches: RecordingMetadata, HardwareMetadata, Sensor,
Compensation and RecordingData -- plus the write path (save_recording,
save_dataset_bundle/load_dataset_bundle) added for DerivedDataset/
DatasetBundle support.

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

from ICOschema.schema.generated.python.dataset import DatasetBundle, DerivedDataset, LinearConversion, NoConversion
from ICOschema.storage.python.hdf5 import load_dataset_bundle, load_recording, save_dataset_bundle, save_recording

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"


def test_load_recording_from_hdf5():
    assert FIXTURE.exists(), f"fixture not found at {FIXTURE}"

    recording = load_recording(str(FIXTURE))

    # --- RecordingMetadata: read from the acceleration table's Start_Time attr ---
    assert recording.recording_metadata.start_time == "2026-07-07T11:01:15.141594"

    # --- HardwareMetadata: adc_reference_voltage attr, only channel1 is populated ---
    assert recording.hardware_metadata.adc_reference_voltage == "3.3"
    assert recording.hardware_metadata.channel2_metadata is None
    assert recording.hardware_metadata.channel3_metadata is None

    channel1_metadata = recording.hardware_metadata.channel1_metadata
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

    # --- RecordingData: columnar arrays aligned by index, one row per sample ---
    data = recording.recording_data
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


def test_load_recording_rejects_channel_sensor_count_mismatch(tmp_path):
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
        load_recording(str(bad_file))


def test_load_recording_v1_uses_declared_primary_table_name(tmp_path):
    # A "current" (v1) file: no assumption that the primary table is called
    # "acceleration", and the raw values are NOT pre-converted, exercising
    # the LinearConversion branch that the legacy fixture never hits.
    v1_file = tmp_path / "v1.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 512.0), (1, 100, 600.0)], already_converted=False)

    recording = load_recording(str(v1_file))

    assert recording.recording_metadata.start_time == "2026-02-02T00:00:00"
    assert recording.hardware_metadata.adc_reference_voltage == "5.0"
    assert recording.recording_data.channel1 == pytest.approx([512.0, 600.0])

    sensor = recording.hardware_metadata.channel1_metadata.sensor
    assert sensor.sensor_id == "volt_01"
    assert sensor.unit == "V"

    compensations = recording.hardware_metadata.channel1_metadata.compensations
    assert len(compensations) == 1
    assert isinstance(compensations[0], LinearConversion)
    assert compensations[0].gain == pytest.approx(2.0)
    assert compensations[0].offset == pytest.approx(-10.0)


def test_load_recording_rejects_unknown_format_version(tmp_path):
    bad_file = tmp_path / "unknown_version.hdf5"
    with h5py.File(bad_file, "w") as f:
        f.attrs["icoschema_format_version"] = "99.0"

    with pytest.raises(ValueError, match="Unsupported icoschema_format_version"):
        load_recording(str(bad_file))


# ── write: save_recording / round trip ──────────────────────────────────────

def test_save_recording_round_trips_through_load_recording(tmp_path):
    original = load_recording(str(FIXTURE))
    out_file = tmp_path / "roundtrip.hdf5"

    save_recording(original, str(out_file))
    reloaded = load_recording(str(out_file))

    assert reloaded.recording_metadata.start_time == original.recording_metadata.start_time
    assert reloaded.hardware_metadata.adc_reference_voltage == original.hardware_metadata.adc_reference_voltage
    assert reloaded.recording_data.counter == original.recording_data.counter
    assert reloaded.recording_data.timestamp == original.recording_data.timestamp
    assert reloaded.recording_data.channel1 == pytest.approx(original.recording_data.channel1)

    sensor = reloaded.hardware_metadata.channel1_metadata.sensor
    original_sensor = original.hardware_metadata.channel1_metadata.sensor
    assert sensor.sensor_id == original_sensor.sensor_id
    assert sensor.unit == original_sensor.unit
    assert isinstance(reloaded.hardware_metadata.channel1_metadata.compensations[0], NoConversion)


def test_save_recording_round_trips_a_linear_conversion_channel(tmp_path):
    v1_file = tmp_path / "v1.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 512.0), (1, 100, 600.0)], already_converted=False)
    original = load_recording(str(v1_file))

    out_file = tmp_path / "roundtrip_linear.hdf5"
    save_recording(original, str(out_file))
    reloaded = load_recording(str(out_file))

    compensation = reloaded.hardware_metadata.channel1_metadata.compensations[0]
    assert isinstance(compensation, LinearConversion)
    assert compensation.gain == pytest.approx(2.0)
    assert compensation.offset == pytest.approx(-10.0)
    assert reloaded.recording_data.channel1 == pytest.approx([512.0, 600.0])


# ── write/read: DatasetBundle / DerivedDataset ──────────────────────────────

def _derived(key: str, array: np.ndarray, **extra) -> DerivedDataset:
    return DerivedDataset(
        key=key,
        values=array.ravel().tolist(),
        shape=list(array.shape),
        dtype=str(array.dtype),
        **extra,
    )


def test_save_and_load_dataset_bundle_round_trips_computations(tmp_path):
    recording = load_recording(str(FIXTURE))
    details = np.array([[1.0, 2.0], [3.0, 4.0]])
    bundle = DatasetBundle(
        recording=recording,
        computations={
            "wavelet_coefficients/channel1/details": _derived(
                "wavelet_coefficients/channel1/details",
                details,
                unit="g",
                produced_by="wavelet_transform@1.0.0",
                params='{"wavelet": "db4", "level": 3}',
            ),
        },
    )

    out_file = tmp_path / "bundle.hdf5"
    save_dataset_bundle(bundle, str(out_file))
    reloaded = load_dataset_bundle(str(out_file))

    assert set(reloaded.computations.keys()) == {"wavelet_coefficients/channel1/details"}
    entry = reloaded.computations["wavelet_coefficients/channel1/details"]
    assert entry.shape == [2, 2]
    assert np.array(entry.values).reshape(entry.shape) == pytest.approx(details)
    assert entry.unit == "g"
    assert entry.produced_by == "wavelet_transform@1.0.0"
    assert entry.params == '{"wavelet": "db4", "level": 3}'


def test_load_dataset_bundle_has_empty_computations_when_file_has_none(tmp_path):
    recording = load_recording(str(FIXTURE))
    out_file = tmp_path / "no_computations.hdf5"
    save_recording(recording, str(out_file))

    bundle = load_dataset_bundle(str(out_file))

    assert bundle.computations == {}


def test_load_dataset_bundle_preserves_native_hdf5_shape_not_flattened(tmp_path):
    recording = load_recording(str(FIXTURE))
    array = np.arange(24.0).reshape(2, 3, 4)
    bundle = DatasetBundle(recording=recording, computations={"a/b": _derived("a/b", array)})

    out_file = tmp_path / "shaped.hdf5"
    save_dataset_bundle(bundle, str(out_file))

    with h5py.File(out_file, "r") as f:
        ds = f["computations/a/b"]
        assert ds.shape == (2, 3, 4)  # stored natively, not flattened


def test_load_dataset_bundle_skips_malformed_computation_by_default(tmp_path):
    recording = load_recording(str(FIXTURE))
    out_file = tmp_path / "malformed.hdf5"
    save_recording(recording, str(out_file))

    with h5py.File(out_file, "a") as f:
        group = f.create_group("computations")
        group.create_dataset("good", data=np.array([1.0, 2.0]))
        # A non-numeric dataset: DerivedDataset.values coerces every element
        # via float(v), which raises for a string -- simulates a corrupt entry.
        group.create_dataset("bad", data=np.array(["not", "numeric"], dtype=h5py.string_dtype()))

    bundle = load_dataset_bundle(str(out_file))

    assert set(bundle.computations.keys()) == {"good"}


def test_load_dataset_bundle_raises_on_malformed_computation_when_requested(tmp_path):
    recording = load_recording(str(FIXTURE))
    out_file = tmp_path / "malformed_strict.hdf5"
    save_recording(recording, str(out_file))

    with h5py.File(out_file, "a") as f:
        group = f.create_group("computations")
        group.create_dataset("bad", data=np.array(["not", "numeric"], dtype=h5py.string_dtype()))

    with pytest.raises(ValueError):
        load_dataset_bundle(str(out_file), on_error="raise")
