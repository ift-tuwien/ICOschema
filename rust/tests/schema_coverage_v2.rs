//! Fails when `dataset.yaml` has something the Rust port has not been taught about
//! (see `icoschema::v2::schema_support`). This is the check behind
//! "change the LinkML schema -> `just generate` -> the build / tests complain".

use std::collections::{BTreeMap, BTreeSet};
use std::path::PathBuf;

use icoschema::v2::schema_support::{CLASSES, ENUMS};
use serde_yml::Value;

fn schema_text() -> String {
    let path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../icoschema/v2/schema/dataset.yaml");
    // Checked out with CRLF line endings on Windows; the edits below assume LF.
    std::fs::read_to_string(path).unwrap().replace("\r\n", "\n")
}

fn keys(v: Option<&Value>) -> Vec<String> {
    v.and_then(Value::as_mapping)
        .map(|m| m.keys().filter_map(|k| k.as_str().map(str::to_string)).collect())
        .unwrap_or_default()
}

/// Every difference between the schema and the manifest, as readable sentences.
fn problems(schema_yaml: &str) -> Vec<String> {
    let schema: Value = serde_yml::from_str(schema_yaml).expect("dataset.yaml is not valid YAML");
    let classes = schema.get("classes");

    // Attributes of each class, with the ones inherited through `is_a`.
    let own: BTreeMap<String, Vec<String>> =
        keys(classes).into_iter().map(|c| (c.clone(), keys(classes.unwrap()[c.as_str()].get("attributes")))).collect();
    let parent = |c: &str| classes.unwrap()[c].get("is_a").and_then(Value::as_str).map(str::to_string);
    let all_attributes = |c: &str| {
        let mut out = BTreeSet::new();
        let mut at = Some(c.to_string());
        while let Some(name) = at {
            out.extend(own.get(&name).cloned().unwrap_or_default());
            at = parent(&name);
        }
        out
    };

    let mut problems = Vec::new();
    for class in own.keys() {
        match CLASSES.iter().find(|c| c.name == class) {
            None => problems.push(format!("class {class} is new: decide how storage and model handle it, then add it to CLASSES")),
            Some(known) => {
                let wanted = all_attributes(class);
                let handled: BTreeSet<String> = known.attributes.iter().map(|a| a.to_string()).collect();
                for new in wanted.difference(&handled) {
                    problems.push(format!("{class}.{new} is new: handle it in storage/hdf5.rs and model/, then add it to CLASSES"));
                }
                for gone in handled.difference(&wanted) {
                    problems.push(format!("{class}.{gone} is gone from the schema: remove it from CLASSES"));
                }
            }
        }
    }
    for known in CLASSES {
        if !own.contains_key(known.name) {
            problems.push(format!("class {} is gone from the schema: remove it from CLASSES", known.name));
        }
    }

    let enums = schema.get("enums");
    for name in keys(enums) {
        let values: BTreeSet<String> = keys(enums.unwrap()[name.as_str()].get("permissible_values")).into_iter().collect();
        match ENUMS.iter().find(|(n, _)| *n == name) {
            None => problems.push(format!("enum {name} is new: handle it in storage/hdf5.rs, then add it to ENUMS")),
            Some((_, known)) => {
                let handled: BTreeSet<String> = known.iter().map(|v| v.to_string()).collect();
                for new in values.difference(&handled) {
                    problems.push(format!("enum value {name}.{new} is new: handle it in storage/hdf5.rs, then add it to ENUMS"));
                }
                for gone in handled.difference(&values) {
                    problems.push(format!("enum value {name}.{gone} is gone from the schema: remove it from ENUMS"));
                }
            }
        }
    }
    for (name, _) in ENUMS {
        if !keys(enums).contains(&name.to_string()) {
            problems.push(format!("enum {name} is gone from the schema: remove it from ENUMS"));
        }
    }
    problems
}

#[test]
fn the_rust_port_handles_everything_in_the_schema() {
    let found = problems(&schema_text());
    assert!(
        found.is_empty(),
        "dataset.yaml and the Rust port disagree (see rust/src/v2/schema_support.rs):\n  - {}",
        found.join("\n  - ")
    );
}

// The check itself: each kind of schema edit must be noticed.

fn edited(from: &str, to: &str) -> String {
    let text = schema_text();
    assert!(text.contains(from), "test needs `{from}` in dataset.yaml");
    text.replacen(from, to, 1)
}

#[test]
fn notices_a_new_attribute() {
    let found = problems(&edited("      sensor_id:\n", "      serial_number:\n        range: string\n      sensor_id:\n"));
    assert_eq!(found, ["Sensor.serial_number is new: handle it in storage/hdf5.rs and model/, then add it to CLASSES"]);
}

#[test]
fn notices_an_attribute_inherited_by_subclasses() {
    // `conversion_type` lives on Conversion and reaches its subclasses: the manifest lists it on each.
    let found = problems(&edited(
        "    attributes:\n      conversion_type:\n",
        "    attributes:\n      label:\n        range: string\n      conversion_type:\n",
    ));
    assert_eq!(found.len(), 3, "{found:?}"); // Conversion, NoConversion, LinearConversion
}

#[test]
fn notices_a_new_class_and_a_new_subclass() {
    let found = problems(&format!("{}\n  Spline:\n    is_a: Conversion\n", schema_text().replace("\nenums:", "\n  Extra:\n    description: x\n\nenums:")));
    assert!(found.iter().any(|p| p.starts_with("class Extra is new")), "{found:?}");
    let found = problems(&schema_text().replace("\nenums:", "\n  Spline:\n    is_a: Conversion\n    attributes:\n      knots:\n        range: float\n\nenums:"));
    assert_eq!(found, ["class Spline is new: decide how storage and model handle it, then add it to CLASSES"]);
}

#[test]
fn notices_a_new_enum_value_and_a_new_enum() {
    let found = problems(&edited("      error:\n        description: The step raised", "      skipped:\n        description: x\n      error:\n        description: The step raised"));
    assert_eq!(found, ["enum value ComputationStatus.skipped is new: handle it in storage/hdf5.rs, then add it to ENUMS"]);
    let found = problems(&format!("{}\n  Shape:\n    permissible_values:\n      round: {{}}\n", schema_text()));
    assert!(found.iter().any(|p| p.starts_with("enum Shape is new")), "{found:?}");
}

#[test]
fn notices_removals() {
    let found = problems(&edited(
        "      gain:\n        range: float\n        required: true\n        description: >-\n          Multiplicative factor.\n",
        "",
    ));
    assert_eq!(found, ["LinearConversion.gain is gone from the schema: remove it from CLASSES"]);
}
