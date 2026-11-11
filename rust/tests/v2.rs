//! Schema version 2: the stored synthetic files of the Python package (`test/v2/data`), each 10 seconds of sine
//! waves, are read and checked against what `test/v2/synthetic_files.py` puts in them, written again by the
//! Rust writer and read back, and the refusals of other schema versions.

use std::path::PathBuf;

use icoschema::v2::schema as g;
use icoschema::v2::DatasetBundle;

const ROWS: usize = 10_000;
const FS: f64 = 1000.0;

fn data(name: &str) -> String {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../test/v2/data").join(name).to_str().unwrap().to_string()
}

fn v1_data(name: &str) -> String {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../test/v1/data").join(name).to_str().unwrap().to_string()
}

fn temporary(name: &str) -> String {
    let dir = std::env::temp_dir().join(format!("icoschema-rust-v2-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join(name).to_str().unwrap().to_string()
}

/// Amplitude `channel`, frequency `5 * channel * (source + 1)` Hz, as float32 (what the files store).
fn signal(channel: usize, source: usize) -> Vec<f64> {
    (0..ROWS)
        .map(|i| {
            let t = i as f64 / FS;
            let wave = channel as f64 * (2.0 * std::f64::consts::PI * 5.0 * (channel * (source + 1)) as f64 * t).sin();
            f64::from(wave as f32)
        })
        .collect()
}

fn assert_signal(got: &[f64], channel: usize, source: usize) {
    let want = signal(channel, source);
    assert_eq!(got.len(), want.len());
    for (i, (g, w)) in got.iter().zip(&want).enumerate() {
        assert!((g - w).abs() < 1e-5, "channel {channel} sample {i}: {g} != {w}");
    }
}

/// `(kind, gain, offset)` the synthetic files give each channel.
fn expected_conversion(channel: usize) -> (&'static str, f64, f64) {
    match channel {
        1 => ("linear", 2.0, -10.0),
        2 => ("none", 1.0, 0.0),
        _ => ("linear", 0.5, 0.25),
    }
}

fn conversion(metadata: &g::ChannelMetadata) -> (&'static str, f64, f64) {
    match &metadata.conversion {
        g::ConversionOrSubtype::NoConversion(_) => ("none", 1.0, 0.0),
        g::ConversionOrSubtype::LinearConversion(l) => ("linear", l.gain, l.offset),
    }
}

fn channel_metadata(hardware: &g::HardwareMetadata, channel: usize) -> &g::ChannelMetadata {
    match channel {
        1 => Some(&hardware.channel1_metadata),
        2 => hardware.channel2_metadata.as_ref(),
        _ => hardware.channel3_metadata.as_ref(),
    }
    .unwrap_or_else(|| panic!("no metadata for channel {channel}"))
}

fn channel_data(data: &g::RecordingData, channel: usize) -> &[f64] {
    match channel {
        1 => &data.channel1,
        2 => data.channel2.as_deref().unwrap(),
        _ => data.channel3.as_deref().unwrap(),
    }
}

fn check_channels(source: &g::Source, channels: usize, which: usize) {
    for channel in 1..=channels {
        let metadata = channel_metadata(&source.hardware_metadata, channel);
        assert_eq!(conversion(metadata), expected_conversion(channel), "channel {channel} conversion");
        let sensor = &metadata.sensor;
        assert_eq!(sensor.name.as_deref(), Some(format!("Sensor {channel}").as_str()));
        assert_eq!(sensor.sensor_id.as_deref(), Some(format!("s{channel}").as_str()));
        assert_eq!(sensor.sensor_type.as_deref(), Some("SYNTH"));
        assert_eq!(sensor.dimension.as_deref(), Some("Acceleration"));
        assert_eq!(sensor.unit.as_deref(), Some("g"));
        assert_signal(channel_data(&source.recording_data, channel), channel, which);
    }
    assert_eq!(source.recording_data.channel2.is_some(), channels >= 2);
    assert_eq!(source.hardware_metadata.channel3_metadata.is_some(), channels >= 3);
}

fn assert_timestamps(source: &g::Source) {
    let want: Vec<isize> = (0..ROWS as isize).map(|i| i * 1000).collect();
    assert_eq!(source.recording_data.timestamp, want);
}

#[test]
fn a_packet_source_with_everything_a_file_can_have() {
    for channels in [1, 3] {
        let bundle = DatasetBundle::from_hdf5(&data(&format!("hdf5_2.0_{channels}ch.hdf5"))).unwrap();
        let sources = bundle.recording.sources();
        assert_eq!(sources.len(), 1);
        let source: &g::Source = &sources[0];
        assert_eq!(source.name, "source1");
        assert_eq!(source.description.as_deref(), Some("Synthetic sine waves"));
        assert_eq!(source.stu_mac.as_deref(), Some("08-6B-D7-0F-47-2C"));
        assert_eq!(source.sth_mac.as_deref(), Some("14-2D-41-D7-77-7D"));
        assert_eq!(source.recording_metadata.start_time.as_deref(), Some("2026-03-04T05:06:07"));
        assert_eq!(source.hardware_metadata.adc_reference_voltage.as_deref(), Some("3.3"));
        let counter: Vec<isize> = (0..ROWS as isize).map(|i| i % 256).collect();
        assert_eq!(source.recording_data.counter.as_deref(), Some(counter.as_slice()));
        assert_timestamps(source);
        check_channels(source, channels, 0);
        assert!(source.quality.is_none() && source.sampling_frequency.is_none());

        // the preprocessed table, the step and the computation
        assert_eq!(bundle.preprocessed_tables.len(), 1);
        let table = &bundle.preprocessed_tables[0];
        assert_eq!(table.source.as_deref(), Some("source1"));
        assert_eq!(table.channel_sampling_frequency, FS);
        assert!(matches!(table.sampling_frequency_source, g::SamplingFrequencySource::Hardware));
        assert_eq!((table.fill_method.as_str(), table.producer.as_str()), ("linear", "synthetic"));
        assert_signal(&table.channel1, 1, 0);
        assert_eq!(bundle.steps.len(), 1);
        let step = &bundle.steps[0];
        assert_eq!((step.node.as_str(), step.step_index, step.producer.as_str()), ("rms", 0, "synthetic"));
        assert_eq!(step.inputs.as_deref(), Some(["recording".to_string()].as_slice()));
        assert_eq!(step.output_keys.as_deref(), Some(["rms/ch1".to_string()].as_slice()));
        let derived = bundle.computation("rms/ch1").unwrap();
        assert_eq!((derived.values.as_slice(), derived.unit.as_deref()), ([1.5, 2.5].as_slice(), Some("g")));

        let provenance = bundle.provenance.as_ref().unwrap();
        assert_eq!(provenance.source_format.as_deref(), Some("hdf5"));
        assert_eq!(provenance.source_format_version.as_deref(), Some("2.0"));
    }
}

#[test]
fn a_waveform_source_has_no_counter_but_its_own_rate_and_quality() {
    for channels in [1, 3] {
        let bundle = DatasetBundle::from_hdf5(&data(&format!("hdf5_2.0_{channels}ch_waveform.hdf5"))).unwrap();
        let source: &g::Source = &bundle.recording.sources()[0];
        assert_eq!(source.name, "tdms-like");
        assert!(source.recording_data.counter.is_none());
        assert_eq!(source.sampling_frequency, Some(FS));
        assert_eq!(source.additional_data.as_deref(), Some(r#"{"file": "x.tdms"}"#));
        let quality = source.quality.as_ref().unwrap();
        assert_eq!(quality.sampling_frequency, Some(10.0));
        let want: Vec<f64> = (0..100).map(|i| if i % 5 == 0 { 90.0 } else { 100.0 }).collect();
        assert_eq!(quality.values, want);
        assert_timestamps(source);
        check_channels(source, channels, 0);
        assert!(bundle.preprocessed_tables.is_empty() && bundle.steps.is_empty());
    }
}

#[test]
fn a_file_of_several_sources() {
    for channels in [1, 3] {
        let bundle = DatasetBundle::from_hdf5(&data(&format!("hdf5_2.0_{channels}ch_multi.hdf5"))).unwrap();
        assert_eq!(bundle.recording.source_names(), ["stu1", "stu2"]);
        let sources = bundle.recording.sources();
        let (first, second): (&g::Source, &g::Source) = (&sources[0], &sources[1]);
        assert_eq!(first.stu_mac.as_deref(), Some("08-6B-D7-0F-47-2C"));
        assert_eq!(second.stu_mac, None);
        assert_eq!(first.recording_metadata.start_time.as_deref(), Some("2026-03-04T05:06:07"));
        assert_eq!(second.recording_metadata.start_time.as_deref(), Some("2026-03-04T05:06:08"));
        assert!(first.recording_data.counter.is_some() && second.recording_data.counter.is_none());
        assert!(first.quality.is_none() && second.quality.is_some());
        check_channels(first, channels, 0);
        check_channels(second, channels, 1);
        // only the first source has a preprocessed table; steps and computations are of the file
        assert_eq!(bundle.preprocessed_tables.len(), 1);
        assert_eq!(bundle.preprocessed_tables[0].source.as_deref(), Some("stu1"));
        assert_eq!(bundle.steps.len(), 1);
        assert!(bundle.computation("rms/ch1").is_some());
    }
}

#[test]
fn every_stored_file_survives_a_write_by_rust() {
    for kind in ["", "_waveform", "_multi"] {
        for channels in [1, 3] {
            let name = format!("hdf5_2.0_{channels}ch{kind}.hdf5");
            let bundle = DatasetBundle::from_hdf5(&data(&name)).unwrap();
            let target = temporary(&name);
            bundle.to_hdf5(&target).unwrap();
            let again = DatasetBundle::from_hdf5(&target).unwrap();
            assert_eq!(bundle.recording.source_names(), again.recording.source_names(), "{name}");
            for (a, b) in bundle.recording.sources().iter().zip(again.recording.sources()) {
                // the writer stores float32 and the reader returns what was stored: equal after the first read
                assert_eq!(**a, **b, "{name}");
            }
            assert_eq!(bundle.steps, again.steps, "{name}");
            assert_eq!(bundle.computations, again.computations, "{name}");
            assert_eq!(
                bundle.preprocessed_tables.iter().map(|t| (**t).clone()).collect::<Vec<_>>(),
                again.preprocessed_tables.iter().map(|t| (**t).clone()).collect::<Vec<_>>(),
                "{name}"
            );
            let version = again.provenance.unwrap();
            assert_eq!(version.source_format_version.as_deref(), Some("2.0"));
            std::fs::remove_file(target).unwrap();
        }
    }
}

#[test]
fn a_conversion_without_parameters_is_stored_as_none_and_read_back() {
    let bundle = DatasetBundle::from_hdf5(&data("hdf5_2.0_3ch.hdf5")).unwrap();
    let target = temporary("conversions.hdf5");
    bundle.to_hdf5(&target).unwrap();
    let again = DatasetBundle::from_hdf5(&target).unwrap();
    let source: &g::Source = &again.recording.sources()[0];
    let kinds: Vec<_> = (1..=3).map(|c| conversion(channel_metadata(&source.hardware_metadata, c))).collect();
    assert_eq!(kinds, [("linear", 2.0, -10.0), ("none", 1.0, 0.0), ("linear", 0.5, 0.25)]);
    std::fs::remove_file(target).unwrap();
}

// ── other schema versions are refused, with the way to read them ────────────

#[test]
fn a_file_of_schema_version_one_is_refused_with_a_pointer_to_v1() {
    for name in ["hdf5_1.0_1ch.hdf5", "hdf5_1.4_3ch_multi.hdf5"] {
        let error = DatasetBundle::from_hdf5(&v1_data(name)).unwrap_err().to_string();
        assert!(error.contains("schema version 1"), "{name}: {error}");
        assert!(error.contains("icoschema::v1"), "{name}: {error}");
    }
}

#[test]
fn an_unversioned_file_is_schema_version_one() {
    let error = DatasetBundle::from_hdf5(&v1_data("hdf5_legacy_1ch.hdf5")).unwrap_err().to_string();
    assert!(error.contains("no icoschema_format_version") && error.contains("icoschema::v1"), "{error}");
}

#[cfg(feature = "tdms")]
#[test]
fn a_tdms_channel_is_an_identity_linear_conversion_and_the_group_is_not_a_mac() {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../test/v2/data/tdms_legacy_3ch_multi.tdms");
    let bundle = DatasetBundle::from_tdms(path.to_str().unwrap()).unwrap();
    assert!(bundle.recording.sources().len() > 1);
    for source in bundle.recording.sources() {
        let source: &g::Source = source;
        assert!(source.stu_mac.is_none() && source.sth_mac.is_none() && source.description.is_none());
        for channel in 1..=3 {
            assert_eq!(conversion(channel_metadata(&source.hardware_metadata, channel)), ("linear", 1.0, 0.0));
        }
    }
}
