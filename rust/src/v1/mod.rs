//! Schema version 1 (`icoschema/v1` in the Python package): the generated schema (`schema`), a model
//! layer with the convenience API (`model`) and the HDF5 / TDMS storage adapters (`storage`).
//!
//! The version is self-contained (it refers to the rest of the crate only through the shared
//! `Error`/`Result`), so that the next version starts as a copy of it.

pub use icoschema_gen_v1 as schema;

pub mod model;
pub mod schema_support;
pub mod storage;

pub use model::{DatasetBundle, PreprocessedRecording, Recording, Source};
