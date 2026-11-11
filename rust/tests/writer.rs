//! The HDF5 writer: it must produce what Python's writer produces (compared through
//! `expected_roundtrip.json`), refuse what the file format cannot hold, and never leave a
//! half-written file behind.

mod common;

use std::path::PathBuf;

use common::{check_bundle, expected, fixtures, load};
use icoschema::v1::schema as g;
use icoschema::v1::{DatasetBundle, Recording, Source};

/// A path no other test (they run in parallel) uses.
fn temp(name: &str) -> PathBuf {
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let n = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("icoschema-writer-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join(name)
}

fn path(p: &std::path::Path) -> &str {
    p.to_str().unwrap()
}

fn only(recording: &Recording) -> &Source {
    recording.only_source().unwrap()
}

fn one(source: g::Source) -> Recording {
    Recording::single(source).unwrap()
}

// ── parity with the Python writer ───────────────────────────────────────────

#[test]
fn rewriting_every_fixture_reads_back_like_python_rewrites_it() {
    let want = expected("expected_roundtrip.json");
    let mut checked = 0;
    for (name, want) in &want {
        let original = load(name).unwrap_or_else(|e| panic!("{name}: {e}"));
        let target = temp(name);
        let written = original.to_hdf5(path(&target));
        if want.get("write_error").is_some() {
            assert!(written.is_err(), "{name}: Python cannot write this bundle but Rust did");
            continue;
        }
        written.unwrap_or_else(|e| panic!("{name}: {e}"));
        let again = DatasetBundle::from_hdf5(path(&target)).unwrap_or_else(|e| panic!("{name} (reread): {e}"));
        check_bundle(&format!("{name} (rewritten)"), &again, want);
        checked += 1;
    }
    assert!(checked >= 15, "only {checked} fixtures rewritten");
}

#[test]
fn recording_alone_is_written_as_format_1_0() {
    let recording = Recording::from_hdf5(path(&fixtures().join("bundle_full.h5"))).unwrap();
    let target = temp("alone.h5");
    recording.to_hdf5(path(&target)).unwrap();
    let bundle = DatasetBundle::from_hdf5(path(&target)).unwrap();
    assert!(bundle.preprocessed_tables.is_empty() && bundle.steps.is_empty() && bundle.computations.is_empty());
    assert_eq!(only(&bundle.recording).counter(), only(&recording).counter());
    // "1.0": the version attribute and nothing newer, not even the empty groups
    let file = rust_hdf5::H5File::open(&target).unwrap();
    assert_eq!(file.attr("icoschema_format_version").unwrap().read_string().unwrap(), "1.0");
    assert!(file.dataset("preprocessed").is_err());
}

#[test]
fn format_version_follows_the_content() {
    let full = DatasetBundle::from_hdf5(path(&fixtures().join("bundle_full.h5"))).unwrap();
    let version = |bundle: &DatasetBundle, name: &str| {
        let target = temp(name);
        bundle.to_hdf5(path(&target)).unwrap();
        rust_hdf5::H5File::open(&target).unwrap().attr("icoschema_format_version").unwrap().read_string().unwrap()
    };
    assert_eq!(version(&full, "v12.h5"), "1.2");
    let names: Vec<String> = full.steps.iter().map(|s| s.node.clone()).collect();
    let without_steps = full.clone().without_steps(names.iter().map(String::as_str)).unwrap();
    assert_eq!(version(&without_steps, "v11.h5"), "1.1");
    assert_eq!(version(&without_steps.without_preprocessed(None).unwrap(), "v10.h5"), "1.0");
}

// ── building bundles from scratch ───────────────────────────────────────────

fn sensor(i: usize) -> g::Sensor {
    g::Sensor {
        sensor_id: Some(format!("s{i}")),
        sensor_type: Some("ADXL1001".into()),
        name: Some(format!("Sensor {i}")),
        unit: Some("g".into()),
        dimension: Some("Acceleration".into()),
        phys_min: Some(-100.0),
        phys_max: Some(100.0),
        volt_min: Some(0.0),
        volt_max: Some(3.25),
    }
}

fn channel(i: usize, compensation: g::CompensationOrSubtype) -> g::ChannelMetadata {
    g::ChannelMetadata { sensor: sensor(i), compensations: vec![compensation] }
}

fn no_conversion() -> g::CompensationOrSubtype {
    g::CompensationOrSubtype::NoConversion(g::NoConversion { order: 0 })
}

fn recording(channels: usize, rows: usize) -> Recording {
    one(source("source1", channels, rows))
}

fn source(name: &str, channels: usize, rows: usize) -> g::Source {
    let column = |c: usize| (0..rows).map(|i| (i * (c + 1)) as f64 * 0.5).collect::<Vec<_>>();
    g::Source {
        name: name.into(),
        stu_id: None,
        sth_id: None,
        sampling_frequency: None,
        quality: None,
        additional_data: None,
        hardware_metadata: g::HardwareMetadata {
            revision: None,
            adc_reference_voltage: Some("3.3".into()),
            adc_prescaler: None,
            adc_acquisition_time: None,
            adc_oversample_rate: None,
            channel1_metadata: channel(1, no_conversion()),
            channel2_metadata: (channels > 1).then(|| channel(2, no_conversion())),
            channel3_metadata: (channels > 2).then(|| channel(3, no_conversion())),
        },
        recording_metadata: g::RecordingMetadata {
            start_time: Some("2026-01-02T03:04:05".into()),
            pre_metadata: None,
            post_metadata: Some("{}".into()),
        },
        recording_data: g::RecordingData {
            timestamp: (0..rows).map(|i| i as isize * 100).collect(),
            counter: Some((0..rows).map(|i| (i % 256) as isize).collect()),
            channel1: column(0),
            channel2: (channels > 1).then(|| column(1)),
            channel3: (channels > 2).then(|| column(2)),
        },
    }
}

fn derived(key: &str, shape: &[isize], dtype: &str, values: Vec<f64>) -> g::DerivedDataset {
    g::DerivedDataset {
        key: key.into(),
        values,
        shape: shape.to_vec(),
        dtype: dtype.into(),
        unit: Some("g".into()),
        produced_by: None,
        produced_at: None,
        params: Some("{\"a\": 1}".into()),
        description: None,
    }
}

fn step(node: &str, outputs: &[&str]) -> g::ComputationStep {
    g::ComputationStep {
        node: node.into(),
        step_index: 99, // assigned by with_step
        producer: "test@1".into(),
        params: None,
        resolved_params: None,
        inputs: Some(vec![]),
        status: Some(g::ComputationStatus::Ok),
        error: None,
        summary: None,
        output_keys: Some(outputs.iter().map(|s| s.to_string()).collect()),
        started_at: None,
        duration_s: Some(0.5),
        environment: None,
        source_node: None,
    }
}

#[test]
fn a_bundle_built_in_rust_survives_a_round_trip() {
    let bundle = DatasetBundle::new(recording(3, 700))
        .with_computation("fft/channel1", derived("fft/channel1", &[2, 3], "float32", (0..6).map(f64::from).collect()))
        .with_computation("fft/channel1.frequency", derived("fft/channel1.frequency", &[3], "float64", vec![0.5, 1.5, 2.5]))
        .with_computation("counts", derived("counts", &[4], "uint16", vec![0.0, 1.0, 65535.0, 7.0]))
        .with_computation("signed", derived("signed", &[2], "int8", vec![-128.0, 127.0]))
        .with_computation("one", derived("one", &[1], "float64", vec![42.0]))
        .with_step(step("fft", &["fft/channel1", "fft/channel1.frequency"]))
        .unwrap();
    assert_eq!(bundle.steps[0].step_index, 0);
    assert_eq!(bundle.unmanaged_keys().len(), 3);
    let target = temp("scratch.h5");
    bundle.to_hdf5(path(&target)).unwrap();

    let back = DatasetBundle::from_hdf5(path(&target)).unwrap();
    assert_eq!(only(&back.recording).counter(), only(&bundle.recording).counter());
    assert_eq!(only(&back.recording).timestamps(), only(&bundle.recording).timestamps());
    for (a, b) in only(&back.recording).channel3().iter().zip(only(&bundle.recording).channel3()) {
        assert_eq!(*a as f32, *b as f32);
    }
    assert_eq!(back.computations.len(), 5);
    let fft = &back.computations["fft/channel1"];
    assert_eq!((fft.shape.clone(), fft.dtype.as_str(), fft.values.clone()), (vec![2, 3], "float32", (0..6).map(f64::from).collect()));
    assert_eq!(fft.unit.as_deref(), Some("g"));
    assert_eq!(fft.params.as_deref(), Some("{\"a\": 1}"));
    assert_eq!(back.computations["counts"].values, [0.0, 1.0, 65535.0, 7.0]);
    assert_eq!(back.computations["counts"].dtype, "uint16");
    assert_eq!(back.computations["signed"].values, [-128.0, 127.0]);
    assert_eq!(back.computations["one"].values, [42.0]);
    assert_eq!(back.steps.len(), 1);
    assert_eq!(back.steps[0].output_keys.as_deref(), Some(&["fft/channel1".to_string(), "fft/channel1.frequency".to_string()][..]));
    assert_eq!(back.steps[0].inputs.as_deref(), Some(&[][..]));
    assert_eq!(back.steps[0].duration_s, Some(0.5));
    assert_eq!(back.computations_of("fft").unwrap().len(), 2);
}

#[test]
fn linear_conversion_and_tiny_recordings_round_trip() {
    for rows in [1, 2] {
        let mut rec = source("source1", 1, rows);
        rec.hardware_metadata.channel1_metadata.compensations =
            vec![g::CompensationOrSubtype::LinearConversion(g::LinearConversion { order: 0, gain: 2.5, offset: -1.0 })];
        let target = temp(&format!("linear{rows}.h5"));
        one(rec).to_hdf5(path(&target)).unwrap();
        let back = Recording::from_hdf5(path(&target)).unwrap();
        assert_eq!(only(&back).counter().len(), rows);
        match &only(&back).hardware_metadata.channel1_metadata.compensations[..] {
            [g::CompensationOrSubtype::LinearConversion(l)] => assert_eq!((l.gain, l.offset), (2.5, -1.0)),
            other => panic!("{other:?}"),
        }
    }
}

#[test]
fn a_recording_without_samples_is_refused() {
    // Python would write a table without channels, which nothing can read back.
    assert!(write_error(recording(1, 0)).contains("at least one sample"));
}

// ── what the file format cannot hold: errors, not silent loss ────────────────

fn write_error(rec: Recording) -> String {
    let target = temp("refused.h5");
    let _ = std::fs::remove_file(&target);
    let error = rec.to_hdf5(path(&target)).expect_err("should be refused").to_string();
    assert!(!target.exists(), "a refused write left a file behind");
    assert!(!PathBuf::from(format!("{}.tmp", path(&target))).exists(), "a refused write left its temporary file behind");
    error
}

#[test]
fn compensations_the_format_cannot_hold_are_refused() {
    let mut rec = source("source1", 2, 10);
    rec.hardware_metadata.channel2_metadata.as_mut().unwrap().compensations =
        vec![g::CompensationOrSubtype::PolynomialConversion(g::PolynomialConversion { order: 0, coefficients: vec![0.0, 1.0] })];
    let error = write_error(one(rec));
    assert!(error.contains("channel2") && error.contains("PolynomialConversion") && error.contains("not representable"), "{error}");

    for other in [
        g::CompensationOrSubtype::FrequencyCompensation(g::FrequencyCompensation { order: 0 }),
        g::CompensationOrSubtype::Conversion(g::Conversion { order: 0 }),
    ] {
        let mut rec = source("source1", 1, 10);
        rec.hardware_metadata.channel1_metadata.compensations = vec![other];
        assert!(write_error(one(rec)).contains("not representable"));
    }

    let mut rec = source("source1", 1, 10);
    rec.hardware_metadata.channel1_metadata.compensations = vec![no_conversion(), no_conversion()];
    assert!(write_error(one(rec)).contains("2 compensations"));
    let mut rec = source("source1", 1, 10);
    rec.hardware_metadata.channel1_metadata.compensations = vec![];
    assert!(write_error(one(rec)).contains("0 compensations"));
}

#[test]
fn hardware_revision_is_refused_because_the_format_has_no_place_for_it() {
    let mut rec = source("source1", 1, 10);
    rec.hardware_metadata.revision = Some("B".into());
    assert!(write_error(one(rec)).contains("revision is not stored"));
}

#[test]
fn mixed_conversion_states_are_refused() {
    let mut rec = source("source1", 2, 10);
    rec.hardware_metadata.channel2_metadata.as_mut().unwrap().compensations =
        vec![g::CompensationOrSubtype::LinearConversion(g::LinearConversion { order: 0, gain: 2.0, offset: 0.0 })];
    assert!(write_error(one(rec)).contains("different already-converted states"));
}

#[test]
fn malformed_columns_are_refused() {
    let mut rec = source("source1", 2, 10);
    rec.recording_data.channel2 = Some(vec![1.0; 9]);
    assert!(write_error(one(rec)).contains("same length"));

    let mut rec = source("source1", 1, 10);
    rec.recording_data.counter.as_mut().unwrap()[3] = 256;
    assert!(write_error(one(rec)).contains("does not fit in 8 bits"));

    let mut rec = source("source1", 1, 10);
    rec.recording_data.timestamp[3] = -1;
    assert!(write_error(one(rec)).contains("negative"));

    let mut rec = source("source1", 3, 10);
    rec.recording_data.channel2 = None; // channel3 without channel2
    assert!(write_error(one(rec)).contains("earlier channel"));

    let mut rec = source("source1", 1, 10);
    rec.recording_data.channel1 = vec![]; // samples, but no channel data
    assert!(write_error(one(rec)).contains("at least channel1"));
}

#[test]
fn texts_that_do_not_fit_their_field_are_refused() {
    let mut rec = source("source1", 1, 10);
    rec.hardware_metadata.channel1_metadata.sensor.name = Some("x".repeat(101));
    assert!(write_error(one(rec)).contains("does not fit in 100 bytes"));
    let mut rec = source("source1", 1, 10);
    rec.hardware_metadata.channel1_metadata.sensor.unit = Some("12345678901".into());
    assert!(write_error(one(rec)).contains("does not fit in 10 bytes"));
}

#[test]
fn computations_with_unwritable_data_are_refused() {
    let write = |key: &str, shape: &[isize], dtype: &str, values: Vec<f64>| {
        let target = temp("computation.h5");
        DatasetBundle::new(recording(1, 10))
            .with_computation(key, derived(key, shape, dtype, values))
            .to_hdf5(path(&target))
            .expect_err("should be refused")
            .to_string()
    };
    assert!(write("a", &[2], "float16", vec![0.0, 1.0]).contains("dtype \"float16\" is not supported"));
    assert!(write("a", &[2], "complex128", vec![0.0, 1.0]).contains("not supported"));
    assert!(write("a", &[3], "float64", vec![0.0, 1.0]).contains("needs 3 values"));
    assert!(write("a", &[-1], "float64", vec![]).contains("negative dimension"));
    assert!(write("a", &[], "float64", vec![1.0]).contains("no dimensions"));
    assert!(write("a", &[1], "int8", vec![200.0]).contains("out of range"));
    assert!(write("a", &[1], "uint8", vec![-1.0]).contains("out of range"));
    assert!(write("a", &[1], "int32", vec![1.5]).contains("not an integer"));
    assert!(write("a", &[1], "int32", vec![f64::NAN]).contains("not an integer"));
    assert!(write("a//b", &[1], "float64", vec![1.0]).contains("path segments"));
    assert!(write("../x", &[1], "float64", vec![1.0]).contains("path segments"));
    assert!(write("", &[1], "float64", vec![1.0]).contains("path segments"));
}

#[test]
fn a_computation_key_cannot_be_dataset_and_group() {
    let target = temp("clash.h5");
    let bundle = DatasetBundle::new(recording(1, 10))
        .with_computation("a", derived("a", &[1], "float64", vec![1.0]))
        .with_computation("a/b", derived("a/b", &[1], "float64", vec![1.0]));
    let error = bundle.to_hdf5(path(&target)).unwrap_err().to_string();
    assert!(error.contains("both a dataset and a group"), "{error}");
}

// ── the bundle's own rules (as in the Python model) ─────────────────────────

#[test]
fn steps_are_validated() {
    let bundle = DatasetBundle::new(recording(1, 10)).with_computation("x", derived("x", &[1], "float64", vec![1.0]));
    let refused = |b: DatasetBundle, s: g::ComputationStep| b.with_step(s).unwrap_err().to_string();
    assert!(refused(bundle.clone(), step("", &[])).contains("non-empty"));
    assert!(refused(bundle.clone(), step("a/b", &[])).contains("no '/'"));
    assert!(refused(bundle.clone(), step(".hidden", &[])).contains("not start with '.'"));
    assert!(refused(bundle.clone(), step("s", &["missing"])).contains("missing from computations"));
    let with = bundle.clone().with_step(step("s", &["x"])).unwrap();
    assert!(refused(with.clone(), step("s", &[])).contains("duplicate step name"));
    // a failed with_step leaves the bundle as it was
    assert_eq!(with.steps.len(), 1);
    let two = with.with_step(step("t", &[])).unwrap();
    assert_eq!(two.steps.iter().map(|s| s.step_index).collect::<Vec<_>>(), [0, 1]);

    // hand-edited steps are caught when writing
    let mut broken = two.clone();
    broken.steps[1].step_index = 5;
    let target = temp("broken-steps.h5");
    assert!(broken.to_hdf5(path(&target)).unwrap_err().to_string().contains("expected 1"));
    assert!(!target.exists());
}

#[test]
fn without_steps_renumbers_and_drops_the_outputs() {
    let bundle = DatasetBundle::new(recording(1, 10))
        .with_computation("a", derived("a", &[1], "float64", vec![1.0]))
        .with_computation("b", derived("b", &[1], "float64", vec![2.0]))
        .with_computation("loose", derived("loose", &[1], "float64", vec![3.0]))
        .with_step(step("one", &["a"]))
        .unwrap()
        .with_step(step("two", &["b"]))
        .unwrap();
    assert_eq!(bundle.unmanaged_keys().into_iter().collect::<Vec<_>>(), ["loose"]);
    assert!(bundle.clone().without_steps(["nope"]).unwrap_err().to_string().contains("no such step"));
    let after = bundle.without_steps(["one"]).unwrap();
    assert_eq!(after.steps.len(), 1);
    assert_eq!((after.steps[0].node.as_str(), after.steps[0].step_index), ("two", 0));
    let mut keys: Vec<_> = after.computations.keys().cloned().collect();
    keys.sort();
    assert_eq!(keys, ["b", "loose"]);
    assert!(after.computations_of("one").is_err());
}

#[test]
fn a_preprocessed_table_must_fit_the_recording() {
    let rec = recording(2, 10);
    let grid = 10;
    let table = |rows: usize, channel2: bool, frequency: f64| g::PreprocessedRecording {
        timestamp: (0..rows as isize).collect(),
        channel1: vec![0.0; rows],
        channel2: channel2.then(|| vec![0.0; rows]),
        channel3: None,
        channel_sampling_frequency: frequency,
        sampling_frequency_source: g::SamplingFrequencySource::Default,
        fill_method: "forward_fill".into(),
        producer: "t@1".into(),
        source: None,
    };
    let bundle = DatasetBundle::new(rec);
    let error = |p| bundle.clone().with_preprocessed(p, None).unwrap_err().to_string();
    assert!(error(table(grid, false, 100.0)).contains("channels [\"channel1\"], but the recording has [\"channel1\", \"channel2\"]"));
    assert!(error(table(grid - 1, true, 100.0)).contains("has 9 rows, but the recording's gap-free grid has 10"));
    assert!(error(table(grid, true, 0.0)).contains("positive and finite"));
    assert!(error(table(grid, true, f64::INFINITY)).contains("positive and finite"));
    let ok = bundle.clone().with_preprocessed(table(grid, true, 100.0), None).unwrap();

    let again = ok.clone().with_recording(recording(2, 10)).unwrap_err().to_string();
    assert!(again.contains("without_preprocessed"), "{again}");
    assert!(ok.without_preprocessed(None).unwrap().with_recording(recording(2, 20)).is_ok());
}

// ── files ───────────────────────────────────────────────────────────────────

#[test]
fn writing_replaces_an_existing_file_and_creates_folders() {
    let target = temp("nested/deeper/out.h5");
    let _ = std::fs::remove_dir_all(target.parent().unwrap());
    recording(1, 10).to_hdf5(path(&target)).unwrap();
    assert_eq!(only(&Recording::from_hdf5(path(&target)).unwrap()).counter().len(), 10);
    recording(1, 30).to_hdf5(path(&target)).unwrap(); // overwrites
    assert_eq!(only(&Recording::from_hdf5(path(&target)).unwrap()).counter().len(), 30);
    assert!(!PathBuf::from(format!("{}.tmp", path(&target))).exists());
}

#[test]
fn a_failed_write_keeps_the_previous_file() {
    let target = temp("keep.h5");
    recording(1, 10).to_hdf5(path(&target)).unwrap();
    let mut bad = source("source1", 1, 10);
    bad.recording_data.counter.as_mut().unwrap()[0] = 1000;
    assert!(one(bad).to_hdf5(path(&target)).is_err());
    assert_eq!(only(&Recording::from_hdf5(path(&target)).unwrap()).counter().len(), 10, "the old file must survive");
}

#[test]
fn the_written_file_is_compressed_like_pythons() {
    let bundle = DatasetBundle::new(recording(3, 50_000));
    let target = temp("size.h5");
    bundle.to_hdf5(path(&target)).unwrap();
    let raw = 50_000 * 21;
    let size = std::fs::metadata(&target).unwrap().len() as usize;
    assert!(size < raw / 2, "{size} bytes for {raw} raw bytes: the table is not compressed");
    let file = rust_hdf5::H5File::open(&target).unwrap();
    let dataset = file.dataset("recording").unwrap();
    assert!(dataset.is_chunked());
    assert_eq!(dataset.filters().unwrap().len(), 2, "shuffle + deflate");
}

