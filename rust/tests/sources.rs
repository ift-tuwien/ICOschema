//! Several sources, waveform sources (format 1.4), provenance, start offsets and the bundle's
//! tracing of steps to sources: the rules of `test/test_sources.py`, `test_format_1_4.py` and
//! `test_tdms.py` (the part that does not read TDMS) in the Python package.

mod common;

use std::path::PathBuf;

use common::{fixtures, load};
use icoschema::v1::schema as g;
use icoschema::v1::{DatasetBundle, Recording, Source};

fn temp(name: &str) -> PathBuf {
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let n = NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    let dir = std::env::temp_dir().join(format!("icoschema-sources-{}-{n}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join(name)
}

fn path(p: &std::path::Path) -> &str {
    p.to_str().unwrap()
}

fn version(target: &std::path::Path) -> String {
    rust_hdf5::H5File::open(target).unwrap().attr("icoschema_format_version").unwrap().read_string().unwrap()
}

fn channel() -> g::ChannelMetadata {
    g::ChannelMetadata {
        sensor: g::Sensor {
            sensor_id: None,
            sensor_type: None,
            name: Some("Channel1".into()),
            unit: Some("g".into()),
            dimension: None,
            phys_min: None,
            phys_max: None,
            volt_min: None,
            volt_max: None,
        },
        compensations: vec![g::CompensationOrSubtype::NoConversion(g::NoConversion { order: 0 })],
    }
}

fn base(name: &str, start: Option<&str>, rows: usize) -> g::Source {
    g::Source {
        name: name.into(),
        stu_id: None,
        sth_id: None,
        sampling_frequency: None,
        quality: None,
        additional_data: None,
        hardware_metadata: g::HardwareMetadata {
            revision: None,
            adc_reference_voltage: None,
            adc_prescaler: None,
            adc_acquisition_time: None,
            adc_oversample_rate: None,
            channel1_metadata: channel(),
            channel2_metadata: None,
            channel3_metadata: None,
        },
        recording_metadata: g::RecordingMetadata { start_time: start.map(str::to_string), pre_metadata: None, post_metadata: None },
        recording_data: g::RecordingData {
            timestamp: (0..rows as isize).map(|i| i * 100_000).collect(),
            counter: None,
            channel1: (0..rows).map(|i| i as f64).collect(),
            channel2: None,
            channel3: None,
        },
    }
}

/// A packet source: a wrapping counter, one row per packet.
fn packet(name: &str, start: Option<&str>, rows: usize) -> g::Source {
    let mut source = base(name, start, rows);
    source.recording_data.counter = Some((0..rows).map(|i| (i % 256) as isize).collect());
    source
}

/// A waveform source (what a TDMS file gives): no counter, its own rate and quality.
fn waveform(name: &str, start: Option<&str>, rows: usize, fs: f64) -> g::Source {
    let mut source = base(name, start, rows);
    source.sampling_frequency = Some(fs);
    source.quality = Some(g::QualityChannel { values: vec![100.0, 90.0], sampling_frequency: Some(10.0) });
    source.additional_data = Some("{\"file\": {\"name\": \"t\"}}".into());
    source
}

fn recording(sources: Vec<g::Source>) -> Recording {
    Recording::new(sources.into_iter().map(Source::from).collect()).unwrap()
}

fn table(source: &str, rows: usize, channels: usize) -> g::PreprocessedRecording {
    g::PreprocessedRecording {
        timestamp: (0..rows as isize).collect(),
        channel1: vec![1.0; rows],
        channel2: (channels > 1).then(|| vec![2.0; rows]),
        channel3: None,
        channel_sampling_frequency: 10.0,
        sampling_frequency_source: g::SamplingFrequencySource::Hardware,
        fill_method: "forward_fill".into(),
        producer: "t@1".into(),
        source: Some(source.into()),
    }
}

fn step(node: &str, source_node: Option<&str>, inputs: &[&str], outputs: &[&str]) -> g::ComputationStep {
    g::ComputationStep {
        node: node.into(),
        step_index: 0,
        producer: "t@1".into(),
        params: None,
        resolved_params: None,
        inputs: Some(inputs.iter().map(|s| s.to_string()).collect()),
        status: Some(g::ComputationStatus::Ok),
        error: None,
        summary: None,
        output_keys: Some(outputs.iter().map(|s| s.to_string()).collect()),
        started_at: None,
        duration_s: None,
        environment: None,
        source_node: source_node.map(str::to_string),
    }
}

fn result(key: &str) -> g::DerivedDataset {
    g::DerivedDataset { key: key.into(), values: vec![1.0], shape: vec![1], dtype: "float64".into(), unit: None, produced_by: None, produced_at: None, params: None, description: None }
}

// ── the recording ────────────────────────────────────────────────────────────

#[test]
fn source_names_must_be_unique_path_segments() {
    let refused = |names: &[&str]| {
        Recording::new(names.iter().map(|n| Source::from(packet(n, None, 3))).collect()).unwrap_err().to_string()
    };
    assert!(refused(&[]).contains("at least one source"));
    assert!(refused(&["a", "a"]).contains("duplicate source name"));
    assert!(refused(&["a/b"]).contains("no '/'"));
    assert!(refused(&[".hidden"]).contains("not start with '.'"));
    assert!(refused(&[""]).contains("non-empty"));
}

#[test]
fn only_source_names_the_sources_when_there_are_several() {
    let rec = recording(vec![packet("a", None, 3), packet("b", None, 3)]);
    let error = rec.only_source().unwrap_err().to_string();
    assert!(error.contains("2 sources") && error.contains("\"a\"") && error.contains("\"b\""), "{error}");
    assert_eq!(rec.source("b").unwrap().name(), "b");
    assert!(rec.source("c").is_none());
}

#[test]
fn sources_are_placed_by_their_start_times_without_touching_their_timestamps() {
    let rec = recording(vec![
        packet("late", Some("2026-01-01T00:00:10.500000"), 3),
        packet("early", Some("2026-01-01T00:00:00"), 3),
        packet("none", None, 3),
    ]);
    assert_eq!(rec.earliest_start().unwrap(), Some(1_767_225_600_000_000)); // 2026-01-01T00:00:00 UTC
    let offsets = rec.start_offsets().unwrap();
    assert_eq!(offsets.iter().map(|(n, _)| *n).collect::<Vec<_>>(), ["late", "early", "none"]);
    assert_eq!(offsets.iter().map(|(_, o)| *o).collect::<Vec<_>>(), [10.5, 0.0, 0.0]);
    for (got, want) in rec.time_axis(Some("late")).unwrap().iter().zip([10.5, 10.6, 10.7]) {
        assert!((got - want).abs() < 1e-9, "{got} != {want}");
    }
    assert_eq!(rec.source("late").unwrap().timestamps(), [0, 100_000, 200_000]);
    assert!(rec.time_axis(None).unwrap_err().to_string().contains("3 sources"));
    assert!(recording(vec![packet("x", Some("later"), 3)]).start_offsets().is_err());
}

// ── what a source derives ────────────────────────────────────────────────────

#[test]
fn a_source_without_counter_is_a_gap_free_grid_with_its_own_rate() {
    let source = Source::from(waveform("w", None, 4, 1000.0));
    assert!(!source.has_counter() && source.counter().is_empty());
    assert_eq!(source.rows_per_packet().unwrap(), 1);
    assert_eq!(source.sample_index().unwrap(), [0, 1, 2, 3]);
    assert_eq!(source.filled_mask().unwrap(), [false; 4]);
    assert_eq!(source.channel_sampling_frequency().unwrap().0, 1000.0);
    assert_eq!(source.total_sampling_frequency().unwrap(), (1000.0, icoschema::v1::model::FrequencySource::Hardware));
    // no rows at all is still an error
    let empty = Source::from(base("e", None, 0));
    assert!(empty.rows_per_packet().unwrap_err().to_string().contains("empty counter"));
}

#[test]
fn signal_loss_comes_from_the_quality_channel() {
    let mut source = waveform("w", None, 4, 1000.0);
    let loss = |s: &g::Source| (Source::from(s.clone()).signal_loss_percentage(), Source::from(s.clone()).signal_loss_measured());
    assert_eq!(loss(&source), (5.0, true)); // 100 - mean(100, 90)
    source.quality.as_mut().unwrap().values = vec![f64::NAN, 80.0, f64::INFINITY];
    assert_eq!(loss(&source), (20.0, true)); // non-finite values do not count
    source.quality.as_mut().unwrap().values = vec![150.0];
    assert_eq!(loss(&source), (0.0, true)); // clipped to 0..100
    source.quality.as_mut().unwrap().values = vec![f64::NAN];
    assert_eq!(loss(&source), (0.0, false)); // nothing usable: an assumed 0
    source.quality = None;
    assert_eq!(loss(&source), (0.0, false));
    // a packet source measures it from the counter
    assert!(Source::from(packet("p", None, 5)).signal_loss_measured());
}

#[test]
fn files_saved_with_the_old_tdms_json_still_report_rate_and_loss() {
    let mut source = packet("source1", None, 4);
    source.recording_metadata.post_metadata = Some(
        "{\"tdms\": {\"sampling_frequency\": 5000.0, \"signal_loss_percentage\": 2.5, \"signal_loss_measured\": true}, \"x\": 1}".into(),
    );
    let source = Source::from(source);
    assert_eq!(source.channel_sampling_frequency().unwrap(), (5000.0, icoschema::v1::model::FrequencySource::Hardware));
    assert_eq!((source.signal_loss_percentage(), source.signal_loss_measured()), (2.5, true));
    let mut plain = packet("source1", None, 4);
    plain.recording_metadata.post_metadata = Some("not json".into());
    assert_eq!(Source::from(plain).signal_loss_percentage(), 0.0); // counter without gaps
}

// ── writing and reading back ─────────────────────────────────────────────────

#[test]
fn several_sources_keep_their_order_and_are_written_as_1_3() {
    let mut zeta = packet("zeta", Some("2026-01-01T00:00:00"), 30);
    zeta.stu_id = Some("STU1".into());
    zeta.sth_id = Some("STH1".into());
    let bundle = DatasetBundle::new(recording(vec![zeta, packet("alpha", Some("2026-01-01T00:00:02.500000"), 20)]))
        .with_preprocessed(table("alpha", 20, 1), None)
        .unwrap();
    let target = temp("multi.h5");
    bundle.to_hdf5(path(&target)).unwrap();
    assert_eq!(version(&target), "1.3");

    let back = DatasetBundle::from_hdf5(path(&target)).unwrap();
    assert_eq!(back.recording.source_names(), ["zeta", "alpha"]);
    let zeta = back.recording.source("zeta").unwrap();
    assert_eq!((zeta.stu_id.as_deref(), zeta.sth_id.as_deref()), (Some("STU1"), Some("STH1")));
    assert_eq!(back.recording.source("alpha").unwrap().timestamps().len(), 20);
    assert_eq!(back.preprocessed_tables.len(), 1);
    assert_eq!(back.preprocessed_for("alpha").unwrap().unwrap().len(), 20);
    assert!(back.preprocessed_for("zeta").unwrap().is_none());
    assert!(back.preprocessed().unwrap_err().to_string().contains("use preprocessed_for"));
    assert!(back.preprocessed_for("nope").is_err());
    assert_eq!(back.recording.start_offsets().unwrap(), [("zeta", 0.0), ("alpha", 2.5)]);
}

#[test]
fn waveform_sources_are_written_as_1_4_with_their_name_and_no_counter() {
    let mut plain = DatasetBundle::new(recording(vec![waveform("source1", Some("2026-01-01T00:00:00"), 50, 2000.0)]));
    plain.provenance = Some(g::Provenance {
        source_format: Some("tdms".into()),
        source_format_version: Some("legacy".into()),
        reader: Some("icoschema 0.3.0".into()),
        writer: None,
    });
    let target = temp("waveform.h5");
    plain.to_hdf5(path(&target)).unwrap();
    assert_eq!(version(&target), "1.4");

    let file = rust_hdf5::H5File::open(&target).unwrap();
    assert_eq!(file.dataset("recording").unwrap().attr("source_name").unwrap().read_string().unwrap(), "source1");
    assert!(file.dataset("quality").is_ok());
    assert!(file.attr("writer").unwrap().read_string().unwrap().starts_with("icoschema-rust"));

    let back = DatasetBundle::from_hdf5(path(&target)).unwrap();
    let source = back.recording.only_source().unwrap();
    assert!(!source.has_counter());
    assert_eq!(source.sampling_frequency, Some(2000.0));
    assert_eq!(source.quality.as_ref().unwrap().values, [100.0, 90.0]);
    assert_eq!(source.quality.as_ref().unwrap().sampling_frequency, Some(10.0));
    assert_eq!(source.additional_data.as_deref(), Some("{\"file\": {\"name\": \"t\"}}"));
    // where the data came from survives the round trip; the writer is this file's
    let provenance = back.provenance.unwrap();
    assert_eq!(
        (provenance.source_format.as_deref(), provenance.source_format_version.as_deref(), provenance.reader.as_deref()),
        (Some("tdms"), Some("legacy"), Some("icoschema 0.3.0"))
    );
    assert!(provenance.writer.unwrap().starts_with("icoschema-rust"));
}

#[test]
fn waveform_and_packet_sources_share_a_1_4_file_with_steps_and_tables() {
    let bundle = DatasetBundle::new(recording(vec![waveform("w", Some("2026-01-01T00:00:00"), 40, 10.0), packet("p", None, 25)]))
        .with_preprocessed(table("w", 40, 1), None)
        .unwrap()
        .with_computation("rms/channel1", result("rms/channel1"))
        .with_step(step("rms", Some("preprocessed:w"), &[], &["rms/channel1"]))
        .unwrap();
    let target = temp("mixed.h5");
    bundle.to_hdf5(path(&target)).unwrap();
    assert_eq!(version(&target), "1.4");
    let back = DatasetBundle::from_hdf5(path(&target)).unwrap();
    assert_eq!(back.recording.source_names(), ["w", "p"]);
    assert!(back.recording.source("p").unwrap().has_counter());
    assert_eq!(back.preprocessed_for("w").unwrap().unwrap().len(), 40);
    assert_eq!(back.steps[0].source_node.as_deref(), Some("preprocessed:w"));
    assert_eq!(back.computations_for_source("w").unwrap().len(), 1);
}

#[test]
fn a_plain_packet_recording_keeps_its_old_version_and_layout() {
    let target = temp("plain.h5");
    DatasetBundle::new(recording(vec![packet("source1", Some("2026-01-01T00:00:00"), 10)])).to_hdf5(path(&target)).unwrap();
    assert_eq!(version(&target), "1.0");
    let file = rust_hdf5::H5File::open(&target).unwrap();
    assert!(file.dataset("recording").unwrap().attr("source_name").is_err()); // the default name is not stored before 1.4
    assert!(file.attr("source_format").is_err()); // nothing is claimed about an in-memory bundle's origin
    assert!(file.attr("writer").is_ok());
}

#[test]
fn files_read_without_provenance_attributes_are_hdf5_of_their_version() {
    let provenance = load("multi_source.h5").unwrap().provenance.unwrap();
    assert_eq!(provenance.source_format.as_deref(), Some("hdf5"));
    assert_eq!(provenance.source_format_version.as_deref(), Some("1.3"));
    assert!(provenance.reader.unwrap().starts_with("icoschema-rust"));
    assert!(provenance.writer.unwrap().starts_with("icoschema")); // Python wrote it
    let legacy = load("legacy.h5").unwrap().provenance.unwrap();
    assert_eq!(legacy.source_format_version.as_deref(), Some("legacy"));
    assert_eq!(legacy.writer, None);
}

#[test]
fn a_writer_refuses_duplicate_or_unusable_source_names() {
    // the recording type cannot be built with them, but the generated one can
    let sources = vec![packet("a", None, 3), packet("a", None, 3)];
    let result = icoschema::v1::storage::write::save(
        icoschema::v1::storage::write::Parts {
            sources: sources.iter().collect(),
            preprocessed: vec![],
            computations: &Default::default(),
            steps: &[],
            provenance: None,
        },
        path(&temp("dup.h5")),
    );
    assert!(result.unwrap_err().to_string().contains("duplicate source name"));
}

// ── the bundle ───────────────────────────────────────────────────────────────

#[test]
fn a_preprocessed_table_needs_a_source_when_there_are_several() {
    let bundle = DatasetBundle::new(recording(vec![packet("a", None, 10), packet("b", None, 10)]));
    let mut anonymous = table("a", 10, 1);
    anonymous.source = None;
    let error = bundle.clone().with_preprocessed(anonymous.clone(), None).unwrap_err().to_string();
    assert!(error.contains("say which one"), "{error}");
    let with = bundle.clone().with_preprocessed(anonymous.clone(), Some("b")).unwrap();
    assert_eq!(with.preprocessed_tables[0].source.as_deref(), Some("b"));
    assert!(bundle.clone().with_preprocessed(table("a", 10, 1), Some("b")).unwrap_err().to_string().contains("not \"b\""));
    assert!(bundle.clone().with_preprocessed(table("zzz", 10, 1), None).unwrap_err().to_string().contains("no such source"));

    // tables stay in source order whichever was added first, and a table replaces that source's
    let both = bundle
        .clone()
        .with_preprocessed(table("b", 10, 1), None)
        .unwrap()
        .with_preprocessed(table("a", 10, 1), None)
        .unwrap()
        .with_preprocessed(table("b", 10, 1), None)
        .unwrap();
    assert_eq!(both.preprocessed_tables.iter().map(|t| t.source.clone().unwrap()).collect::<Vec<_>>(), ["a", "b"]);
    assert!(both.clone().without_preprocessed(Some("c")).is_err());
    assert_eq!(both.clone().without_preprocessed(Some("a")).unwrap().preprocessed_tables.len(), 1);
    assert!(bundle.without_preprocessed(Some("a")).unwrap_err().to_string().contains("no preprocessed table"));
}

#[test]
fn steps_are_traced_back_to_their_source() {
    let mut bundle = DatasetBundle::new(recording(vec![packet("a", None, 10), packet("b", None, 10)]))
        .with_preprocessed(table("b", 10, 1), None)
        .unwrap();
    for key in ["ra/x", "rb/x", "mix/x", "again/x", "free/x"] {
        bundle = bundle.with_computation(key, result(key));
    }
    let bundle = bundle
        .with_step(step("ra", Some("a"), &[], &["ra/x"]))
        .unwrap()
        .with_step(step("rb", Some("preprocessed:b"), &[], &["rb/x"]))
        .unwrap()
        .with_step(step("mix", None, &["ra", "rb"], &["mix/x"]))
        .unwrap()
        .with_step(step("again", Some("ra"), &[], &["again/x"]))
        .unwrap()
        .with_step(step("free", None, &[], &["free/x"]))
        .unwrap();
    let of = |node: &str| bundle.source_of(node).unwrap();
    assert_eq!(of("a").as_deref(), Some("a"));
    assert_eq!(of("preprocessed:b").as_deref(), Some("b"));
    assert_eq!(of("ra").as_deref(), Some("a"));
    assert_eq!(of("rb").as_deref(), Some("b"));
    assert_eq!(of("again").as_deref(), Some("a")); // through another step
    assert_eq!(of("mix"), None); // inputs from two sources
    assert_eq!(of("free"), None); // no source_node, no inputs, several sources
    assert!(bundle.source_of("preprocessed").unwrap_err().to_string().contains("ambiguous"));
    assert!(bundle.source_of("preprocessed:zzz").unwrap_err().to_string().contains("unknown source"));
    assert!(bundle.source_of("nobody").unwrap_err().to_string().contains("not a source"));

    let mut for_a: Vec<_> = bundle.computations_for_source("a").unwrap().into_keys().collect();
    for_a.sort();
    assert_eq!(for_a, ["again/x", "ra/x"]);
    assert!(bundle.computations_for_source("zzz").is_err());

    // a single source needs no name
    let single = DatasetBundle::new(recording(vec![packet("only", None, 5)]));
    assert_eq!(single.source_of("preprocessed").unwrap().as_deref(), Some("only"));
}

#[test]
fn step_names_may_not_take_a_source_name_or_read_an_unknown_source() {
    let bundle = DatasetBundle::new(recording(vec![packet("a", None, 5), packet("b", None, 5)]));
    let refused = |s: g::ComputationStep| bundle.clone().with_step(s).unwrap_err().to_string();
    assert!(refused(step("a", None, &[], &[])).contains("reserved"));
    assert!(refused(step("preprocessed", None, &[], &[])).contains("reserved"));
    assert!(refused(step("preprocessed:a", None, &[], &[])).contains("reserved"));
    assert!(refused(step("s", Some("preprocessed:zzz"), &[], &[])).contains("no such source"));
    // a step name may be anything else, and a source_node need not name a recorded step
    assert!(bundle.with_step(step("s", Some("failed_earlier"), &[], &[])).is_ok());
}

#[test]
fn replacing_the_recording_keeps_the_provenance() {
    let mut bundle = DatasetBundle::new(recording(vec![packet("a", None, 5)]));
    bundle.provenance = Some(g::Provenance { source_format: Some("hdf5".into()), source_format_version: None, reader: None, writer: None });
    let replaced = bundle.with_recording(recording(vec![packet("b", None, 5)])).unwrap();
    assert_eq!(replaced.provenance.unwrap().source_format.as_deref(), Some("hdf5"));
}

// ── from_file ────────────────────────────────────────────────────────────────

#[test]
fn from_file_tells_the_formats_apart_by_content_not_name() {
    let hdf5 = fixtures().join("multi_source.h5");
    assert_eq!(DatasetBundle::from_file(path(&hdf5)).unwrap().recording.sources().len(), 2);
    let renamed = temp("no-extension");
    std::fs::copy(&hdf5, &renamed).unwrap();
    assert!(DatasetBundle::from_file(path(&renamed)).is_ok());

    // an HDF5 file with a user block has its signature further in
    let with_user_block = fixtures().join("bundle_full_userblock.h5");
    assert!(DatasetBundle::from_file(path(&with_user_block)).is_ok());

    let tdms = temp("data.tdms");
    std::fs::write(&tdms, b"TDSm\x69\x12\x00\x00rest").unwrap();
    // recognised as TDMS by its first bytes, then refused as the broken file it is
    assert!(DatasetBundle::from_file(path(&tdms)).is_err());
    #[cfg(feature = "tdms")]
    {
        let real_tdms = fixtures().join("tdms/two_stus.tdms");
        assert_eq!(DatasetBundle::from_file(path(&real_tdms)).unwrap().recording.sources().len(), 2);
    }
    let junk = temp("junk.hdf5");
    std::fs::write(&junk, b"not a recording").unwrap();
    assert!(DatasetBundle::from_file(path(&junk)).unwrap_err().to_string().contains("neither an HDF5 nor a TDMS"));
    assert!(DatasetBundle::from_file(path(&temp("missing.h5"))).is_err());
}
