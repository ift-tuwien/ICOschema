//! The Rust reader against what the Python icoschema reads from the same files
//! (`tests/gen_fixtures.py` builds the fixtures and `expected.json`).

mod common;

use common::{check_bundle, expected, fixtures, load};
use icoschema::v1::DatasetBundle;
use serde_json::Value;

fn check(name: &str, want: &Value) {
    let loaded = load(name);
    if let Some(error) = want.get("load_error") {
        assert!(loaded.is_err(), "{name}: Rust loaded a file Python rejects ({error})");
        return;
    }
    check_bundle(name, &loaded.unwrap_or_else(|e| panic!("{name}: {e}")), want);
}

macro_rules! fixture_tests {
    ($($test:ident => $file:literal),* $(,)?) => {$(
        #[test]
        fn $test() { check($file, &expected("expected.json")[$file]); }
    )*};
}

fixture_tests! {
    bundle_full => "bundle_full.h5",
    bundle_full_newest_format => "bundle_full_latest.h5",
    bundle_full_user_block => "bundle_full_userblock.h5",
    bundle_full_user_block_newest_format => "bundle_full_userblock_latest.h5",
    one_channel_linear_uncompressed => "one_channel_linear.h5",
    two_channels_adc => "two_channels_adc.h5",
    legacy_layout => "legacy.h5",
    python_repo_test_file => "python_repo_with_sensors.h5",
    no_sensor_table => "no_sensors.h5",
    incomplete_adc_settings => "adc_incomplete.h5",
    inconsistent_rows_per_packet => "inconsistent_rows.h5",
    rejects_unknown_version => "err_version.h5",
    rejects_sensor_count_mismatch => "err_sensor_count.h5",
    rejects_missing_start_time => "err_no_start_time.h5",
    rejects_four_channels => "err_four_channels.h5",
    rejects_unconverted_without_sensors => "err_unconverted_no_sensors.h5",
    several_sources_with_steps_and_a_preprocessed_table => "multi_source.h5",
    waveform_source_without_counter => "waveform_single.h5",
    waveform_and_packet_sources_in_one_file => "waveform_multi.h5",
    tdms_json_in_post_metadata_of_an_old_file => "legacy_tdms_json.h5",
    rejects_duplicate_source_names => "err_duplicate_sources.h5",
    rejects_a_listed_source_without_group => "err_missing_source_group.h5",
}

#[test]
fn every_fixture_has_a_test() {
    let tested = 22;
    // schema version 2 fixtures, tested in tests/features.rs (they have no expected values from Python here)
    let elsewhere = ["malformed_computation.h5"];
    let files = std::fs::read_dir(fixtures())
        .unwrap()
        .map(|e| e.unwrap().path())
        .filter(|path| path.extension().is_some_and(|x| x == "h5"))
        .filter(|path| !elsewhere.contains(&path.file_name().unwrap().to_str().unwrap()))
        .count();
    assert_eq!(files, tested);
}

/// Truncated and randomly corrupted files must come back as errors (or load), never panic or
/// try to allocate terabytes. Deterministic: a fixed-seed generator picks the damage.
#[test]
fn corrupt_files_never_panic() {
    let dir = std::env::temp_dir().join(format!("icoschema-corrupt-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let mut state = 0x2545F4914F6CDD1Du64;
    let mut next = move || {
        state ^= state << 13;
        state ^= state >> 7;
        state ^= state << 17;
        state
    };
    for name in ["bundle_full.h5", "bundle_full_latest.h5", "bundle_full_userblock.h5", "legacy.h5"] {
        let original = std::fs::read(fixtures().join(name)).unwrap();
        for round in 0..60 {
            let mut data = original.clone();
            if round % 6 == 0 {
                data.truncate((next() as usize) % data.len());
            } else {
                for _ in 0..[1, 3, 10, 40][round % 4] {
                    let at = (next() as usize) % data.len();
                    data[at] = next() as u8;
                }
            }
            let path = dir.join(format!("{name}-{round}.h5"));
            std::fs::write(&path, &data).unwrap();
            let result = std::panic::catch_unwind(|| DatasetBundle::from_hdf5(path.to_str().unwrap()).map(|_| ()));
            assert!(result.is_ok(), "{name} round {round}: panicked");
        }
    }
    std::fs::remove_dir_all(&dir).ok();
}
