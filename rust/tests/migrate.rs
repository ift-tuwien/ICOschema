//! The v1 -> v2 migration and `icoschema::read`: every channel becomes a `LinearConversion`, whatever v1 said.

use std::collections::HashMap;
use std::path::PathBuf;

use icoschema::migrate::{self, Scaling};
use icoschema::v1;
use icoschema::v1::schema as g1;
use icoschema::v2;
use icoschema::v2::schema as g2;

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("..")
}

fn v1_data(name: &str) -> String {
    root().join("test/v1/data").join(name).to_str().unwrap().to_string()
}

fn v2_data(name: &str) -> String {
    root().join("test/v2/data").join(name).to_str().unwrap().to_string()
}

/// The real acquisition file: `conversion = "true"` and a sensors row with scaling 75.757576 / -125.
fn real_file() -> String {
    root().join("test/v1/test_with_sensors.hdf5").to_str().unwrap().to_string()
}

fn temporary(name: &str) -> String {
    let dir = std::env::temp_dir().join(format!("icoschema-rust-migrate-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    dir.join(name).to_str().unwrap().to_string()
}

fn sensor(changes: impl FnOnce(&mut g1::Sensor)) -> g1::Sensor {
    let mut sensor = g1::Sensor {
        sensor_id: Some("s1".into()),
        sensor_type: None,
        name: None,
        unit: Some("g".into()),
        dimension: None,
        phys_min: Some(-100.0),
        phys_max: Some(100.0),
        volt_min: Some(0.33),
        volt_max: Some(2.97),
    };
    changes(&mut sensor);
    sensor
}

fn channel(compensations: Vec<g1::CompensationOrSubtype>, sensor: g1::Sensor) -> g1::ChannelMetadata {
    g1::ChannelMetadata { sensor, compensations }
}

fn linear(order: isize, gain: f64, offset: f64) -> g1::CompensationOrSubtype {
    g1::CompensationOrSubtype::LinearConversion(g1::LinearConversion { order, gain, offset })
}

fn none() -> g1::CompensationOrSubtype {
    g1::CompensationOrSubtype::NoConversion(g1::NoConversion { order: 0 })
}

/// `(gain, offset)` and the warnings of the migration of a channel.
fn convert(
    compensations: Vec<g1::CompensationOrSubtype>,
    sensor: g1::Sensor,
    stored: Option<Scaling>,
) -> Result<(Scaling, Vec<String>), String> {
    // a v1 bundle of one source, one channel, from a real file with its channel replaced
    let bundle = v1::DatasetBundle::from_hdf5(&real_file()).unwrap();
    let mut inner: g1::Source = (**bundle.recording.only_source().unwrap()).clone();
    inner.hardware_metadata.channel1_metadata = channel(compensations, sensor);
    let name = inner.name.clone();
    let rebuilt = v1::DatasetBundle::new(v1::Recording::single(inner).unwrap());
    let stored: HashMap<String, Vec<Scaling>> = stored.map(|s| (name, vec![s])).into_iter().collect();
    match migrate::v1_to_v2_with_warnings(&rebuilt, &stored) {
        Ok((migrated, warnings)) => {
            let source: &g2::Source = migrated.recording.only_source().unwrap();
            match &source.hardware_metadata.channel1_metadata.conversion {
                g2::ConversionOrSubtype::LinearConversion(l) => Ok(((l.gain, l.offset), warnings)),
                other => panic!("not a LinearConversion: {other:?}"),
            }
        }
        Err(error) => Err(error.to_string()),
    }
}

#[test]
fn the_range_gives_gain_and_offset_as_delta_phys_over_delta_volt() {
    let (gain, offset) = migrate::linear_from_range(&sensor(|_| {})).unwrap();
    assert!((gain - 200.0 / 2.64).abs() < 1e-9);
    assert!((gain * 0.33 + offset + 100.0).abs() < 1e-9);
    assert!((gain * 2.97 + offset - 100.0).abs() < 1e-9);
}

#[test]
fn an_incomplete_or_empty_range_gives_no_conversion() {
    for strip in [
        (|s: &mut g1::Sensor| s.phys_min = None) as fn(&mut g1::Sensor),
        |s| s.phys_max = None,
        |s| s.volt_min = None,
        |s| s.volt_max = None,
    ] {
        let error = migrate::linear_from_range(&sensor(strip)).unwrap_err().to_string();
        assert!(error.contains("no complete phys/volt range"), "{error}");
    }
    let error = migrate::linear_from_range(&sensor(|s| s.volt_max = s.volt_min)).unwrap_err().to_string();
    assert!(error.contains("volt_min == volt_max"), "{error}");
}

#[test]
fn the_stored_scaling_wins_over_everything() {
    let ((gain, offset), _) = convert(vec![linear(0, 2.0, 3.0)], sensor(|_| {}), Some((5.0, 6.0))).unwrap();
    assert_eq!((gain, offset), (5.0, 6.0));
    // also for a channel v1 called NoConversion (the file said "already converted")
    let ((gain, offset), _) = convert(vec![none()], sensor(|_| {}), Some((5.0, 6.0))).unwrap();
    assert_eq!((gain, offset), (5.0, 6.0));
}

#[test]
fn a_linear_conversion_without_stored_scaling_is_kept() {
    let (scaling, _) = convert(vec![linear(0, 2.0, 3.0)], sensor(|s| s.phys_min = None), None).unwrap();
    assert_eq!(scaling, (2.0, 3.0));
}

#[test]
fn no_conversion_without_stored_scaling_takes_the_range_else_one_and_zero() {
    let (scaling, _) = convert(vec![none()], sensor(|_| {}), None).unwrap();
    assert_eq!(scaling, migrate::linear_from_range(&sensor(|_| {})).unwrap());
    let (scaling, _) = convert(vec![none()], sensor(|s| s.volt_max = None), None).unwrap();
    assert_eq!(scaling, (1.0, 0.0));
}

#[test]
fn a_stored_scaling_that_differs_from_the_range_is_kept_with_a_warning() {
    let (scaling, warnings) = convert(vec![none()], sensor(|_| {}), Some((2.0, 3.0))).unwrap();
    assert_eq!(scaling, (2.0, 3.0));
    assert!(warnings.iter().any(|w| w.contains("keeping the stored one")), "{warnings:?}");
    let derived = migrate::linear_from_range(&sensor(|_| {})).unwrap();
    let (_, warnings) = convert(vec![none()], sensor(|_| {}), Some(derived)).unwrap();
    assert!(warnings.is_empty(), "{warnings:?}");
}

#[test]
fn a_polynomial_of_degree_one_is_linear_and_others_cannot_be_migrated() {
    let polynomial = |coefficients: Vec<f64>| {
        g1::CompensationOrSubtype::PolynomialConversion(g1::PolynomialConversion { order: 0, coefficients })
    };
    let (scaling, _) = convert(vec![polynomial(vec![3.0, 2.0])], sensor(|s| s.phys_min = None), None).unwrap();
    assert_eq!(scaling, (2.0, 3.0));
    let error = convert(vec![polynomial(vec![1.0, 2.0, 3.0])], sensor(|_| {}), None).unwrap_err();
    assert!(error.contains("no v2 form"), "{error}");
    let frequency = g1::CompensationOrSubtype::FrequencyCompensation(g1::FrequencyCompensation { order: 0 });
    let error = convert(vec![frequency], sensor(|_| {}), None).unwrap_err();
    assert!(error.contains("no v2 form"), "{error}");
    let error = convert(vec![linear(0, 1.0, 0.0), linear(1, 2.0, 0.0)], sensor(|_| {}), None).unwrap_err();
    assert!(error.contains("cannot be migrated"), "{error}");
}

#[test]
fn the_schema_version_of_a_file() {
    assert_eq!(migrate::schema_version_of_file(&v1_data("hdf5_1.0_1ch.hdf5")).unwrap(), 1);
    assert_eq!(migrate::schema_version_of_file(&v1_data("hdf5_legacy_1ch.hdf5")).unwrap(), 1);
    assert_eq!(migrate::schema_version_of_file(&v1_data("tdms_legacy_1ch.tdms")).unwrap(), 1);
    assert_eq!(migrate::schema_version_of_file(&v2_data("hdf5_2.0_1ch.hdf5")).unwrap(), 2);
    let not_a_file = temporary("x.txt");
    std::fs::write(&not_a_file, "hello").unwrap();
    let error = migrate::schema_version_of_file(&not_a_file).unwrap_err().to_string();
    assert!(error.contains("neither an HDF5 nor a TDMS file"), "{error}");
}

#[test]
fn the_real_file_ignores_its_conversion_attribute_and_keeps_its_values() {
    let old = v1::DatasetBundle::from_hdf5(&real_file()).unwrap();
    let migrated = icoschema::read(&real_file()).unwrap();
    let source: &g2::Source = migrated.recording.only_source().unwrap();
    let g2::ConversionOrSubtype::LinearConversion(conversion) = &source.hardware_metadata.channel1_metadata.conversion
    else {
        panic!("not linear")
    };
    assert!((conversion.gain - 75.757576).abs() < 1e-5, "{}", conversion.gain);
    assert!((conversion.offset + 125.0).abs() < 1e-5, "{}", conversion.offset);
    let old_source: &g1::Source = old.recording.only_source().unwrap();
    assert_eq!(source.recording_data.channel1, old_source.recording_data.channel1);
    assert_eq!(source.recording_data.timestamp, old_source.recording_data.timestamp);
}

#[test]
fn read_opens_a_file_of_the_latest_version_as_it_is() {
    let path = v2_data("hdf5_2.0_3ch_multi.hdf5");
    let read: v2::DatasetBundle = icoschema::read(&path).unwrap();
    let direct = v2::DatasetBundle::from_hdf5(&path).unwrap();
    assert_eq!(read.recording.source_names(), direct.recording.source_names());
    assert_eq!(*read.recording.sources()[1], *direct.recording.sources()[1]);
}

#[test]
fn every_stored_v1_file_reads_as_the_latest_and_converts_to_a_readable_file() {
    let mut names: Vec<_> = std::fs::read_dir(root().join("test/v1/data"))
        .unwrap()
        .map(|e| e.unwrap().file_name().into_string().unwrap())
        .collect();
    names.sort();
    assert!(names.len() >= 18);
    for name in names {
        let path = v1_data(&name);
        let old = v1::DatasetBundle::from_file(&path).unwrap();
        let bundle = icoschema::read(&path).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(bundle.recording.source_names(), old.recording.source_names(), "{name}");
        for (new, old) in bundle.recording.sources().iter().zip(old.recording.sources()) {
            assert_eq!(new.recording_data.timestamp, old.recording_data.timestamp, "{name}");
            assert_eq!(new.recording_data.channel1, old.recording_data.channel1, "{name}");
            assert_eq!(new.stu_mac, old.stu_id, "{name}");
            assert_eq!(new.sth_mac, old.sth_id, "{name}");
        }
        assert_eq!(bundle.steps.len(), old.steps.len(), "{name}");
        assert_eq!(bundle.computations.len(), old.computations.len(), "{name}");

        let target = temporary(&format!("{name}.v2.hdf5"));
        migrate::convert_file(&path, &target).unwrap_or_else(|e| panic!("{name}: {e}"));
        assert_eq!(migrate::schema_version_of_file(&target).unwrap(), 2, "{name}");
        let converted = v2::DatasetBundle::from_hdf5(&target).unwrap();
        assert_eq!(converted.recording.source_names(), bundle.recording.source_names(), "{name}");
        std::fs::remove_file(target).unwrap();
    }
}

#[test]
fn the_stored_scalings_of_v1_files_become_the_conversions() {
    for name in ["hdf5_1.0_3ch.hdf5", "hdf5_1.4_3ch_multi.hdf5"] {
        let path = v1_data(name);
        let old = v1::DatasetBundle::from_hdf5(&path).unwrap();
        let single = old.recording.sources()[0].name().to_string();
        let stored = v1::storage::hdf5::stored_scalings(&path, &single).unwrap();
        assert!(!stored.is_empty(), "{name}");
        let migrated = icoschema::read(&path).unwrap();
        for source in migrated.recording.sources() {
            let scalings = &stored[source.name()];
            let metadata = [
                Some(&source.hardware_metadata.channel1_metadata),
                source.hardware_metadata.channel2_metadata.as_ref(),
                source.hardware_metadata.channel3_metadata.as_ref(),
            ];
            for (metadata, (gain, offset)) in metadata.into_iter().flatten().zip(scalings) {
                let g2::ConversionOrSubtype::LinearConversion(l) = &metadata.conversion else { panic!("{name}: not linear") };
                assert_eq!((l.gain, l.offset), (*gain, *offset), "{name}");
            }
        }
    }
}
