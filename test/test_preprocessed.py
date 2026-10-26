"""Tests for the 0.1.0b3 additions: gap helpers and sampling frequency on
`Recording`, process metadata and ADC settings in storage, compression,
format-version selection, and the `PreprocessedRecording` table with its
validation."""

import logging
from pathlib import Path

import h5py
import numpy as np
import pytest
from hdf5_helpers import write_v1_file

from icoschema import DatasetBundle, PreprocessedRecording, Recording
from icoschema.schema.generated.python import dataset as generated

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"
DEFAULT_TOTAL = 38_400_000 / (3 * 21 * 64)


def _recording(counter: list[int], *, channels: int = 1, **hardware) -> Recording:
    sensor = generated.Sensor(unit="g")
    channel_metadata = generated.ChannelMetadata(sensor=sensor, compensations=[generated.NoConversion(order=0)])
    data = {f"channel{i + 1}": [float(v) for v in range(len(counter))] for i in range(channels)}
    return Recording(
        hardware_metadata=generated.HardwareMetadata(
            **{f"channel{i + 1}_metadata": channel_metadata for i in range(channels)}, **hardware
        ),
        recording_metadata=generated.RecordingMetadata(start_time="2026-01-01T00:00:00"),
        recording_data=generated.RecordingData(timestamp=list(range(len(counter))), counter=counter, **data),
    )


def _preprocess(recording: Recording, **overrides) -> PreprocessedRecording:
    """A minimal forward-fill + rebase, standing in for the real producer."""
    index = recording.sample_index()
    repeats = np.diff(np.append(index, index[-1] + 1))
    fs, source = recording.channel_sampling_frequency()
    kwargs = {
        "timestamp": (recording.timestamps[0] + np.round(np.arange(index[-1] + 1) * 1e6 / fs)).astype(int).tolist(),
        "channel_sampling_frequency": fs,
        "sampling_frequency_source": source,
        "fill_method": "forward_fill",
        "producer": "test@0",
    }
    for name in ("channel1", "channel2", "channel3"):
        values = getattr(recording, name)
        if values.size:
            kwargs[name] = np.repeat(values, repeats).tolist()
    kwargs.update(overrides)
    return PreprocessedRecording(**kwargs)


# ── Recording: gap helpers ───────────────────────────────────────────────────

def test_rows_per_packet_and_sample_index_on_the_gap_free_fixture():
    recording = Recording.from_hdf5(str(FIXTURE))
    assert recording.rows_per_packet() == 3  # 1-channel recording
    index = recording.sample_index()
    assert index.dtype == np.int64
    assert np.array_equal(index, np.arange(48_027))
    assert not recording.filled_mask().any()


def test_sample_index_places_rows_after_lost_packets():
    # 3 rows per packet; packets 2 and 3 are lost (6 rows).
    recording = _recording([0, 0, 0, 1, 1, 1, 4, 4, 4])
    assert list(recording.sample_index()) == [0, 1, 2, 3, 4, 5, 12, 13, 14]
    assert list(np.flatnonzero(recording.filled_mask())) == [6, 7, 8, 9, 10, 11]


def test_sample_index_handles_loss_across_wraparound():
    recording = _recording([254, 255, 2])  # 0 and 1 lost, 1 row per packet
    assert list(recording.sample_index()) == [0, 1, 4]


def test_rows_per_packet_rejects_inconsistent_packets():
    with pytest.raises(ValueError, match="inconsistent rows per packet"):
        _recording([0, 0, 1, 1, 1, 2, 2, 3]).rows_per_packet()


def test_rows_per_packet_rejects_empty_counter():
    recording = _recording([0])
    recording.recording_data.counter = []  # the generated class won't construct with empty required columns
    with pytest.raises(ValueError, match="empty counter"):
        recording.rows_per_packet()


# ── Recording: sampling frequency ────────────────────────────────────────────

def test_sampling_frequency_defaults_to_the_default_adc_settings():
    recording = Recording.from_hdf5(str(FIXTURE))
    assert recording.total_sampling_frequency() == (pytest.approx(DEFAULT_TOTAL), "default")
    assert recording.channel_sampling_frequency() == (pytest.approx(DEFAULT_TOTAL), "default")  # 1 channel


def test_channel_sampling_frequency_splits_the_total_across_channels():
    recording = _recording([0, 1, 2], channels=3)
    assert recording.channel_count == 3
    assert recording.channel_sampling_frequency() == (pytest.approx(DEFAULT_TOTAL / 3), "default")


def test_sampling_frequency_uses_recorded_adc_settings():
    recording = _recording([0, 1, 2], adc_prescaler=1, adc_acquisition_time=3, adc_oversample_rate=32)
    assert recording.total_sampling_frequency() == (pytest.approx(38_400_000 / (2 * 16 * 32)), "hardware")


def test_sampling_frequency_rejects_partial_adc_settings():
    recording = _recording([0, 1, 2], adc_prescaler=2, adc_oversample_rate=64)
    with pytest.raises(ValueError, match="incomplete ADC settings"):
        recording.total_sampling_frequency()


def test_sampling_frequency_rejects_invalid_adc_settings():
    recording = _recording([0, 1, 2], adc_prescaler=2, adc_acquisition_time=8, adc_oversample_rate=0)
    with pytest.raises(ValueError, match="invalid ADC settings"):
        recording.total_sampling_frequency()


# ── storage: process metadata, ADC settings, unknown attributes ─────────────

def test_pre_and_post_metadata_survive_a_rewrite(tmp_path):
    recording = Recording.from_hdf5(str(FIXTURE))
    assert '"profile": "cirp_twm_open"' in recording.recording_metadata.pre_metadata
    assert '"tool_breakage": false' in recording.recording_metadata.post_metadata

    out_file = tmp_path / "rewritten.hdf5"
    DatasetBundle.from_hdf5(str(FIXTURE)).to_hdf5(str(out_file))
    reloaded = Recording.from_hdf5(str(out_file))

    assert reloaded.recording_metadata.pre_metadata == recording.recording_metadata.pre_metadata
    assert reloaded.recording_metadata.post_metadata == recording.recording_metadata.post_metadata


def test_adc_settings_are_read_and_round_tripped(tmp_path):
    v1_file = tmp_path / "adc.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 1.0), (1, 100, 2.0)], already_converted=True)
    with h5py.File(v1_file, "a") as f:
        f["vibration"].attrs["adc_prescaler"] = 1
        f["vibration"].attrs["adc_acquisition_time"] = b"3"  # string-typed attributes are accepted too
        f["vibration"].attrs["adc_oversample_rate"] = np.uint16(32)

    recording = Recording.from_hdf5(str(v1_file))
    hardware = recording.hardware_metadata
    assert (hardware.adc_prescaler, hardware.adc_acquisition_time, hardware.adc_oversample_rate) == (1, 3, 32)

    out_file = tmp_path / "adc_roundtrip.hdf5"
    recording.to_hdf5(str(out_file))
    assert Recording.from_hdf5(str(out_file)).total_sampling_frequency()[1] == "hardware"


def test_non_integer_adc_setting_is_rejected(tmp_path):
    v1_file = tmp_path / "bad_adc.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 1.0)], already_converted=True)
    with h5py.File(v1_file, "a") as f:
        f["vibration"].attrs["adc_prescaler"] = "two"

    with pytest.raises(ValueError, match="adc_prescaler"):
        Recording.from_hdf5(str(v1_file))


def test_unknown_primary_table_attributes_are_logged_as_dropped(tmp_path, caplog):
    v1_file = tmp_path / "extra.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 1.0)], already_converted=True)
    with h5py.File(v1_file, "a") as f:
        f["vibration"].attrs["operator"] = "someone"

    with caplog.at_level(logging.WARNING):
        Recording.from_hdf5(str(v1_file))
    assert "operator" in caplog.text


def test_pytables_bookkeeping_attributes_are_not_reported(caplog):
    with caplog.at_level(logging.WARNING):
        Recording.from_hdf5(str(FIXTURE))
    assert "unknown attributes" not in caplog.text


# ── storage: compression and format version ──────────────────────────────────

def test_datasets_are_written_compressed(tmp_path):
    bundle = DatasetBundle.from_hdf5(str(FIXTURE)).with_computation(
        "a/scalar", generated.DerivedDataset(key="a/scalar", values=[1.0], shape=[1], dtype="float64")
    )
    bundle = bundle.with_computation(
        "a/array", generated.DerivedDataset(key="a/array", values=[1.0, 2.0], shape=[2], dtype="float32")
    )
    out_file = tmp_path / "compressed.hdf5"
    bundle.to_hdf5(str(out_file))

    with h5py.File(out_file, "r") as f:
        assert f["recording"].compression == "gzip"
        assert f["recording"].shuffle
        assert f["computations/a/array"].compression == "gzip"
        assert f["computations/a/scalar"].compression is None  # too small to bother


def test_bundle_without_preprocessed_table_is_written_as_1_0(tmp_path):
    out_file = tmp_path / "plain.hdf5"
    DatasetBundle.from_hdf5(str(FIXTURE)).to_hdf5(str(out_file))
    with h5py.File(out_file, "r") as f:
        assert f.attrs["icoschema_format_version"] == "1.0"
        assert "preprocessed_table" not in f.attrs


def test_legacy_and_1_0_files_load_without_preprocessed_table(tmp_path):
    assert DatasetBundle.from_hdf5(str(FIXTURE)).preprocessed is None

    v1_file = tmp_path / "v1.hdf5"
    write_v1_file(v1_file, rows=[(0, 0, 1.0)], already_converted=True)
    with h5py.File(v1_file, "a") as f:
        f.create_dataset("preprocessed", data=np.zeros(1))  # not declared, and 1.0 has no such table
    assert DatasetBundle.from_hdf5(str(v1_file)).preprocessed is None


# ── PreprocessedRecording ────────────────────────────────────────────────────

def test_preprocessed_table_round_trips_as_format_1_1(tmp_path):
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    bundle = bundle.with_preprocessed(_preprocess(bundle.recording))
    out_file = tmp_path / "preprocessed.hdf5"
    bundle.to_hdf5(str(out_file))

    with h5py.File(out_file, "r") as f:
        assert f.attrs["icoschema_format_version"] == "1.1"
        assert f.attrs["preprocessed_table"] == "preprocessed"
        table = f["preprocessed"]
        assert table.dtype.names == ("timestamp", "channel1")
        assert table.dtype["channel1"] == np.float32
        assert table.compression == "gzip"

    reloaded = DatasetBundle.from_hdf5(str(out_file))
    preprocessed = reloaded.preprocessed
    assert isinstance(preprocessed, PreprocessedRecording)
    assert len(preprocessed) == 48_027
    assert preprocessed.channel1_values == pytest.approx(bundle.recording.channel1)
    assert preprocessed.timestamp == bundle.preprocessed.timestamp
    assert preprocessed.channel_sampling_frequency == pytest.approx(DEFAULT_TOTAL)
    assert str(preprocessed.sampling_frequency_source) == "default"
    assert preprocessed.fill_method == "forward_fill"
    assert preprocessed.producer == "test@0"
    assert list(preprocessed.to_dataframe().columns) == ["timestamp", "channel1"]


def test_preprocessed_table_on_a_lossy_recording_has_one_row_per_grid_position():
    recording = _recording([0, 0, 0, 1, 1, 1, 4, 4, 4])
    bundle = DatasetBundle(recording=recording).with_preprocessed(_preprocess(recording))
    assert len(bundle.preprocessed) == 15
    assert bundle.preprocessed.channel1[6:12] == [5.0] * 6  # forward-filled from the last row before the gap


def test_with_preprocessed_rejects_wrong_row_count():
    recording = _recording([0, 1, 2])
    with pytest.raises(ValueError, match="gap-free grid has 3"):
        DatasetBundle(recording=recording).with_preprocessed(
            _preprocess(recording, timestamp=[0, 1], channel1=[0.0, 1.0])
        )


def test_with_preprocessed_rejects_mismatched_channels():
    recording = _recording([0, 1, 2])
    with pytest.raises(ValueError, match="channels"):
        DatasetBundle(recording=recording).with_preprocessed(_preprocess(recording, channel2=[0.0, 1.0, 2.0]))


def test_with_preprocessed_rejects_non_positive_sampling_frequency():
    recording = _recording([0, 1, 2])
    with pytest.raises(ValueError, match="channel_sampling_frequency"):
        DatasetBundle(recording=recording).with_preprocessed(
            _preprocess(recording, channel_sampling_frequency=0.0)
        )


def test_preprocessed_requires_a_known_sampling_frequency_source():
    recording = _recording([0, 1, 2])
    with pytest.raises(ValueError, match="SamplingFrequencySource"):
        _preprocess(recording, sampling_frequency_source="guessed")


def test_inconsistent_preprocessed_table_in_a_file_raises_even_with_on_error_skip(tmp_path):
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    out_file = tmp_path / "inconsistent.hdf5"
    bundle.with_preprocessed(_preprocess(bundle.recording)).to_hdf5(str(out_file))
    with h5py.File(out_file, "a") as f:
        table = f["preprocessed"][:-1]
        attrs = dict(f["preprocessed"].attrs)
        del f["preprocessed"]
        f.create_dataset("preprocessed", data=table).attrs.update(attrs)

    with pytest.raises(ValueError, match="gap-free grid"):
        DatasetBundle.from_hdf5(str(out_file), on_error="skip")


def test_preprocessed_table_missing_an_attribute_raises(tmp_path):
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    out_file = tmp_path / "no_producer.hdf5"
    bundle.with_preprocessed(_preprocess(bundle.recording)).to_hdf5(str(out_file))
    with h5py.File(out_file, "a") as f:
        del f["preprocessed"].attrs["producer"]

    with pytest.raises(ValueError, match="producer"):
        DatasetBundle.from_hdf5(str(out_file))


def test_recording_from_hdf5_reads_a_1_1_file(tmp_path):
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    out_file = tmp_path / "preprocessed.hdf5"
    bundle.with_preprocessed(_preprocess(bundle.recording)).to_hdf5(str(out_file))
    assert len(Recording.from_hdf5(str(out_file)).counter) == 48_027


def test_with_recording_refuses_while_preprocessed_is_set():
    recording = _recording([0, 1, 2])
    bundle = DatasetBundle(recording=recording).with_preprocessed(_preprocess(recording))
    replacement = _recording([0, 1, 2, 3])

    with pytest.raises(ValueError, match="without_preprocessed"):
        bundle.with_recording(replacement)
    assert bundle.without_preprocessed().with_recording(replacement).recording is replacement


def test_with_computation_keeps_the_preprocessed_table():
    recording = _recording([0, 1, 2])
    bundle = DatasetBundle(recording=recording).with_preprocessed(_preprocess(recording))
    derived = generated.DerivedDataset(key="a", values=[1.0], shape=[1], dtype="float32")
    assert bundle.with_computation("a", derived).preprocessed is bundle.preprocessed
