"""Tests for the public model layer (ICOschema.model), the only thing other
codebases should import: Recording.from_hdf5(), Recording.to_dataframe(),
the timestamps/channelN getters, and DatasetBundle.from_hdf5()/.to_hdf5().
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest
from hdf5_helpers import write_v1_file

from ICOschema.model.python.dataset_bundle import DatasetBundle
from ICOschema.model.python.recording import Recording
from ICOschema.schema.generated.python import dataset as generated

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"


def _recording_with_counter(counter: list[int]) -> Recording:
    """A minimal Recording with an arbitrary counter, for signal_loss_percentage tests."""
    sensor = generated.Sensor(unit="g")
    channel_metadata = generated.ChannelMetadata(sensor=sensor, compensations=[generated.NoConversion(order=0)])
    return Recording(
        hardware_metadata=generated.HardwareMetadata(channel1_metadata=channel_metadata),
        recording_metadata=generated.RecordingMetadata(start_time="2026-01-01T00:00:00"),
        recording_data=generated.RecordingData(
            timestamp=list(range(len(counter))),
            counter=counter,
            channel1=[0.0] * len(counter),
        ),
    )


def test_from_hdf5_returns_a_recording_with_all_generated_fields():
    recording = Recording.from_hdf5(str(FIXTURE))

    assert isinstance(recording, Recording)
    assert isinstance(recording, generated.Recording)  # still a real generated.Recording too

    assert recording.recording_metadata.start_time == "2026-07-07T11:01:15.141594"
    assert recording.hardware_metadata.adc_reference_voltage == "3.3"

    channel1_metadata = recording.hardware_metadata.channel1_metadata
    assert channel1_metadata.sensor.sensor_id == "acc100g_01"
    # Compensation is descriptive only -- the plain generated class, untouched.
    assert isinstance(channel1_metadata.compensations[0], generated.NoConversion)


def test_to_dataframe_produces_raw_uncompensated_columnar_data():
    recording = Recording.from_hdf5(str(FIXTURE))
    df = recording.to_dataframe()

    assert list(df.columns) == ["timestamp", "counter", "channel1"]
    assert len(df) == 48027

    assert list(df["counter"][:5]) == [0, 0, 0, 1, 1]
    assert list(df["timestamp"][:5]) == [0, 0, 0, 1237, 1237]
    assert df["channel1"].iloc[0] == pytest.approx(87.85954284667969)


def test_channel_and_timestamp_getters_return_numpy_arrays():
    recording = Recording.from_hdf5(str(FIXTURE))

    assert isinstance(recording.timestamps, np.ndarray)
    assert isinstance(recording.channel1, np.ndarray)
    assert list(recording.timestamps[:3]) == recording.recording_data.timestamp[:3]
    assert recording.channel1[:3] == pytest.approx([87.85954284667969, 87.86335754394531, 87.87098693847656])

    # channel2/channel3 aren't populated in this fixture, but the getters
    # still return (empty) numpy arrays rather than raising.
    assert isinstance(recording.channel2, np.ndarray)
    assert recording.channel2.size == 0
    assert recording.channel3.size == 0


def test_signal_loss_percentage_is_zero_for_the_fixture():
    # This fixture's counter increments cleanly (with repeats, no gaps) up to
    # its 8-bit wraparound at 255 -> 0, so no loss should be inferred.
    recording = Recording.from_hdf5(str(FIXTURE))
    assert recording.signal_loss_percentage == pytest.approx(0.0)


def test_signal_loss_percentage_ignores_repeats_and_clean_wraparound():
    # 253->254 (normal), 254->254 (repeat), 254->255->0 (clean 8-bit
    # wraparound), 0->1 (normal): a continuous, gap-free sequence throughout.
    recording = _recording_with_counter([253, 254, 254, 255, 0, 1])
    assert recording.signal_loss_percentage == pytest.approx(0.0)


def test_signal_loss_percentage_counts_plain_gap():
    # 1 -> 5 skips 2, 3, 4: 3 lost out of 3 received + 3 lost.
    recording = _recording_with_counter([0, 1, 5])
    assert recording.signal_loss_percentage == pytest.approx(3 / (3 + 3) * 100)


def test_signal_loss_percentage_counts_gap_across_wraparound():
    # 255 -> 2 skips 0, 1 (wraparound with loss): 2 lost out of 3 received + 2 lost.
    recording = _recording_with_counter([254, 255, 2])
    assert recording.signal_loss_percentage == pytest.approx(2 / (3 + 2) * 100)


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_is_json_encodable():
    recording = Recording.from_hdf5(str(FIXTURE))
    # Raises if anything in the tree isn't a plain str/int/float/None/dict/list
    # (e.g. a numpy scalar or array) -- no custom encoder should ever be needed.
    json.dumps(recording.summary())


def test_summary_top_level_fields():
    recording = Recording.from_hdf5(str(FIXTURE))
    summary = recording.summary()

    assert summary["start_time"] == "2026-07-07T11:01:15.141594"
    assert summary["sample_count"] == 48_027
    assert summary["signal_loss_percentage"] == pytest.approx(recording.signal_loss_percentage)


def test_summary_includes_stats_and_sensor_identity_for_present_channels():
    recording = Recording.from_hdf5(str(FIXTURE))
    summary = recording.summary()

    assert set(summary["channels"].keys()) == {"channel1"}  # this fixture has no channel2/3
    channel1 = summary["channels"]["channel1"]
    assert channel1["sensor_id"] == "acc100g_01"
    assert channel1["sensor_type"] == "ADXL1001"
    assert channel1["unit"] == "g"
    assert channel1["sample_count"] == 48_027
    assert channel1["min"] == pytest.approx(float(recording.channel1.min()))
    assert channel1["max"] == pytest.approx(float(recording.channel1.max()))
    assert channel1["mean"] == pytest.approx(float(recording.channel1.mean()))
    assert channel1["std"] == pytest.approx(float(recording.channel1.std()))


def test_summary_omits_absent_channels():
    recording = _recording_with_counter([0, 1, 2])
    summary = recording.summary()
    assert set(summary["channels"].keys()) == {"channel1"}


def test_summary_values_are_plain_python_types_not_numpy_scalars():
    recording = Recording.from_hdf5(str(FIXTURE))
    summary = recording.summary()
    channel1 = summary["channels"]["channel1"]

    for value in (channel1["min"], channel1["max"], channel1["mean"], channel1["std"]):
        assert type(value) is float  # not np.float32/np.float64
    assert type(summary["sample_count"]) is int
    assert not math.isnan(channel1["std"])


def test_from_hdf5_dispatches_to_v1_format(tmp_path):
    v1_file = tmp_path / "v1.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 512.0), (1, 100, 600.0)], already_converted=False)

    recording = Recording.from_hdf5(str(v1_file))
    df = recording.to_dataframe()

    # Uncompensated: matches the raw "v" column values in the file directly,
    # even though this channel's LinearConversion says otherwise -- that
    # compensation is descriptive only, not applied by to_dataframe().
    assert list(df["channel1"]) == pytest.approx([512.0, 600.0])


def test_recording_to_hdf5_round_trips_through_from_hdf5(tmp_path):
    recording = Recording.from_hdf5(str(FIXTURE))
    out_file = tmp_path / "roundtrip.hdf5"

    recording.to_hdf5(str(out_file))
    reloaded = Recording.from_hdf5(str(out_file))

    assert reloaded.recording_metadata.start_time == recording.recording_metadata.start_time
    assert reloaded.channel1 == pytest.approx(recording.channel1)
    assert list(reloaded.counter) == list(recording.counter)


# ── DatasetBundle ────────────────────────────────────────────────────────────

def test_dataset_bundle_from_hdf5_has_empty_computations_for_a_bare_recording():
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))

    assert isinstance(bundle.recording, Recording)  # upgraded to the model class, not left as generated.Recording
    assert bundle.computations == {}


def test_dataset_bundle_with_computation_and_to_hdf5_round_trips(tmp_path):
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    derived = generated.DerivedDataset(
        key="wavelet_coefficients/channel1/details",
        values=[1.0, 2.0, 3.0, 4.0],
        shape=[2, 2],
        dtype="float64",
        unit="g",
        produced_by="wavelet_transform@1.0.0",
    )
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)

    out_file = tmp_path / "bundle.hdf5"
    bundle.to_hdf5(str(out_file))
    reloaded = DatasetBundle.from_hdf5(str(out_file))

    assert set(reloaded.computations.keys()) == {"wavelet_coefficients/channel1/details"}
    entry = reloaded.computations["wavelet_coefficients/channel1/details"]
    assert np.array(entry.values).reshape(entry.shape) == pytest.approx(np.array([[1.0, 2.0], [3.0, 4.0]]))
    assert entry.unit == "g"


def test_dataset_bundle_with_recording_replaces_recording_only():
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    corrected = _recording_with_counter([0, 1, 2])

    updated = bundle.with_recording(corrected)

    assert updated.recording is corrected
    assert updated.computations == bundle.computations
    assert bundle.recording is not corrected  # original bundle untouched
