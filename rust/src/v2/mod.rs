//! Schema version 2 (`icoschema/v2` in the Python package): the generated schema (`schema`), a model
//! layer with the convenience API (`model`) and the HDF5 / TDMS storage adapters (`storage`).
//!
//! The version is self-contained (it refers to the rest of the crate only through the shared
//! `Error`/`Result`), so that the next version starts as a copy of it.

pub use icoschema_gen_v2 as schema;

pub mod model;
pub mod schema_support;
pub mod storage;

pub use model::{DatasetBundle, PreprocessedRecording, Recording, Source};
pub use storage::OnError;

/// The HDF5 file format versions this schema version reads (one), or with
/// `writable` the ones `to_hdf5_with(.., Some(version))` can write, oldest first. Like Python's
/// `hdf5_format_versions(writable=...)`.
pub fn hdf5_format_versions(writable: bool) -> Vec<&'static str> {
    if writable {
        storage::write::writable_versions()
    } else {
        storage::hdf5::readable_versions()
    }
}
