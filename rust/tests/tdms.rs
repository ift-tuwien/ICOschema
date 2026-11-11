//! The TDMS reader against what the Python icoschema (tdmspy) reads from the same files
//! (`tests/gen_tdms_fixtures.py` builds the fixtures and `expected_tdms.json`), plus what is
//! specific to the Rust reader.
#![cfg(feature = "tdms")]

mod common;

use std::path::PathBuf;

use common::close;
use icoschema::v1::{DatasetBundle, Source};
use serde_json::Value;

fn fixtures() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/tdms")
}

fn expected() -> serde_json::Map<String, Value> {
    let text = std::fs::read_to_string(fixtures().join("expected_tdms.json")).unwrap();
    serde_json::from_str::<Value>(&text).unwrap().as_object().unwrap().clone()
}

fn path(name: &str) -> String {
    fixtures().join(name).to_str().unwrap().to_string()
}

fn temp(name: &str) -> PathBuf {
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let n = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("icoschema-tdms-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join(name)
}

/// FNV-1a 64 of `bytes`, as in `gen_tdms_fixtures.py`.
fn fnv1a(bytes: &[u8]) -> String {
    let mut hash = 0xCBF2_9CE4_8422_2325u64;
    for byte in bytes {
        hash = (hash ^ u64::from(*byte)).wrapping_mul(0x0000_0100_0000_01B3);
    }
    format!("{hash:016x}")
}

fn floats(v: &Value) -> Vec<f64> {
    v.as_array().unwrap().iter().map(|x| x.as_f64().unwrap()).collect()
}

fn check_source(name: &str, source: &Source, want: &Value) {
    let name = format!("{name} [{}]", source.name());
    assert_eq!(source.name(), want["name"].as_str().unwrap(), "{name} name");
    assert_eq!(source.stu_id.as_deref(), want["stu_id"].as_str(), "{name} stu_id");
    assert!(close(source.sampling_frequency.unwrap(), want["sampling_frequency"].as_f64().unwrap()), "{name} rate");
    match (&source.quality, want["quality"].is_null()) {
        (None, true) => {}
        (Some(q), false) => {
            assert_eq!(q.values, floats(&want["quality"]["values"]), "{name} quality");
            assert_eq!(q.sampling_frequency, want["quality"]["sampling_frequency"].as_f64(), "{name} quality rate");
        }
        _ => panic!("{name}: presence of quality differs"),
    }
    let additional: Value = serde_json::from_str(source.additional_data.as_deref().unwrap()).unwrap();
    assert_eq!(additional, want["additional_data"], "{name} additional_data");
    assert_eq!(source.recording_metadata.start_time.as_deref(), want["start_time"].as_str(), "{name} start_time");
    assert_eq!(source.channel_count() as i64, want["channel_count"], "{name} channel_count");
    let sensors: Vec<Value> = [
        Some(&source.hardware_metadata.channel1_metadata),
        source.hardware_metadata.channel2_metadata.as_ref(),
        source.hardware_metadata.channel3_metadata.as_ref(),
    ]
    .into_iter()
    .map(|m| m.map_or(Value::Null, |m| serde_json::json!([m.sensor.name, m.sensor.unit])))
    .collect();
    assert_eq!(Value::Array(sensors), want["sensors"], "{name} sensors");
    assert!(source.hardware_metadata.channel1_metadata.compensations.len() == 1);

    // the samples: length, a hash of every value, and the first and last few for a readable failure
    let timestamps: Vec<i64> = source.timestamps().iter().map(|t| *t as i64).collect();
    assert_eq!(timestamps.len() as i64, want["rows"], "{name} rows");
    assert_eq!(timestamps.iter().take(4).copied().collect::<Vec<_>>(), want["timestamps_head"].as_array().unwrap().iter().map(|v| v.as_i64().unwrap()).collect::<Vec<_>>(), "{name} timestamps");
    let bytes: Vec<u8> = timestamps.iter().flat_map(|t| t.to_le_bytes()).collect();
    assert_eq!(fnv1a(&bytes), want["timestamps_hash"].as_str().unwrap(), "{name} timestamps hash");
    let channels = [source.channel1(), source.channel2(), source.channel3()];
    let head: Vec<f64> = channels[0].iter().take(4).copied().collect();
    let tail: Vec<f64> = channels[0].iter().rev().take(3).rev().copied().collect();
    if let Some(values) = want.get("channel1_values") {
        // numpy's polynomial evaluation is not reproducible to the last bit: compare with a tolerance
        let values = floats(values);
        assert_eq!(channels[0].len(), values.len(), "{name} channel1 length");
        for (i, (got, want)) in channels[0].iter().zip(&values).enumerate() {
            assert!((got - want).abs() <= 1e-12 * want.abs().max(1.0), "{name} channel1[{i}]: {got} != {want}");
        }
    } else {
        assert_eq!(head, floats(&want["channel1_head"]), "{name} channel1 head");
        assert_eq!(tail, floats(&want["channel1_tail"]), "{name} channel1 tail");
        for (i, values) in channels.iter().enumerate() {
            let hash = (!values.is_empty()).then(|| fnv1a(&values.iter().flat_map(|v| v.to_le_bytes()).collect::<Vec<u8>>()));
            assert_eq!(hash.as_deref(), want["channel_hashes"][i].as_str(), "{name} channel{} hash", i + 1);
        }
    }

    assert!(!source.has_counter(), "{name}: a TDMS source has no counter");
    assert!(close(source.signal_loss_percentage(), want["signal_loss_percentage"].as_f64().unwrap()), "{name} loss");
    assert_eq!(source.signal_loss_measured(), want["signal_loss_measured"].as_bool().unwrap(), "{name} measured");
    let (hz, origin) = source.channel_sampling_frequency().unwrap();
    assert!(close(hz, want["channel_fs"][0].as_f64().unwrap()), "{name} channel fs");
    assert_eq!(format!("{origin:?}").to_lowercase(), want["channel_fs"][1].as_str().unwrap());
}

fn check(name: &str, want: &Value) {
    let loaded = DatasetBundle::from_tdms_with_warnings(&path(name));
    if let Some(error) = want.get("load_error") {
        assert!(loaded.is_err(), "{name}: Rust loaded a file Python rejects ({error})");
        return;
    }
    let (bundle, warnings) = loaded.unwrap_or_else(|e| panic!("{name}: {e}"));
    let provenance = bundle.provenance.as_ref().unwrap();
    assert_eq!(provenance.source_format.as_deref(), want["provenance"]["source_format"].as_str());
    assert_eq!(provenance.source_format_version.as_deref(), want["provenance"]["source_format_version"].as_str());
    let want_warnings: Vec<&str> = want["warnings"].as_array().unwrap().iter().map(|w| w.as_str().unwrap()).collect();
    assert_eq!(warnings.iter().map(String::as_str).collect::<Vec<_>>(), want_warnings, "{name} warnings");

    let wsources = want["sources"].as_array().unwrap();
    assert_eq!(bundle.recording.sources().len(), wsources.len(), "{name} source count");
    for (source, w) in bundle.recording.sources().iter().zip(wsources) {
        check_source(name, source, w);
    }
    let offsets = bundle.recording.start_offsets().unwrap();
    for ((n, o), w) in offsets.iter().zip(want["start_offsets"].as_array().unwrap()) {
        assert_eq!(*n, w[0].as_str().unwrap());
        assert!(close(*o, w[1].as_f64().unwrap()), "{name} offset of {n}: {o} != {}", w[1]);
    }
}

macro_rules! fixture_tests {
    ($($test:ident => $file:literal),* $(,)?) => {$(
        #[test]
        fn $test() { check($file, &expected()[$file]); }
    )*};
}

fixture_tests! {
    one_stu_with_a_system_quality_group => "single_stu.tdms",
    no_quality_means_an_assumed_zero_loss => "single_stu_no_quality.tdms",
    float32_samples => "single_float32.tdms",
    several_stus_are_several_sources => "two_stus.tdms",
    the_longest_group_name_wins_and_sources_keep_file_order => "stu_prefixes.tdms",
    channels_keep_file_order_not_alphabetical_order => "channel_order.tdms",
    the_start_offset_is_added_to_the_start_time => "start_offset.tdms",
    linear_scaling_is_applied => "scaled_linear.tdms",
    linear_scaling_of_single_precision_data_stays_single_precision => "scaled_linear_float32.tdms",
    chained_polynomial_and_linear_scaling => "scaled_chain.tdms",
    data_declared_as_scaled_is_not_scaled_again => "scaled_already.tdms",
    scaling_declared_on_the_group => "scaled_group_level.tdms",
    several_segments_of_one_channel_set => "segments.tdms",
    quality_groups_that_do_not_match_the_channels_warn => "quality_mismatch.tdms",
    the_worst_of_several_quality_groups_is_kept => "quality_worst.tdms",
    the_real_two_stu_file_with_metadata_only_segments => "dual_stu.tdms",
    rejects_a_file_without_rawdata => "err_no_rawdata.tdms",
    rejects_channels_with_different_increments => "err_mixed_increments.tdms",
    rejects_four_channels => "err_four_channels.tdms",
    rejects_channels_of_unequal_length => "err_unequal_lengths.tdms",
    rejects_a_channel_without_increment => "err_no_increment.tdms",
    rejects_an_unknown_format_version => "err_version.tdms",
}

#[test]
fn every_fixture_has_a_test() {
    let files = std::fs::read_dir(fixtures()).unwrap().filter(|e| e.as_ref().unwrap().path().extension().is_some_and(|x| x == "tdms")).count();
    assert_eq!(files, expected().len());
    assert_eq!(files, 23, "add the new fixture to `fixture_tests!`");
}

// ── what is specific to the Rust reader ─────────────────────────────────────

#[test]
fn from_file_reads_tdms_by_content_and_the_result_saves_as_hdf5() {
    let renamed = temp("noextension");
    std::fs::copy(path("two_stus.tdms"), &renamed).unwrap();
    let bundle = DatasetBundle::from_file(renamed.to_str().unwrap()).unwrap();
    assert_eq!(bundle.recording.source_names(), ["STU1", "STU2"]);

    let target = temp("saved.h5");
    bundle.to_hdf5(target.to_str().unwrap()).unwrap();
    let back = DatasetBundle::from_hdf5(target.to_str().unwrap()).unwrap();
    let (stu2, original) = (back.recording.source("STU2").unwrap(), bundle.recording.source("STU2").unwrap());
    assert!(!stu2.has_counter());
    assert_eq!(stu2.sampling_frequency, original.sampling_frequency);
    assert_eq!(stu2.signal_loss_percentage(), original.signal_loss_percentage());
    assert_eq!(stu2.additional_data, original.additional_data);
    let provenance = back.provenance.unwrap();
    assert_eq!((provenance.source_format.as_deref(), provenance.source_format_version.as_deref()), (Some("tdms"), Some("legacy")));
}

#[test]
fn an_empty_float_quality_channel_is_an_error_not_a_panic() {
    // tdmspy reads this file (a quality channel that holds no values); the tedium crate divides by
    // zero on it. The acquisition software writes its empty quality channels void-typed (see
    // `the_real_two_stu_file...`), which works.
    let error = DatasetBundle::from_tdms(&path("single_stu_empty_quality.tdms")).unwrap_err().to_string();
    assert!(error.contains("TDMS library failed"), "{error}");
}

#[test]
fn recording_from_tdms_is_the_bundles_recording() {
    let recording = icoschema::v1::Recording::from_tdms(&path("single_stu.tdms")).unwrap();
    assert_eq!(recording.only_source().unwrap().name(), "source1");
}

#[test]
fn scale_types_the_reader_cannot_apply_are_refused_not_ignored() {
    // like tdmspy, this reader refuses RTD scaling instead of returning unscaled numbers
    let mut bytes = std::fs::read(path("scaled_linear.tdms")).unwrap();
    let kind = b"Linear";
    for at in 0..bytes.len() - kind.len() {
        if &bytes[at..at + kind.len()] == kind {
            bytes[at..at + kind.len()].copy_from_slice(b"Rtdxxx"); // same length: a scale type that is not supported
        }
    }
    let file = temp("rtd.tdms");
    std::fs::write(&file, &bytes).unwrap();
    let error = DatasetBundle::from_tdms(file.to_str().unwrap()).unwrap_err().to_string();
    assert!(error.contains("not supported"), "{error}");
}

#[test]
fn damaged_files_are_errors_never_panics() {
    let original = std::fs::read(path("segments.tdms")).unwrap();
    let mut state = 0x9E37_79B9_7F4A_7C15u64;
    let mut next = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    let dir = temp("damaged").parent().unwrap().to_path_buf();
    for round in 0..80 {
        let mut data = original.clone();
        if round % 5 == 0 {
            data.truncate((next() as usize) % data.len());
        } else {
            for _ in 0..[1, 3, 10][round % 3] {
                let at = (next() as usize) % data.len();
                data[at] = next() as u8;
            }
        }
        let file = dir.join(format!("damaged-{round}.tdms"));
        std::fs::write(&file, &data).unwrap();
        let result = std::panic::catch_unwind(|| DatasetBundle::from_tdms_with_warnings(file.to_str().unwrap()).map(|_| ()));
        assert!(result.is_ok(), "round {round}: panicked");
    }
}

#[test]
fn a_file_that_is_no_tdms_is_refused() {
    let junk = temp("junk.tdms");
    std::fs::write(&junk, b"definitely not a TDMS file, but long enough to have a lead-in....").unwrap();
    assert!(DatasetBundle::from_tdms(junk.to_str().unwrap()).is_err());
    assert!(DatasetBundle::from_tdms(&path("does-not-exist.tdms")).is_err());
}
