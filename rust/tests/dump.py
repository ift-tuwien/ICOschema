"""Reads an HDF5 file with the Python icoschema and returns everything as plain data (JSON-able).

Used to build `expected*.json` (gen_fixtures.py) and to check files the Rust writer wrote (interop.py).
"""

from icoschema import DatasetBundle


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

