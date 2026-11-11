//! `rewrite <in> <out> [1|2|convert]`: reads a file and writes it again with the Rust writer (used by
//! tests/interop.py to have libhdf5 and the Python icoschema read what Rust wrote).
//!
//! - `1` (the default): a file of schema version 1 is read and written as schema version 1;
//! - `2`: the same for schema version 2;
//! - `convert`: a file of schema version 1 is read, migrated and written as schema version 2.
fn main() -> icoschema::Result<()> {
    let mut args = std::env::args().skip(1);
    let (input, output) = (args.next().expect("input"), args.next().expect("output"));
    match args.next().as_deref().unwrap_or("1") {
        "1" => icoschema::v1::DatasetBundle::from_file(&input)?.to_hdf5(&output),
        "2" => icoschema::v2::DatasetBundle::from_file(&input)?.to_hdf5(&output),
        "convert" => icoschema::migrate::convert_file(&input, &output),
        other => panic!("unknown mode {other:?}: use 1, 2 or convert"),
    }
}
