//! `rewrite <in.h5> <out.h5>`: reads a file and writes it again with the Rust writer
//! (used by tests/interop.py to have libhdf5 and the Python icoschema read what Rust wrote).
fn main() -> icoschema::Result<()> {
    let mut args = std::env::args().skip(1);
    let (input, output) = (args.next().expect("input"), args.next().expect("output"));
    icoschema::DatasetBundle::from_hdf5(&input)?.to_hdf5(&output)
}
