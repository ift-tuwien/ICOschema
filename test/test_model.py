"""Tests for the public model layer (ICOschema.model), the only thing other
codebases should import: Measurement.from_hdf5(), Measurement.to_dataframe(),
and the timestamps/channelN getters.
"""

from pathlib import Path

import numpy as np
import pytest
from hdf5_helpers import write_v1_file

from ICOschema.model.python.measurement import Measurement
from ICOschema.schema.generated.python import measurement as generated

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"


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


def test_from_hdf5_dispatches_to_v1_format(tmp_path):
    v1_file = tmp_path / "v1.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 512.0), (1, 100, 600.0)], already_converted=False)

    measurement = Measurement.from_hdf5(str(v1_file))
    df = measurement.to_dataframe()

    # Uncompensated: matches the raw "v" column values in the file directly,
    # even though this channel's LinearConversion says otherwise -- that
    # compensation is descriptive only, not applied by to_dataframe().
    assert list(df["channel1"]) == pytest.approx([512.0, 600.0])
