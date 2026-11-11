//! `hdf5_format_versions`, writing in a chosen format version, `OnError` when reading and the `DateTime` helpers,
//! for schema versions 1 and 2 (the stored synthetic files of the Python package are the data).

use std::collections::HashMap;
use std::path::PathBuf;

use icoschema::{v1, v2};
use rust_hdf5::H5File;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn v1_data(name: &str) -> String {
    root().join("test/v1/data").join(name).to_str().unwrap().to_string()
}

fn v2_data(name: &str) -> String {
    root().join("test/v2/data").join(name).to_str().unwrap().to_string()
}

fn temporary(name: &str) -> String {
    let dir = std::env::temp_dir().join(format!("icoschema-rust-features-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join(name).to_str().unwrap().to_string()
}

/// The `icoschema_format_version` stored in a file.
fn stored_version(path: &str) -> String {
    H5File::open(path).unwrap().attr("icoschema_format_version").unwrap().read_string().unwrap()
}

// ── hdf5_format_versions ────────────────────────────────────────────────────

#[test]
fn the_format_versions_of_each_schema_version() {
    assert_eq!(v1::hdf5_format_versions(false), ["legacy", "1.0", "1.1", "1.2", "1.3", "1.4"]);
    assert_eq!(v1::hdf5_format_versions(true), ["1.0", "1.1", "1.2", "1.3", "1.4"]);
    assert_eq!(v2::hdf5_format_versions(false), ["2.0"]);
    assert_eq!(v2::hdf5_format_versions(true), ["2.0"]);
    // the top level is the latest schema version's
    assert_eq!(icoschema::hdf5_format_versions(true), v2::hdf5_format_versions(true));
}

// ── format_version when writing ─────────────────────────────────────────────

#[test]
fn v1_writes_the_oldest_version_that_fits_by_default_and_the_one_asked_for() {
    let bundle = v1::DatasetBundle::from_hdf5(&v1_data("hdf5_1.0_1ch.hdf5")).unwrap();
    let default = temporary("default.hdf5");
    bundle.to_hdf5(&default).unwrap();
    assert_eq!(stored_version(&default), "1.0");

    for version in ["1.0", "1.1", "1.2", "1.3", "1.4"] {
        let path = temporary(&format!("as_{version}.hdf5"));
        bundle.to_hdf5_with(&path, Some(version)).unwrap();
        assert_eq!(stored_version(&path), version);
        let again = v1::DatasetBundle::from_hdf5(&path).unwrap();
        assert_eq!(again.recording.source_names(), bundle.recording.source_names(), "{version}");
        assert_eq!(*again.recording.sources()[0], *bundle.recording.sources()[0], "{version}");
        // 1.3 keeps even a single source in a group, 1.4 always stores its name
        let stored = H5File::open(&path).unwrap();
        assert_eq!(stored.root_group().group("sources").is_ok(), version == "1.3", "{version}");
    }
}

#[test]
fn v1_refuses_a_version_that_cannot_hold_the_data_and_unknown_ones() {
    let multi = v1::DatasetBundle::from_hdf5(&v1_data("hdf5_1.3_1ch_multi.hdf5")).unwrap();
    let error = multi.to_hdf5_with(&temporary("multi_1_0.hdf5"), Some("1.0")).unwrap_err().to_string();
    assert!(error.contains("cannot write format \"1.0\"") && error.contains("it has 2 sources"), "{error}");

    let steps = v1::DatasetBundle::from_hdf5(&v1_data("hdf5_1.2_1ch.hdf5")).unwrap();
    assert!(!steps.steps.is_empty());
    let error = steps.to_hdf5_with(&temporary("steps_1_1.hdf5"), Some("1.1")).unwrap_err().to_string();
    assert!(error.contains("computation steps"), "{error}");

    let error = steps.to_hdf5_with(&temporary("nine.hdf5"), Some("9.9")).unwrap_err().to_string();
    assert!(error.contains("cannot write format_version \"9.9\"") && error.contains("1.4"), "{error}");
    let error = steps.to_hdf5_with(&temporary("legacy.hdf5"), Some("legacy")).unwrap_err().to_string();
    assert!(error.contains("writable versions"), "{error}");
}

#[cfg(feature = "tdms")]
#[test]
fn a_waveform_source_needs_the_version_with_source_features() {
    // a TDMS source has no packet counter, a sampling frequency, quality and additional data
    let waveform = v1::DatasetBundle::from_file(&v1_data("tdms_legacy_1ch.tdms")).unwrap();
    let default = temporary("waveform_default.hdf5");
    waveform.to_hdf5(&default).unwrap();
    assert_eq!(stored_version(&default), "1.4");
    for version in ["1.0", "1.1", "1.2", "1.3"] {
        let error = waveform.to_hdf5_with(&temporary("waveform_old.hdf5"), Some(version)).unwrap_err().to_string();
        assert!(
            error.contains(&format!("cannot write format {version:?}"))
                && error.contains("no packet counter")
                && error.contains("quality"),
            "{version}: {error}"
        );
    }
    let path = temporary("waveform_1_4.hdf5");
    waveform.to_hdf5_with(&path, Some("1.4")).unwrap();
    let again = v1::DatasetBundle::from_hdf5(&path).unwrap();
    let (before, after) = (&waveform.recording.sources()[0], &again.recording.sources()[0]);
    assert_eq!((before.name(), before.sampling_frequency), (after.name(), after.sampling_frequency));
    assert_eq!(before.quality, after.quality);
    assert!(after.counter().is_empty());
}

#[test]
fn v2_has_one_format() {
    let bundle = v2::DatasetBundle::from_hdf5(&v2_data("hdf5_2.0_3ch_multi.hdf5")).unwrap();
    let path = temporary("v2.hdf5");
    bundle.to_hdf5_with(&path, Some("2.0")).unwrap();
    assert_eq!(stored_version(&path), "2.0");
    for version in ["1.4", "2.1", "legacy"] {
        let error = bundle.to_hdf5_with(&temporary("v2_other.hdf5"), Some(version)).unwrap_err().to_string();
        assert!(error.contains(&format!("cannot write format_version {version:?}")) && error.contains("2.0"), "{error}");
    }
    // a recording alone, too
    let error = bundle.recording.to_hdf5_with(&temporary("v2_recording.hdf5"), Some("1.0")).unwrap_err().to_string();
    assert!(error.contains("cannot write format_version"), "{error}");
    bundle.recording.to_hdf5_with(&temporary("v2_recording.hdf5"), Some("2.0")).unwrap();
}

// ── on_error ────────────────────────────────────────────────────────────────

/// A v2 file whose step lists an output key that no computation has.
fn file_with_a_dangling_step() -> String {
    use icoschema::v2::schema as g;
    let bundle = v2::DatasetBundle::from_hdf5(&v2_data("hdf5_2.0_1ch.hdf5")).unwrap();
    let step = |node: &str, index: isize, keys: &[&str]| g::ComputationStep {
        node: node.into(),
        step_index: index,
        producer: "test".into(),
        params: None,
        resolved_params: None,
        inputs: None,
        status: None,
        error: None,
        summary: None,
        output_keys: Some(keys.iter().map(|k| k.to_string()).collect()),
        started_at: None,
        duration_s: None,
        environment: None,
        source_node: None,
    };
    let derived = g::DerivedDataset {
        key: "ok/values".into(),
        values: vec![1.0, 2.0],
        shape: vec![2],
        dtype: "float64".into(),
        unit: None,
        produced_by: None,
        produced_at: None,
        params: None,
        description: None,
    };
    let computations = HashMap::from([("ok/values".to_string(), derived)]);
    let steps = [step("good", 0, &["ok/values"]), step("dangling", 1, &["missing/values"])];
    let path = temporary("dangling.hdf5");
    icoschema::v2::storage::write::save(
        icoschema::v2::storage::write::Parts {
            sources: bundle.recording.sources().iter().map(|s| &**s).collect(),
            preprocessed: vec![],
            computations: &computations,
            steps: &steps,
            provenance: None,
            format_version: None,
        },
        &path,
    )
    .unwrap();
    path
}

#[test]
fn a_malformed_step_is_skipped_by_default_and_fails_the_read_with_raise() {
    let path = file_with_a_dangling_step();
    let (bundle, warnings) = v2::DatasetBundle::from_hdf5_with_warnings(&path, v2::OnError::Skip).unwrap();
    assert_eq!(bundle.steps.iter().map(|s| s.node.as_str()).collect::<Vec<_>>(), ["good"]);
    assert_eq!(bundle.steps[0].step_index, 0);
    assert!(bundle.computation("ok/values").is_some());
    assert_eq!(warnings.len(), 1);
    assert!(warnings[0].contains("dangling") && warnings[0].contains("missing/values"), "{warnings:?}");

    // the default is to skip
    let default = v2::DatasetBundle::from_hdf5(&path).unwrap();
    assert_eq!(default.steps.len(), 1);

    let error = v2::DatasetBundle::from_hdf5_with(&path, v2::OnError::Raise).err().unwrap().to_string();
    assert!(error.contains("dangling") && error.contains("output_keys missing"), "{error}");
}

#[test]
fn a_good_file_reads_the_same_either_way_and_without_warnings() {
    for name in ["hdf5_2.0_3ch.hdf5", "hdf5_2.0_3ch_multi.hdf5"] {
        let (skipped, warnings) = v2::DatasetBundle::from_hdf5_with_warnings(&v2_data(name), v2::OnError::Skip).unwrap();
        let (raised, _) = v2::DatasetBundle::from_hdf5_with_warnings(&v2_data(name), v2::OnError::Raise).unwrap();
        assert!(warnings.is_empty(), "{name}: {warnings:?}");
        assert_eq!(skipped.steps, raised.steps, "{name}");
        assert_eq!(skipped.computations, raised.computations, "{name}");
    }
    for name in ["hdf5_1.2_1ch.hdf5", "hdf5_1.4_3ch_multi.hdf5"] {
        let (bundle, warnings) = v1::DatasetBundle::from_hdf5_with_warnings(&v1_data(name), v1::OnError::Raise).unwrap();
        assert!(warnings.is_empty(), "{name}: {warnings:?}");
        assert_eq!(bundle.steps.is_empty(), name != "hdf5_1.2_1ch.hdf5", "{name}");
    }
}

#[test]
fn a_malformed_source_always_fails_the_read() {
    let error = v1::DatasetBundle::from_hdf5_with(
        &root().join("rust/tests/fixtures/err_sensor_count.h5").to_str().unwrap().to_string(),
        v1::OnError::Skip,
    )
    .err()
    .unwrap()
    .to_string();
    assert!(error.contains("sensor row"), "{error}");
}

// ── DateTime ────────────────────────────────────────────────────────────────

#[test]
fn the_start_of_a_source_as_a_datetime() {
    let bundle = v2::DatasetBundle::from_hdf5(&v2_data("hdf5_2.0_1ch_multi.hdf5")).unwrap();
    let sources = bundle.recording.sources();
    let (first, second) = (sources[0].start_datetime().unwrap().unwrap(), sources[1].start_datetime().unwrap().unwrap());
    assert_eq!(first.to_string(), "2026-03-04T05:06:07.000000");
    assert_eq!(second.seconds_since(first), 1.0);
    assert!(first < second);
    let parts = first.components();
    assert_eq!((parts.year, parts.month, parts.day, parts.hour, parts.minute, parts.second), (2026, 3, 4, 5, 6, 7));

    assert_eq!(bundle.recording.earliest_start_datetime().unwrap(), Some(first));
    assert_eq!(bundle.recording.earliest_start().unwrap(), Some(first.micros()));
    assert_eq!(bundle.recording.start_offsets().unwrap(), [("stu1", 0.0), ("stu2", 1.0)]);
    assert_eq!(first.plus_seconds(1.0), second);
}

#[test]
fn a_source_without_a_start_time_has_no_datetime() {
    let bundle = v2::DatasetBundle::from_hdf5(&v2_data("hdf5_2.0_1ch.hdf5")).unwrap();
    let mut inner: icoschema::v2::schema::Source = (**bundle.recording.only_source().unwrap()).clone();
    inner.recording_metadata.start_time = None;
    let source = v2::Source::from(inner.clone());
    assert_eq!(source.start_datetime().unwrap(), None);
    let recording = v2::Recording::single(inner).unwrap();
    assert_eq!(recording.earliest_start_datetime().unwrap(), None);

    let mut bad = (**bundle.recording.only_source().unwrap()).clone();
    bad.recording_metadata.start_time = Some("yesterday".into());
    assert!(v2::Source::from(bad).start_datetime().unwrap_err().to_string().contains("not an ISO 8601 time"));
}

#[test]
fn v1_has_the_same_datetime_helpers() {
    let bundle = v1::DatasetBundle::from_hdf5(&v1_data("hdf5_1.3_1ch_multi.hdf5")).unwrap();
    let starts: Vec<_> = bundle.recording.sources().iter().map(|s| s.start_datetime().unwrap()).collect();
    assert!(starts.iter().all(Option::is_some));
    assert_eq!(bundle.recording.earliest_start_datetime().unwrap(), starts.iter().flatten().min().copied());
}

/// `tests/gen_malformed_fixtures.py`: a computation of strings (`bad/text`) and a step that needs it (`uses_bad`),
/// next to the good computation `rms/ch1` and step `rms` of the v2 synthetic file it is made from.
fn malformed_computation_file() -> String {
    root().join("rust/tests/fixtures/malformed_computation.h5").to_str().unwrap().to_string()
}

#[test]
fn a_malformed_computation_is_skipped_with_its_step() {
    let path = malformed_computation_file();
    let (bundle, warnings) = v2::DatasetBundle::from_hdf5_with_warnings(&path, v2::OnError::Skip).unwrap();
    let mut keys: Vec<_> = bundle.computations.keys().map(String::as_str).collect();
    keys.sort();
    assert_eq!(keys, ["rms/ch1"]);
    assert_eq!(bundle.steps.iter().map(|s| s.node.as_str()).collect::<Vec<_>>(), ["rms"]);
    assert_eq!(bundle.steps[0].step_index, 0);
    assert_eq!(warnings.len(), 2, "{warnings:?}");
    assert!(warnings.iter().any(|w| w.contains("computation") && w.contains("bad/text") && w.contains("not numeric")), "{warnings:?}");
    assert!(warnings.iter().any(|w| w.contains("step") && w.contains("uses_bad")), "{warnings:?}");
    // the rest of the file is read as usual
    assert_eq!(bundle.recording.only_source().unwrap().recording_data.timestamp.len(), 10_000);
    assert_eq!(v2::DatasetBundle::from_hdf5(&path).unwrap().computations.len(), 1);
}

#[test]
fn a_malformed_computation_fails_the_read_with_raise() {
    let error = v2::DatasetBundle::from_hdf5_with(&malformed_computation_file(), v2::OnError::Raise)
        .err()
        .unwrap()
        .to_string();
    assert!(error.contains("bad/text") && error.contains("not numeric"), "{error}");
}
