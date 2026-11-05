//! Shared by the test files: fixture access and the comparison with what Python reads.
#![allow(dead_code)]

use std::path::PathBuf;

use icoschema::schema as g;
use icoschema::DatasetBundle;
use serde_json::Value;

pub fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures")
}

pub fn expected(file: &str) -> serde_json::Map<String, Value> {
    let text = std::fs::read_to_string(fixtures().join(file)).unwrap();
    serde_json::from_str::<Value>(&text).unwrap().as_object().unwrap().clone()
}

pub fn load(name: &str) -> icoschema::Result<DatasetBundle> {
    DatasetBundle::from_hdf5(fixtures().join(name).to_str().unwrap())
}

pub fn close(a: f64, b: f64) -> bool {
    a == b || (a - b).abs() <= 1e-9 * a.abs().max(b.abs()).max(1.0) || (a.is_nan() && b.is_nan())
}

fn floats(v: &Value) -> Vec<f64> {
    v.as_array().unwrap().iter().map(|x| x.as_f64().unwrap()).collect()
}
fn ints(v: &Value) -> Vec<i64> {
    v.as_array().unwrap().iter().map(|x| x.as_i64().unwrap()).collect()
}
fn opt_str(v: &Value) -> Option<String> {
    v.as_str().map(str::to_string)
}
fn opt_f64(v: &Value) -> Option<f64> {
    v.as_f64()
}
fn strs(v: &Value) -> Option<Vec<String>> {
    v.as_array().map(|a| a.iter().map(|x| x.as_str().unwrap().to_string()).collect())
}

fn assert_floats(what: &str, got: &[f64], want: &Value) {
    let want = floats(want);
    assert_eq!(got.len(), want.len(), "{what}: length");
    for (i, (g, w)) in got.iter().zip(&want).enumerate() {
        assert!(close(*g, *w), "{what}[{i}]: {g} != {w}");
    }
}

fn check_sensor(what: &str, got: &g::Sensor, want: &Value) {
    assert_eq!(got.sensor_id, opt_str(&want["sensor_id"]), "{what} sensor_id");
    assert_eq!(got.sensor_type, opt_str(&want["sensor_type"]), "{what} sensor_type");
    assert_eq!(got.name, opt_str(&want["name"]), "{what} name");
    assert_eq!(got.unit, opt_str(&want["unit"]), "{what} unit");
    assert_eq!(got.dimension, opt_str(&want["dimension"]), "{what} dimension");
    for (g, w, f) in [
        (got.phys_min, "phys_min", 0),
        (got.phys_max, "phys_max", 1),
        (got.volt_min, "volt_min", 2),
        (got.volt_max, "volt_max", 3),
    ] {
        let _ = f;
        assert_eq!(g.map(|v| v as f32), opt_f64(&want[w]).map(|v| v as f32), "{what} {w}");
    }
}

fn check_channel(what: &str, got: Option<&g::ChannelMetadata>, want: &Value) {
    match (got, want.is_null()) {
        (None, true) => {}
        (Some(meta), false) => {
            check_sensor(what, &meta.sensor, &want["sensor"]);
            let comps = want["compensations"].as_array().unwrap();
            assert_eq!(meta.compensations.len(), comps.len(), "{what} compensations");
            for (c, w) in meta.compensations.iter().zip(comps) {
                match (c, w["type"].as_str().unwrap()) {
                    (g::CompensationOrSubtype::NoConversion(n), "NoConversion") => assert_eq!(n.order as i64, w["order"]),
                    (g::CompensationOrSubtype::LinearConversion(l), "LinearConversion") => {
                        assert_eq!(l.order as i64, w["order"]);
                        assert!(close(l.gain, w["gain"].as_f64().unwrap()), "{what} gain");
                        assert!(close(l.offset, w["offset"].as_f64().unwrap()), "{what} offset");
                    }
                    (other, ty) => panic!("{what}: compensation {other:?} != {ty}"),
                }
            }
        }
        _ => panic!("{what}: presence of channel metadata differs"),
    }
}

/// `{"ok": v}` / `{"error": ..}` from the Python side.
fn outcome<T>(got: icoschema::Result<T>, want: &Value, check: impl FnOnce(T, &Value)) {
    match (got, want.get("ok")) {
        (Ok(v), Some(w)) => check(v, w),
        (Err(_), None) => assert!(want.get("error").is_some()),
        (Ok(_), None) => panic!("Rust succeeded where Python raised {want}"),
        (Err(e), Some(w)) => panic!("Rust failed ({e}) where Python returned {w}"),
    }
}

/// Everything a bundle holds, compared with the dump of Python's reading (`gen_fixtures.py`).
pub fn check_bundle(name: &str, b: &DatasetBundle, want: &Value) {
    let r = &b.recording;
    let hw = &r.hardware_metadata;

    assert_eq!(r.recording_metadata.start_time, opt_str(&want["start_time"]), "{name} start_time");
    assert_eq!(r.recording_metadata.pre_metadata, opt_str(&want["pre_metadata"]), "{name} pre_metadata");
    assert_eq!(r.recording_metadata.post_metadata, opt_str(&want["post_metadata"]), "{name} post_metadata");
    let adc: Vec<Option<i64>> = want["adc"].as_array().unwrap().iter().map(Value::as_i64).collect();
    assert_eq!(
        vec![hw.adc_prescaler, hw.adc_acquisition_time, hw.adc_oversample_rate].into_iter().map(|v| v.map(|v| v as i64)).collect::<Vec<_>>(),
        adc,
        "{name} adc"
    );
    assert_eq!(hw.adc_reference_voltage, opt_str(&want["adc_reference_voltage"]), "{name} reference voltage");
    check_channel(&format!("{name} ch1"), Some(&hw.channel1_metadata), &want["channels_meta"][0]);
    check_channel(&format!("{name} ch2"), hw.channel2_metadata.as_ref(), &want["channels_meta"][1]);
    check_channel(&format!("{name} ch3"), hw.channel3_metadata.as_ref(), &want["channels_meta"][2]);

    assert_eq!(r.timestamps().iter().map(|v| *v as i64).collect::<Vec<_>>(), ints(&want["timestamps"]), "{name} timestamps");
    assert_eq!(r.counter().iter().map(|v| *v as i64).collect::<Vec<_>>(), ints(&want["counter"]), "{name} counter");
    assert_floats(&format!("{name} channel1"), r.channel1(), &want["channel1"]);
    assert_floats(&format!("{name} channel2"), r.channel2(), &want["channel2"]);
    assert_floats(&format!("{name} channel3"), r.channel3(), &want["channel3"]);
    assert_eq!(r.channel_count() as i64, want["channel_count"], "{name} channel_count");
    assert!(close(r.signal_loss_percentage(), want["signal_loss_percentage"].as_f64().unwrap()), "{name} loss");

    outcome(r.rows_per_packet(), &want["rows_per_packet"], |g, w| assert_eq!(g as i64, *w, "{name} rows/packet"));
    outcome(r.sample_index(), &want["sample_index"], |g, w| assert_eq!(g, ints(w), "{name} sample_index"));
    outcome(r.filled_mask(), &want["filled"], |g, w| {
        assert_eq!(g.iter().filter(|m| **m).count() as i64, *w, "{name} filled")
    });
    let freq = |res: icoschema::Result<(f64, icoschema::model::FrequencySource)>, w: &Value, what: &str| {
        outcome(res, w, |(hz, src), w| {
            assert!(close(hz, w[0].as_f64().unwrap()), "{name} {what} hz");
            assert_eq!(format!("{src:?}").to_lowercase(), w[1].as_str().unwrap(), "{name} {what} source");
        })
    };
    freq(r.total_sampling_frequency(), &want["total_fs"], "total_fs");
    freq(r.channel_sampling_frequency(), &want["channel_fs"], "channel_fs");

    let s = r.summary();
    let ws = &want["summary"];
    assert_eq!(s.sample_count as i64, ws["sample_count"], "{name} summary count");
    assert_eq!(s.start_time, opt_str(&ws["start_time"]));
    let wch = ws["channels"].as_object().unwrap();
    assert_eq!(s.channels.len(), wch.len(), "{name} summary channels");
    for (n, c) in &s.channels {
        let w = &wch[*n];
        assert_eq!(c.sensor_id, opt_str(&w["sensor_id"]));
        assert_eq!(c.sensor_type, opt_str(&w["sensor_type"]));
        assert_eq!(c.unit, opt_str(&w["unit"]));
        for (g, k) in [(c.min, "min"), (c.max, "max"), (c.mean, "mean"), (c.std, "std")] {
            assert!(close(g, w[k].as_f64().unwrap()), "{name} summary {n}.{k}: {g} != {}", w[k]);
        }
    }

    match (&b.preprocessed, want["preprocessed"].is_null()) {
        (None, true) => {}
        (Some(p), false) => {
            let w = &want["preprocessed"];
            assert_eq!(p.timestamps().iter().map(|v| *v as i64).collect::<Vec<_>>(), ints(&w["timestamp"]));
            assert_floats("pre ch1", p.channel1_values(), &w["channel1"]);
            assert_floats("pre ch2", p.channel2_values(), &w["channel2"]);
            assert_floats("pre ch3", p.channel3_values(), &w["channel3"]);
            assert!(close(p.channel_sampling_frequency, w["fs"].as_f64().unwrap()));
            assert_eq!(p.fill_method, w["fill_method"].as_str().unwrap());
            assert_eq!(p.producer, w["producer"].as_str().unwrap());
            assert_eq!(format!("{}", p.sampling_frequency_source), w["source"].as_str().unwrap().trim_start_matches("SamplingFrequencySource.").to_lowercase());
        }
        _ => panic!("{name}: preprocessed presence differs"),
    }

    let wc = want["computations"].as_object().unwrap();
    let mut keys: Vec<_> = b.computations.keys().cloned().collect();
    keys.sort();
    assert_eq!(keys, wc.keys().cloned().collect::<Vec<_>>(), "{name} computation keys");
    for (k, w) in wc {
        let d = &b.computations[k];
        assert_eq!(d.shape.iter().map(|v| *v as i64).collect::<Vec<_>>(), ints(&w["shape"]), "{k} shape");
        assert_eq!(d.dtype, w["dtype"].as_str().unwrap(), "{k} dtype");
        assert_floats(k, &d.values, &w["values"]);
        for (got, field) in [(&d.unit, "unit"), (&d.produced_by, "produced_by"), (&d.produced_at, "produced_at"), (&d.params, "params"), (&d.description, "description")] {
            assert_eq!(got, &opt_str(&w[field]), "{k} {field}");
        }
    }

    let wsteps = want["steps"].as_array().unwrap();
    assert_eq!(b.steps.len(), wsteps.len(), "{name} steps");
    for (s, w) in b.steps.iter().zip(wsteps) {
        assert_eq!(s.node, w["node"].as_str().unwrap());
        assert_eq!(s.step_index as i64, w["step_index"]);
        assert_eq!(s.producer, w["producer"].as_str().unwrap());
        assert_eq!(s.params, opt_str(&w["params"]));
        assert_eq!(s.resolved_params, opt_str(&w["resolved_params"]));
        assert_eq!(s.inputs, strs(&w["inputs"]), "{} inputs", s.node);
        assert_eq!(s.output_keys, strs(&w["output_keys"]), "{} output_keys", s.node);
        assert_eq!(s.error, opt_str(&w["error"]));
        assert_eq!(s.summary, opt_str(&w["summary"]));
        assert_eq!(s.started_at, opt_str(&w["started_at"]));
        assert_eq!(s.duration_s, opt_f64(&w["duration_s"]));
        assert_eq!(s.environment, opt_str(&w["environment"]));
        assert_eq!(s.status.as_ref().map(|v| v.to_string()), opt_str(&w["status"]).map(|v| v.trim_start_matches("ComputationStatus.").to_string()));
    }
}
