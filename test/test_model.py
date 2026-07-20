"""Tests for the public model layer (ICOschema.model), the only thing other
codebases should import: Measurement.from_hdf5(), Measurement.to_dataframe(),
and the timestamps/channelN getters.
"""

import json
import math
from pathlib import Path

import numpy as np
import pytest
from hdf5_helpers import write_v1_file

from ICOschema.model.python.measurement import Measurement
from ICOschema.schema.generated.python import measurement as generated

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"


def _measurement_with_counter(counter: list[int]) -> Measurement:
    """A minimal Measurement with an arbitrary counter, for signal_loss_percentage tests."""
    sensor = generated.Sensor(unit="g")
    channel_metadata = generated.ChannelMetadata(sensor=sensor, compensations=[generated.NoConversion(order=0)])
    return Measurement(
        hardware_metadata=generated.HardwareMetadata(channel1_metadata=channel_metadata),
        measurement_metadata=generated.MeasurementMetadata(start_time="2026-01-01T00:00:00"),
        measurement_data=generated.MeasurementData(
            timestamp=list(range(len(counter))),
            counter=counter,
            channel1=[0.0] * len(counter),
        ),
    )


def test_from_hdf5_returns_a_measurement_with_all_generated_fields():
    measurement = Measurement.from_hdf5(str(FIXTURE))

    assert isinstance(measurement, Measurement)
    assert isinstance(measurement, generated.Measurement)  # still a real generated.Measurement too

    assert measurement.measurement_metadata.start_time == "2026-07-07T11:01:15.141594"
    assert measurement.hardware_metadata.adc_reference_voltage == "3.3"

    channel1_metadata = measurement.hardware_metadata.channel1_metadata
    assert channel1_metadata.sensor.sensor_id == "acc100g_01"
    # Compensation is descriptive only -- the plain generated class, untouched.
    assert isinstance(channel1_metadata.compensations[0], generated.NoConversion)


def test_to_dataframe_produces_raw_uncompensated_columnar_data():
    measurement = Measurement.from_hdf5(str(FIXTURE))
    df = measurement.to_dataframe()

    assert list(df.columns) == ["timestamp", "counter", "channel1"]
    assert len(df) == 48027

    assert list(df["counter"][:5]) == [0, 0, 0, 1, 1]
    assert list(df["timestamp"][:5]) == [0, 0, 0, 1237, 1237]
    assert df["channel1"].iloc[0] == pytest.approx(87.85954284667969)


def test_channel_and_timestamp_getters_return_numpy_arrays():
    measurement = Measurement.from_hdf5(str(FIXTURE))

    assert isinstance(measurement.timestamps, np.ndarray)
    assert isinstance(measurement.channel1, np.ndarray)
    assert list(measurement.timestamps[:3]) == measurement.measurement_data.timestamp[:3]
    assert measurement.channel1[:3] == pytest.approx([87.85954284667969, 87.86335754394531, 87.87098693847656])

    # channel2/channel3 aren't populated in this fixture, but the getters
    # still return (empty) numpy arrays rather than raising.
    assert isinstance(measurement.channel2, np.ndarray)
    assert measurement.channel2.size == 0
    assert measurement.channel3.size == 0


def test_signal_loss_percentage_is_zero_for_the_fixture():
    # This fixture's counter increments cleanly (with repeats, no gaps) up to
    # its 8-bit wraparound at 255 -> 0, so no loss should be inferred.
    measurement = Measurement.from_hdf5(str(FIXTURE))
    assert measurement.signal_loss_percentage == pytest.approx(0.0)


def test_signal_loss_percentage_ignores_repeats_and_clean_wraparound():
    # 253->254 (normal), 254->254 (repeat), 254->255->0 (clean 8-bit
    # wraparound), 0->1 (normal): a continuous, gap-free sequence throughout.
    measurement = _measurement_with_counter([253, 254, 254, 255, 0, 1])
    assert measurement.signal_loss_percentage == pytest.approx(0.0)


def test_signal_loss_percentage_counts_plain_gap():
    # 1 -> 5 skips 2, 3, 4: 3 lost out of 3 received + 3 lost.
    measurement = _measurement_with_counter([0, 1, 5])
    assert measurement.signal_loss_percentage == pytest.approx(3 / (3 + 3) * 100)


def test_signal_loss_percentage_counts_gap_across_wraparound():
    # 255 -> 2 skips 0, 1 (wraparound with loss): 2 lost out of 3 received + 2 lost.
    measurement = _measurement_with_counter([254, 255, 2])
    assert measurement.signal_loss_percentage == pytest.approx(2 / (3 + 2) * 100)


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_is_json_encodable():
    measurement = Measurement.from_hdf5(str(FIXTURE))
    # Raises if anything in the tree isn't a plain str/int/float/None/dict/list
    # (e.g. a numpy scalar or array) -- no custom encoder should ever be needed.
    json.dumps(measurement.summary())


def test_summary_top_level_fields():
    measurement = Measurement.from_hdf5(str(FIXTURE))
    summary = measurement.summary()

    assert summary["start_time"] == "2026-07-07T11:01:15.141594"
    assert summary["sample_count"] == 48_027
    assert summary["signal_loss_percentage"] == pytest.approx(measurement.signal_loss_percentage)


def test_summary_includes_stats_and_sensor_identity_for_present_channels():
    measurement = Measurement.from_hdf5(str(FIXTURE))
    summary = measurement.summary()

    assert set(summary["channels"].keys()) == {"channel1"}  # this fixture has no channel2/3
    channel1 = summary["channels"]["channel1"]
    assert channel1["sensor_id"] == "acc100g_01"
    assert channel1["sensor_type"] == "ADXL1001"
    assert channel1["unit"] == "g"
    assert channel1["sample_count"] == 48_027
    assert channel1["min"] == pytest.approx(float(measurement.channel1.min()))
    assert channel1["max"] == pytest.approx(float(measurement.channel1.max()))
    assert channel1["mean"] == pytest.approx(float(measurement.channel1.mean()))
    assert channel1["std"] == pytest.approx(float(measurement.channel1.std()))


def test_summary_omits_absent_channels():
    measurement = _measurement_with_counter([0, 1, 2])
    summary = measurement.summary()
    assert set(summary["channels"].keys()) == {"channel1"}


def test_summary_values_are_plain_python_types_not_numpy_scalars():
    measurement = Measurement.from_hdf5(str(FIXTURE))
    summary = measurement.summary()
    channel1 = summary["channels"]["channel1"]

    for value in (channel1["min"], channel1["max"], channel1["mean"], channel1["std"]):
        assert type(value) is float  # not np.float32/np.float64
    assert type(summary["sample_count"]) is int
    assert not math.isnan(channel1["std"])


def test_from_hdf5_dispatches_to_v1_format(tmp_path):
    v1_file = tmp_path / "v1.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 512.0), (1, 100, 600.0)], already_converted=False)

    measurement = Measurement.from_hdf5(str(v1_file))
    df = measurement.to_dataframe()

    # Uncompensated: matches the raw "v" column values in the file directly,
    # even though this channel's LinearConversion says otherwise -- that
    # compensation is descriptive only, not applied by to_dataframe().
    assert list(df["channel1"]) == pytest.approx([512.0, 600.0])
