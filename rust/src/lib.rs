//! Rust port of ICOschema: generated schema (`icoschema-gen`), a model layer with the
//! convenience API (`model`) and the HDF5 storage adapter (`storage`).
//!
//! ```no_run
//! let recording = icoschema::Recording::from_hdf5("some_file.hdf5")?;
//! println!("{}", recording.signal_loss_percentage());
//! # Ok::<(), icoschema::Error>(())
//! ```

pub use icoschema_gen as schema;

pub mod model;
pub mod schema_support;
pub mod storage;

pub use model::{DatasetBundle, PreprocessedRecording, Recording};

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
