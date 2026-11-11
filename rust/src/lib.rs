//! Rust port of ICOschema. Every schema version is a module of its own (`v1`, `v2`), like the Python
//! package's `icoschema.v1` and `icoschema.v2`: the generated schema (`schema`), a model layer with the
//! convenience API (`model`) and the storage adapters (`storage`). The names at the top level are those
//! of the latest schema version; `read` opens a file of any schema version as that one.
//!
//! A recording holds one or more sources (one per STU/STH combination); `Source` has the data
//! and the calculations on it.
//!
//! ```no_run
//! let recording = icoschema::Recording::from_hdf5("some_file.hdf5")?;
//! println!("{}", recording.only_source()?.signal_loss_percentage());
//! # Ok::<(), icoschema::Error>(())
//! ```

pub mod migrate;
pub mod v1;
pub mod v2;

// The latest schema version.
pub use v2::model;
pub use v2::{schema, schema_support, storage, DatasetBundle, PreprocessedRecording, Recording, Source};

pub use migrate::{read, schema_version_of_file};

#[derive(Debug, thiserror::Error)]
pub enum Error {
    #[error("hdf5: {0}")]
    Hdf5(#[from] rust_hdf5::Hdf5Error),
    #[error("{0}")]
    Invalid(String),
}

pub type Result<T> = std::result::Result<T, Error>;

pub(crate) fn invalid<T>(message: impl Into<String>) -> Result<T> {
    Err(Error::Invalid(message.into()))
}
