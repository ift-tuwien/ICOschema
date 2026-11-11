"""Reads an HDF5 file with the Python icoschema and returns everything as plain data (JSON-able).

Used to build `expected*.json` (gen_fixtures.py) and to check files the Rust writer wrote (interop.py).
Sources and preprocessed tables are lists (in source order), since JSON objects have no order.
"""

import json

from icoschema.v1 import DatasetBundle


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

def opaque_json(text):
    """`additional_data` is opaque JSON text: compared as data (key order and spacing are the writer's business)."""
    if text is None:
        return None
    try:
        return {"json": json.loads(text)}
    except ValueError:
        return {"text": text}


def dump_source(r):
    h, m = r.hardware_metadata, r.recording_metadata
    return {
        "name": str(r.name), "stu_id": r.stu_id, "sth_id": r.sth_id,
        "sampling_frequency": r.sampling_frequency, "additional_data": opaque_json(r.additional_data),
        "quality": None if r.quality is None else {"values": [float(v) for v in r.quality.values],
                                                    "sampling_frequency": r.quality.sampling_frequency},
        "start_time": m.start_time, "pre_metadata": m.pre_metadata, "post_metadata": m.post_metadata,
        "adc": [h.adc_prescaler, h.adc_acquisition_time, h.adc_oversample_rate], "adc_reference_voltage": h.adc_reference_voltage,
        "channels_meta": [channel_meta(h.channel1_metadata), channel_meta(h.channel2_metadata), channel_meta(h.channel3_metadata)],
        "timestamps": [int(v) for v in r.timestamps], "counter": [int(v) for v in r.counter],
        "channel1": [float(v) for v in r.channel1], "channel2": [float(v) for v in r.channel2], "channel3": [float(v) for v in r.channel3],
        "channel_count": r.channel_count, "has_counter": r.has_counter,
        "signal_loss_percentage": float(r.signal_loss_percentage), "signal_loss_measured": r.signal_loss_measured,
        "rows_per_packet": attempt(r.rows_per_packet),
        "sample_index": attempt(lambda: [int(v) for v in r.sample_index()]),
        "filled": attempt(lambda: int(r.filled_mask().sum())),
        "total_fs": attempt(lambda: list(r.total_sampling_frequency())),
        "channel_fs": attempt(lambda: list(r.channel_sampling_frequency())),
        "summary": r.summary(),
    }

def dump(path):
    try:
        b = DatasetBundle.from_hdf5(str(path), on_error="raise")
    except Exception as e:  # noqa: BLE001
        return {"load_error": type(e).__name__}
    r = b.recording
    names = [str(n) for n in r.sources]
    out = {
        "provenance": {"source_format": b.provenance.source_format, "source_format_version": b.provenance.source_format_version},
        "sources": [dump_source(s) for s in r.sources.values()],
        "start_offsets": [[n, o] for n, o in r.start_offsets().items()],
        "time_axis_head": {n: [float(v) for v in r.time_axis(n)[:3]] for n in names},
        "preprocessed": [{
            "source": str(t.source), "timestamp": [int(v) for v in t.timestamp], "channel1": list(t.channel1),
            "channel2": list(t.channel2), "channel3": list(t.channel3),
            "fs": t.channel_sampling_frequency, "sampling_frequency_source": str(t.sampling_frequency_source),
            "fill_method": t.fill_method, "producer": t.producer} for t in b.preprocessed_tables],
        "computations": {k: {"shape": list(d.shape), "dtype": d.dtype, "values": list(d.values), "unit": d.unit,
                             "produced_by": d.produced_by, "produced_at": d.produced_at, "params": d.params,
                             "description": d.description} for k, d in sorted(b.computations.items())},
        "steps": [{"node": s.node, "step_index": s.step_index, "producer": s.producer, "params": s.params,
                   "resolved_params": s.resolved_params, "inputs": list(s.inputs) if s.inputs is not None else None,
                   "status": None if s.status is None else str(s.status), "error": s.error, "summary": s.summary,
                   "output_keys": list(s.output_keys) if s.output_keys is not None else None,
                   "started_at": s.started_at, "duration_s": s.duration_s, "environment": s.environment,
                   "source_node": s.source_node} for s in b.steps],
        "source_of": {s.node: attempt(lambda s=s: b.source_of(str(s.node))) for s in b.steps},
        "computations_for_source": {n: sorted(b.computations_for_source(n)) for n in names},
    }
    return out
