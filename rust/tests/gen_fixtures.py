"""Builds the HDF5 fixtures in tests/fixtures and expected.json from the *Python* icoschema.

    uv run python rust/tests/gen_fixtures.py          # from the repository root

expected.json is what the Rust reader must reproduce (or, where Python raises, must reject).
"""
import json
import shutil
import sys
from pathlib import Path

import h5py
import numpy as np

from icoschema import DatasetBundle
from icoschema.schema.generated.python import dataset as g

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "fixtures"
OUT.mkdir(parents=True, exist_ok=True)
# A real file from the Python test suite (legacy-style sensors table).
shutil.copyfile(Path(__file__).resolve().parents[2] / "test/test_with_sensors.hdf5", OUT / "python_repo_with_sensors.h5")
rng = np.random.default_rng(7)

SENSOR = [("dimension", "S100"), ("name", "S100"), ("offset", "<f4"), ("phys_max", "<f4"), ("phys_min", "<f4"),
          ("scaling_factor", "<f4"), ("sensor_id", "S100"), ("sensor_type", "S100"), ("unit", "S10"),
          ("volt_max", "<f4"), ("volt_min", "<f4")]


def sensors(n, scaling=1.0, offset=0.0):
    rows = np.zeros(n, dtype=SENSOR)
    for i in range(n):
        rows[i] = (b"Acceleration", f"Sensor {i + 1}".encode(), offset, 100.0, -100.0, scaling,
                   f"s{i + 1}".encode(), b"ADXL1001", b"g", 3.3, 0.0)
    return rows


def counter_steps(rows_per_packet, packets, lose=(), start=250):
    """A wrapping 8-bit counter, `rows_per_packet` rows per packet, with the given packets lost."""
    out = []
    for p in range(packets):
        if p in lose:
            continue
        out += [(start + p) % 256] * rows_per_packet
    return np.array(out, dtype="u1")


def table(counter, channels, ts_step=100):
    dtype = [("counter", "u1"), ("timestamp", "<u8")] + [(f"channel{i + 1}", "<f4") for i in range(channels)]
    t = np.zeros(len(counter), dtype=dtype)
    t["counter"] = counter
    t["timestamp"] = np.arange(len(counter), dtype=np.uint64) * ts_step + 5
    for i in range(channels):
        t[f"channel{i + 1}"] = rng.normal(size=len(counter)) * (i + 1)
    return t


def write(path, tbl, *, name="recording", version="1.0", sens=None, attrs=None, compress=True, extra=None,
          **file_kw):
    with h5py.File(path, "w", **file_kw) as f:
        if version is not None:
            f.attrs["icoschema_format_version"] = version
            f.attrs["primary_table"] = name
        kw = {"compression": "gzip", "compression_opts": 4, "shuffle": True} if compress else {}
        d = f.create_dataset(name, data=tbl, **kw)
        for k, v in {"Start_Time": "2026-03-04T05:06:07.123456", "conversion": "true",
                     "adc_reference_voltage": "3.3", **(attrs or {})}.items():
            if v is not None:
                d.attrs[k] = v
        if sens is not None:
            f.create_dataset("sensors", data=sens)
        if extra:
            extra(f)


# 1. every feature of the current writer: preprocessed table, N-D computations, steps
rec_path = OUT / "bundle_full.h5"
base = table(counter_steps(1, 200, lose={5, 6, 60}), 3)
write(OUT / "_base.h5", base, sens=sensors(3), attrs={"pre_metadata": '{"tool": "T1"}', "post_metadata": '{"wear": 0.3}',
      "adc_prescaler": 2, "adc_acquisition_time": 8, "adc_oversample_rate": 64})
bundle = DatasetBundle.from_hdf5(str(OUT / "_base.h5"))
rec = bundle.recording
idx = rec.sample_index()
n = int(idx[-1]) + 1
freq, _ = rec.channel_sampling_frequency()
bundle = bundle.with_preprocessed(g.PreprocessedRecording(
    timestamp=[int(rec.timestamps[0]) + round(j * 1e6 / freq) for j in range(n)],
    channel1=[0.5] * n, channel2=[1.5] * n, channel3=[2.5] * n,
    channel_sampling_frequency=freq, sampling_frequency_source="hardware", fill_method="forward_fill",
    producer="test@1"))
bundle = bundle.with_computation("fft/channel1", g.DerivedDataset(
    key="fft/channel1", values=[float(i) for i in range(8)], shape=[2, 4], dtype="float32", unit="g",
    produced_by="fft@1", produced_at="2026-01-01T00:00:00", params='{"w": "hann"}', description="two rows"))
bundle = bundle.with_computation("timebase/sample_index", g.DerivedDataset(
    key="timebase/sample_index", values=[float(i) for i in range(5)], shape=[5], dtype="int64"))
bundle = bundle.with_computation("deep/er/path/x", g.DerivedDataset(
    key="deep/er/path/x", values=[1.0, 2.0, 3.0], shape=[3], dtype="float64"))
bundle = bundle.with_step(g.ComputationStep(
    node="fft", step_index=0, producer="fft@1", params='{"w": "hann"}', resolved_params='{"w": "hann", "d": 1}',
    inputs=["a", "", "ü-ö"], status="ok", summary="{}", output_keys=["fft/channel1"], started_at="2026-01-01T00:00:00",
    duration_s=1.25, environment='{"numpy": "2"}'))
bundle = bundle.with_step(g.ComputationStep(
    node="bad", step_index=1, producer="x@1", status="error", error="boom", inputs=["fft"], output_keys=[]))
bundle.to_hdf5(str(rec_path))
(OUT / "_base.h5").unlink()

# 2. a copy with a user block and the newest file format (superblock 3, object header 2, dense attributes)
def reencode(src, dst, **kw):
    with h5py.File(src) as s, h5py.File(dst, "w", **kw) as d:
        for k, v in s.attrs.items():
            d.attrs[k] = v
        for k in s:
            s.copy(k, d)

reencode(rec_path, OUT / "bundle_full_latest.h5", libver="latest")
reencode(rec_path, OUT / "bundle_full_userblock.h5", userblock_size=1024)
reencode(rec_path, OUT / "bundle_full_userblock_latest.h5", libver="latest", userblock_size=512)

# 3. single channel, 3 rows per packet, wraparound with and without loss, unconverted (linear), no ADC settings
write(OUT / "one_channel_linear.h5", table(counter_steps(3, 300, lose={10, 11, 100}), 1),
      sens=sensors(1, scaling=2.5, offset=-1.0), attrs={"conversion": "false"}, compress=False)
# 4. two channels, complete ADC settings, a lost packet right after the wrap
write(OUT / "two_channels_adc.h5", table(counter_steps(2, 150, lose={5}, start=253), 2), sens=sensors(2),
      attrs={"adc_prescaler": 1, "adc_acquisition_time": 4, "adc_oversample_rate": 32})
# 5. legacy (no version): table `acceleration`, no sensors, no conversion flag, Sensor_Range only, no reference voltage
write(OUT / "legacy.h5", table(counter_steps(1, 120, lose={7}), 3), name="acceleration", version=None,
      attrs={"conversion": None, "adc_reference_voltage": None, "Sensor_Range": "± 100.0 g₀"})
# 6. no sensor table, conversion already true, no Sensor_Range
write(OUT / "no_sensors.h5", table(counter_steps(1, 50), 2))
# 7. incomplete ADC settings (load works, sampling frequency must fail)
write(OUT / "adc_incomplete.h5", table(counter_steps(1, 50), 1), sens=sensors(1), attrs={"adc_prescaler": 2})
# 8. inconsistent rows per packet
bad = np.array([1, 1, 1, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5], dtype="u1")
write(OUT / "inconsistent_rows.h5", table(bad, 1), sens=sensors(1))
# 9. rejected files
write(OUT / "err_version.h5", table(counter_steps(1, 10), 1), sens=sensors(1), version="9.9")
write(OUT / "err_sensor_count.h5", table(counter_steps(1, 10), 2), sens=sensors(1))
write(OUT / "err_no_start_time.h5", table(counter_steps(1, 10), 1), sens=sensors(1), attrs={"Start_Time": None})
write(OUT / "err_four_channels.h5", table(counter_steps(1, 10), 4), sens=sensors(4))
write(OUT / "err_unconverted_no_sensors.h5", table(counter_steps(1, 10), 1), attrs={"conversion": "false"})


# 10. several sources (1.3), waveform sources without a packet counter (1.4), the pre-1.4 TDMS JSON
from icoschema import Recording


def meta(i, unit="g", name=None):
    return g.ChannelMetadata(
        sensor=g.Sensor(sensor_id=f"s{i}", sensor_type="ADXL1001", name=name or f"Sensor {i}", unit=unit,
                        dimension="Acceleration", phys_min=-100.0, phys_max=100.0, volt_min=0.0, volt_max=3.3),
        compensations=[g.NoConversion(order=0)])


def hardware(channels, **adc):
    return g.HardwareMetadata(adc_reference_voltage="3.3", **adc,
                              **{f"channel{i + 1}_metadata": meta(i + 1) for i in range(channels)})


def columns(n, channels):
    return {f"channel{i + 1}": [float(v) for v in rng.normal(size=n) * (i + 1)] for i in range(channels)}


def packet_source(name, packets, start, lose=(), channels=1, **extra):
    counter = [int(c) for c in counter_steps(1, packets, lose=set(lose))]
    n = len(counter)
    return g.Source(
        name=name, hardware_metadata=hardware(channels, adc_prescaler=2, adc_acquisition_time=8, adc_oversample_rate=64),
        recording_metadata=g.RecordingMetadata(start_time=start),
        recording_data=g.RecordingData(timestamp=[i * 100 + 5 for i in range(n)], counter=counter, **columns(n, channels)),
        **extra)


def waveform_source(name, rows, start, fs, quality=None, channels=1, **extra):
    return g.Source(
        name=name, hardware_metadata=hardware(channels), sampling_frequency=fs,
        quality=None if quality is None else g.QualityChannel(values=quality, sampling_frequency=10.0),
        recording_metadata=g.RecordingMetadata(start_time=start),
        recording_data=g.RecordingData(timestamp=[round(i * 1e6 / fs) for i in range(rows)], **columns(rows, channels)),
        **extra)


def preprocessed_for(recording, name, fill):
    s = recording.sources[name]
    n = int(s.sample_index()[-1]) + 1
    freq, _ = s.channel_sampling_frequency()
    return g.PreprocessedRecording(
        source=name, timestamp=[int(s.timestamps[0]) + round(j * 1e6 / freq) for j in range(n)],
        **{f"channel{i + 1}": [fill + i] * n for i in range(s.channel_count)},
        channel_sampling_frequency=freq, sampling_frequency_source="hardware", fill_method="forward_fill", producer="test@1")


def result(key, values=(1.0, 2.0)):
    return g.DerivedDataset(key=key, values=list(values), shape=[len(values)], dtype="float64")


def step(node, **kw):
    return g.ComputationStep(node=node, step_index=0, producer="rms@1", status="ok", **kw)


multi = DatasetBundle(recording=Recording(sources=[
    packet_source("a", 120, "2026-01-01T00:00:00", lose={5, 40}, channels=2, stu_id="STU1", sth_id="STH1"),
    packet_source("b", 90, "2026-01-01T00:00:07.250000", lose={10}, stu_id="STU2")]))
multi = multi.with_preprocessed(preprocessed_for(multi.recording, "b", 0.5))
for key in ("rms_a/channel1", "rms_b/channel1", "mix/channel1", "mix_a/channel1", "free/channel1", "loose/channel1"):
    multi = multi.with_computation(key, result(key))
multi = (multi
         .with_step(step("rms_a", source_node="a", output_keys=["rms_a/channel1"]))
         .with_step(step("rms_b", source_node="preprocessed:b", output_keys=["rms_b/channel1"]))
         .with_step(step("mix", inputs=["rms_a", "rms_b"], output_keys=["mix/channel1"]))
         .with_step(step("mix_a", inputs=["rms_a"], output_keys=["mix_a/channel1"]))
         .with_step(step("free", output_keys=["free/channel1"])))
multi.to_hdf5(str(OUT / "multi_source.h5"))

waveform = DatasetBundle(recording=Recording(sources=[
    waveform_source("source1", 300, "2025-04-17T14:08:29.342295", 9523.80952, quality=[100.0, 99.0, 98.5, 100.0],
                    channels=2, additional_data='{"file": {"name": "t"}, "group": null}')]))
waveform = waveform.with_preprocessed(preprocessed_for(waveform.recording, "source1", 1.0))
waveform = waveform.with_computation("rms/channel1", result("rms/channel1")).with_step(
    step("rms", source_node="preprocessed", output_keys=["rms/channel1"]))
waveform.to_hdf5(str(OUT / "waveform_single.h5"))

waveform_multi = DatasetBundle(recording=Recording(sources=[
    waveform_source("STU1", 200, "2025-04-17T14:08:29.342295", 9523.80952, quality=[100.0, 90.0], stu_id="STU1"),
    waveform_source("STU2", 150, "2025-04-17T14:08:36.842295", 2000.0, quality=[100.0, 80.0, 70.0], channels=2,
                    stu_id="STU2", additional_data='{"channels": {"x": {"unit_string": "g"}}}'),
    waveform_source("STU3", 100, "2025-04-17T14:08:20.000000", 4000.0),  # no quality: loss unknown
    packet_source("pkt", 60, "2025-04-17T14:08:30.000000", lose={3})]))
waveform_multi = waveform_multi.with_preprocessed(preprocessed_for(waveform_multi.recording, "STU2", 3.0))
waveform_multi.to_hdf5(str(OUT / "waveform_multi.h5"))

legacy_json = DatasetBundle(recording=Recording(sources=[packet_source("source1", 100, "2026-02-03T04:05:06", lose={7})]))
legacy_json.recording.sources["source1"].recording_metadata.post_metadata = (
    '{"tdms": {"sampling_frequency": 5000.0, "signal_loss_percentage": 2.5, "signal_loss_measured": true}, "other": 1}')
legacy_json.to_hdf5(str(OUT / "legacy_tdms_json.h5"))

# 11. rejected: a `sources` attribute that disagrees with the groups
for name, listed in (("err_duplicate_sources.h5", ["a", "a"]), ("err_missing_source_group.h5", ["a", "zzz"])):
    shutil.copyfile(OUT / "multi_source.h5", OUT / name)
    with h5py.File(OUT / name, "r+") as f:
        del f.attrs["sources"]
        f.attrs.create("sources", listed, dtype=h5py.string_dtype())


sys.path.insert(0, str(Path(__file__).resolve().parent))
from dump import dump

expected = {p.name: dump(p) for p in sorted(OUT.glob("*.h5"))}
(OUT / "expected.json").write_text(json.dumps(expected, indent=1, default=str))


def python_roundtrip(path):
    """What Python reads back after writing the bundle it read from `path` (its writer is not
    lossless: unset sensor texts come back as ""). The Rust writer must produce the same."""
    import tempfile

    try:
        bundle = DatasetBundle.from_hdf5(str(path), on_error="raise")
    except Exception:  # noqa: BLE001
        return None
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "again.h5"
        try:
            bundle.to_hdf5(str(target))
        except Exception as e:  # noqa: BLE001
            return {"write_error": type(e).__name__}
        return dump(target)


roundtrip = {p.name: r for p in sorted(OUT.glob("*.h5")) if (r := python_roundtrip(p)) is not None}
(OUT / "expected_roundtrip.json").write_text(json.dumps(roundtrip, indent=1, default=str))
for k, v in expected.items():
    print(f"{k:34} {'LOAD ERROR ' + v['load_error'] if 'load_error' in v else 'ok'}"
          f"{'' if k not in roundtrip else ('  (python cannot write it back)' if 'write_error' in roundtrip[k] else '')}")
