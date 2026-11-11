"""End-to-end test of the (internal) HDF5 storage adapter of schema version 2 against the converted real
fixture in test/v2/test_with_sensors.hdf5 (see make_fixture.py), checking every level of the schema it
touches: RecordingMetadata, HardwareMetadata, Sensor, Conversion and RecordingData -- plus the write path
(save_recording, save_dataset_bundle/load_dataset_bundle) for DerivedDataset/DatasetBundle support.

This tests icoschema.v2.storage directly, which is an internal implementation detail -- other codebases should
go through icoschema.v2 instead (see test_model.py). Testing storage directly here still earns its keep: it lets
us assert on the exact plain-generated-class shape storage produces, without the model layer's upgrade step in
the way.
"""

import logging
from pathlib import Path

import h5py
import numpy as np
import pytest

from icoschema.v2.schema.generated.dataset import (
    ChannelMetadata,
    Conversion,
    DatasetBundle,
    DerivedDataset,
    HardwareMetadata,
    LinearConversion,
    NoConversion,
    RecordingData,
    RecordingMetadata,
    Sensor,
    Source,
)
from icoschema.v2.schema.generated.dataset import Recording as GeneratedRecording
from icoschema.v2.storage.hdf5 import (
    load_dataset_bundle,
    load_recording,
    save_dataset_bundle,
    save_recording,
)

from .hdf5_helpers import SENSOR_DTYPE, make_sensor_row, write_file

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"


def test_load_recording_from_hdf5():
    assert FIXTURE.exists(), f"fixture not found at {FIXTURE}"

    recording = load_recording(str(FIXTURE))

    # --- RecordingMetadata: read from the acceleration table's Start_Time attr ---
    assert recording.sources["source1"].recording_metadata.start_time == "2026-07-07T11:01:15.141594"

    # --- HardwareMetadata: adc_reference_voltage attr, only channel1 is populated ---
    assert recording.sources["source1"].hardware_metadata.adc_reference_voltage == "3.3"
    assert recording.sources["source1"].hardware_metadata.channel2_metadata is None
    assert recording.sources["source1"].hardware_metadata.channel3_metadata is None

    channel1_metadata = recording.sources["source1"].hardware_metadata.channel1_metadata
    assert channel1_metadata is not None

    # --- Sensor: the single row in the sensors table ---
    sensor = channel1_metadata.sensor
    assert sensor.sensor_id == "acc100g_01"
    assert sensor.sensor_type == "ADXL1001"
    assert sensor.name == "Acceleration 100g"
    assert sensor.unit == "g"
    assert sensor.dimension == "Acceleration"

    # --- Conversion: this file's values are in the sensor's unit already, which is an identity conversion
    # (NoConversion would mean raw voltage values).
    assert channel1_metadata.conversion == LinearConversion(gain=1.0, offset=0.0)

    # --- Source: the MAC addresses, and a description that was never set
    source = recording.sources["source1"]
    assert (source.stu_mac, source.sth_mac, source.description) == ("08-6B-D7-0F-47-2C", "14-2D-41-D7-77-7D", None)

    # --- RecordingData: columnar arrays aligned by index, one row per sample ---
    data = recording.sources["source1"].recording_data
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
    path = tmp_path / "mismatched.hdf5"
    write_file(path, rows=[(0, 0, 1.0)])
    with h5py.File(path, "r+") as f:
        table = np.zeros(1, dtype=[("counter", "u1"), ("timestamp", "<u8"), ("x", "<f4"), ("y", "<f4")])
        del f["vibration"]
        ds = f.create_dataset("vibration", data=table)  # two channel columns (x, y) but only one sensor row
        ds.attrs["Start_Time"] = "2026-01-01T00:00:00"

    with pytest.raises(ValueError, match="sensor row per channel column"):
        load_recording(str(path))


def test_load_recording_reads_the_declared_primary_table(tmp_path):
    # No assumption that the primary table is called "acceleration"; the values are raw and the channel's
    # conversion says how they relate to the sensor's unit.
    path = tmp_path / "hand.hdf5"
    write_file(path, rows=[(0, 0, 512.0), (1, 100, 600.0)], conversion="linear")

    recording = load_recording(str(path))

    source = recording.sources["source1"]
    assert source.recording_metadata.start_time == "2026-02-02T00:00:00"
    assert source.hardware_metadata.adc_reference_voltage == "5.0"
    assert source.recording_data.channel1 == pytest.approx([512.0, 600.0])

    metadata = source.hardware_metadata.channel1_metadata
    assert (metadata.sensor.sensor_id, metadata.sensor.unit) == ("volt_01", "V")
    assert metadata.conversion == LinearConversion(gain=2.0, offset=-10.0)


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

    assert reloaded.sources["source1"].recording_metadata.start_time == original.sources["source1"].recording_metadata.start_time
    assert reloaded.sources["source1"].hardware_metadata.adc_reference_voltage == original.sources["source1"].hardware_metadata.adc_reference_voltage
    assert reloaded.sources["source1"].recording_data.counter == original.sources["source1"].recording_data.counter
    assert reloaded.sources["source1"].recording_data.timestamp == original.sources["source1"].recording_data.timestamp
    assert reloaded.sources["source1"].recording_data.channel1 == pytest.approx(original.sources["source1"].recording_data.channel1)

    sensor = reloaded.sources["source1"].hardware_metadata.channel1_metadata.sensor
    original_sensor = original.sources["source1"].hardware_metadata.channel1_metadata.sensor
    assert sensor.sensor_id == original_sensor.sensor_id
    assert sensor.unit == original_sensor.unit
    assert reloaded.sources["source1"].hardware_metadata.channel1_metadata.conversion == LinearConversion(
        gain=1.0, offset=0.0
    )


def test_save_recording_round_trips_a_linear_conversion_channel(tmp_path):
    path = tmp_path / "hand.hdf5"
    write_file(path, rows=[(0, 0, 512.0), (1, 100, 600.0)], conversion="linear")
    original = load_recording(str(path))

    out_file = tmp_path / "roundtrip_linear.hdf5"
    save_recording(original, str(out_file))
    reloaded = load_recording(str(out_file))

    conversion = reloaded.sources["source1"].hardware_metadata.channel1_metadata.conversion
    assert isinstance(conversion, LinearConversion)
    assert conversion.gain == pytest.approx(2.0)
    assert conversion.offset == pytest.approx(-10.0)
    assert reloaded.sources["source1"].recording_data.channel1 == pytest.approx([512.0, 600.0])


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


# ── the sensors table and the conversions ──────────────────────────────────

def _source(channels: int = 1, **extra) -> Source:
    """A minimal source whose channels have different conversions: linear, none, linear again."""
    conversions = [LinearConversion(gain=2.0, offset=-10.0), NoConversion(), LinearConversion(gain=0.5, offset=0.25)]
    metadata = {
        f"channel{c}_metadata": ChannelMetadata(
            sensor=Sensor(sensor_id=f"s{c}", name=f"Sensor {c}", unit="g", dimension="Acceleration"),
            conversion=conversions[c - 1],
        )
        for c in range(1, channels + 1)
    }
    return Source(
        name="source1",
        hardware_metadata=HardwareMetadata(**metadata),
        recording_metadata=RecordingMetadata(start_time="2026-01-01T00:00:00"),
        recording_data=RecordingData(
            timestamp=[0, 100, 200],
            counter=[0, 1, 2],
            **{f"channel{c}": [float(c), c + 0.5, c + 1.0] for c in range(1, channels + 1)},
        ),
        **extra,
    )


def test_every_channel_has_its_own_conversion(tmp_path):
    original = GeneratedRecording(sources=[_source(3)])
    save_recording(original, str(tmp_path / "c.hdf5"))
    hardware = load_recording(str(tmp_path / "c.hdf5")).sources["source1"].hardware_metadata

    assert hardware.channel1_metadata.conversion == LinearConversion(gain=2.0, offset=-10.0)
    assert hardware.channel2_metadata.conversion == NoConversion()
    assert hardware.channel3_metadata.conversion == LinearConversion(gain=0.5, offset=0.25)


def test_the_sensors_table_holds_the_sensor_and_the_conversion_and_nothing_else(tmp_path):
    save_recording(GeneratedRecording(sources=[_source(3)]), str(tmp_path / "t.hdf5"))
    with h5py.File(tmp_path / "t.hdf5") as f:
        table = f["sensors"][:]
        assert table.dtype.names == (
            "dimension",
            "name",
            "sensor_id",
            "sensor_type",
            "unit",
            "conversion",
            "gain",
            "offset",
        )
        assert [kind.decode() for kind in table["conversion"]] == ["linear", "none", "linear"]
        assert table["gain"].tolist() == [2.0, 1.0, 0.5]  # a conversion of none has the neutral values
        assert "conversion" not in f["recording"].attrs  # no table-wide flag any more


def test_a_sensor_field_that_is_not_set_stays_unset(tmp_path):
    source = _source(1)
    source.hardware_metadata.channel1_metadata.sensor = Sensor(name="only a name")
    save_recording(GeneratedRecording(sources=[source]), str(tmp_path / "u.hdf5"))

    sensor = load_recording(str(tmp_path / "u.hdf5")).sources["source1"].hardware_metadata.channel1_metadata.sensor
    assert sensor == Sensor(name="only a name")  # not '' for the fields that were never set


def test_start_time_and_reference_voltage_are_optional(tmp_path):
    source = _source(1)
    source.recording_metadata = RecordingMetadata()
    save_recording(GeneratedRecording(sources=[source]), str(tmp_path / "o.hdf5"))
    with h5py.File(tmp_path / "o.hdf5") as f:
        assert "Start_Time" not in f["recording"].attrs and "adc_reference_voltage" not in f["recording"].attrs

    loaded = load_recording(str(tmp_path / "o.hdf5")).sources["source1"]
    assert loaded.recording_metadata.start_time is None
    assert loaded.hardware_metadata.adc_reference_voltage is None


def test_description_and_mac_addresses_are_stored_as_attributes_of_the_primary_table(tmp_path):
    source = _source(1, description="a note", stu_mac="08-6B-D7-0F-47-2C", sth_mac="14-2D-41-D7-77-7D")
    save_recording(GeneratedRecording(sources=[source]), str(tmp_path / "m.hdf5"))
    with h5py.File(tmp_path / "m.hdf5") as f:
        attrs = f["recording"].attrs
        assert (attrs["description"], attrs["stu_mac"], attrs["sth_mac"]) == (
            "a note",
            "08-6B-D7-0F-47-2C",
            "14-2D-41-D7-77-7D",
        )
        assert "stu_id" not in attrs and "sth_id" not in attrs

    loaded = load_recording(str(tmp_path / "m.hdf5")).sources["source1"]
    assert (loaded.description, loaded.stu_mac, loaded.sth_mac) == ("a note", "08-6B-D7-0F-47-2C", "14-2D-41-D7-77-7D")


def test_every_source_of_several_has_its_own_description(tmp_path):
    first, second = _source(1, description="first"), _source(1, description="second")
    first.name, second.name = "a", "b"
    save_recording(GeneratedRecording(sources=[first, second]), str(tmp_path / "d.hdf5"))
    sources = load_recording(str(tmp_path / "d.hdf5")).sources
    assert [(str(name), source.description) for name, source in sources.items()] == [("a", "first"), ("b", "second")]


def test_a_conversion_the_format_cannot_store_is_refused_when_writing(tmp_path):
    source = _source(1)
    source.hardware_metadata.channel1_metadata.conversion = Conversion()  # the abstract base: no kind
    with pytest.raises(TypeError, match="Cannot write a conversion of type Conversion"):
        save_recording(GeneratedRecording(sources=[source]), str(tmp_path / "x.hdf5"))


def test_channel_data_without_metadata_is_refused_when_writing(tmp_path):
    source = _source(1)
    source.recording_data.channel2 = [1.0, 2.0, 3.0]
    with pytest.raises(ValueError, match="has channel2 data but no channel2_metadata"):
        save_recording(GeneratedRecording(sources=[source]), str(tmp_path / "x.hdf5"))


def test_a_file_without_a_sensors_table_is_refused(tmp_path):
    path = tmp_path / "none.hdf5"
    write_file(path, rows=[(0, 0, 1.0)])
    with h5py.File(path, "r+") as f:
        del f["sensors"]
    with pytest.raises(ValueError, match="no `sensors` table"):
        load_recording(str(path))


def test_a_file_with_an_empty_sensors_table_is_refused(tmp_path):
    path = tmp_path / "empty.hdf5"
    write_file(path, rows=[(0, 0, 1.0)])
    with h5py.File(path, "r+") as f:
        del f["sensors"]
        f.create_dataset("sensors", data=np.zeros(0, dtype=SENSOR_DTYPE))
    with pytest.raises(ValueError, match="sensor row per channel column"):
        load_recording(str(path))


def test_a_partial_sensors_table_is_refused(tmp_path):
    path = tmp_path / "partial.hdf5"
    write_file(path, rows=[(0, 0, 1.0)])
    with h5py.File(path, "r+") as f:
        table = np.zeros(1, dtype=[("counter", "u1"), ("timestamp", "<u8"), ("x", "<f4"), ("y", "<f4")])
        del f["vibration"]
        f.create_dataset("vibration", data=table).attrs["Start_Time"] = "t"
        del f["sensors"]
        f.create_dataset("sensors", data=make_sensor_row())  # one row for two channels
    with pytest.raises(ValueError, match="sensor row per channel column"):
        load_recording(str(path))


def test_an_unknown_kind_of_conversion_is_refused(tmp_path):
    path = tmp_path / "poly.hdf5"
    write_file(path, rows=[(0, 0, 1.0)], sensor_row=make_sensor_row(conversion=b"polynomial"))
    with pytest.raises(ValueError, match="unknown conversion 'polynomial'"):
        load_recording(str(path))


def test_an_unknown_primary_table_attribute_is_reported_as_dropped(tmp_path, caplog):
    path = tmp_path / "extra.hdf5"
    write_file(path, rows=[(0, 0, 1.0)])
    with h5py.File(path, "r+") as f:
        f["vibration"].attrs["Sensor_Range"] = "± 100.0 g₀"  # what a schema version 1 file may carry
        f["vibration"].attrs["conversion"] = "true"  # ... and the table-wide flag of version 1

    with caplog.at_level(logging.WARNING, logger="icoschema.v2.storage.hdf5"):
        load_recording(str(path))

    assert "Sensor_Range" in caplog.text and "conversion" in caplog.text
