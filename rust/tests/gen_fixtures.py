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


# ── the expected values, from Python ────────────────────────────────────────
def comp(c):
    return {"type": type(c).__name__, "order": c.order, **{k: getattr(c, k) for k in ("gain", "offset", "coefficients") if hasattr(c, k)}}

def channel_meta(m):
    if m is None:
        return None
    s = m.sensor
    return {"sensor": {k: getattr(s, k) for k in ("sensor_id", "sensor_type", "name", "unit", "dimension",
                                                  "phys_min", "phys_max", "volt_min", "volt_max")},
            "compensations": [comp(c) for c in m.compensations]}

def attempt(fn):
    try:
        return {"ok": fn()}
    except Exception as e:  # noqa: BLE001
        return {"error": type(e).__name__}

def dump(path):
    try:
        b = DatasetBundle.from_hdf5(str(path), on_error="raise")
    except Exception as e:  # noqa: BLE001
        return {"load_error": type(e).__name__}
    r = b.recording
    h, m = r.hardware_metadata, r.recording_metadata
    out = {
        "start_time": m.start_time, "pre_metadata": m.pre_metadata, "post_metadata": m.post_metadata,
        "adc": [h.adc_prescaler, h.adc_acquisition_time, h.adc_oversample_rate], "adc_reference_voltage": h.adc_reference_voltage,
        "channels_meta": [channel_meta(h.channel1_metadata), channel_meta(h.channel2_metadata), channel_meta(h.channel3_metadata)],
        "timestamps": [int(v) for v in r.timestamps], "counter": [int(v) for v in r.counter],
        "channel1": [float(v) for v in r.channel1], "channel2": [float(v) for v in r.channel2], "channel3": [float(v) for v in r.channel3],
        "channel_count": r.channel_count, "signal_loss_percentage": float(r.signal_loss_percentage),
        "rows_per_packet": attempt(r.rows_per_packet),
        "sample_index": attempt(lambda: [int(v) for v in r.sample_index()]),
        "filled": attempt(lambda: int(r.filled_mask().sum())),
        "total_fs": attempt(lambda: list(r.total_sampling_frequency())),
        "channel_fs": attempt(lambda: list(r.channel_sampling_frequency())),
        "summary": r.summary(),
        "preprocessed": None if b.preprocessed is None else {
            "timestamp": [int(v) for v in b.preprocessed.timestamp], "channel1": list(b.preprocessed.channel1),
            "channel2": list(b.preprocessed.channel2), "channel3": list(b.preprocessed.channel3),
            "fs": b.preprocessed.channel_sampling_frequency, "source": str(b.preprocessed.sampling_frequency_source),
            "fill_method": b.preprocessed.fill_method, "producer": b.preprocessed.producer},
        "computations": {k: {"shape": list(d.shape), "dtype": d.dtype, "values": list(d.values), "unit": d.unit,
                             "produced_by": d.produced_by, "produced_at": d.produced_at, "params": d.params,
                             "description": d.description} for k, d in sorted(b.computations.items())},
        "steps": [{"node": s.node, "step_index": s.step_index, "producer": s.producer, "params": s.params,
                   "resolved_params": s.resolved_params, "inputs": list(s.inputs) if s.inputs is not None else None,
                   "status": None if s.status is None else str(s.status), "error": s.error, "summary": s.summary,
                   "output_keys": list(s.output_keys) if s.output_keys is not None else None,
                   "started_at": s.started_at, "duration_s": s.duration_s, "environment": s.environment} for s in b.steps],
    }
    return out

expected = {p.name: dump(p) for p in sorted(OUT.glob("*.h5"))}
(OUT / "expected.json").write_text(json.dumps(expected, indent=1, default=str))
for k, v in expected.items():
    print(f"{k:34} {'LOAD ERROR ' + v['load_error'] if 'load_error' in v else 'ok'}")
