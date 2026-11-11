//! Storage adapters (internal; use `Recording::from_hdf5` / `DatasetBundle::from_hdf5`).
pub mod hdf5;
#[cfg(feature = "tdms")]
pub mod tdms;
mod table;
mod vlen;
pub mod write;

use rust_hdf5::H5Dataset;

use crate::{invalid, Result};

/// A corrupt file can claim a dataset of terabytes and rust-hdf5 allocates it before reading.
/// gzip cannot expand data by more than about 1000x, so a dataset larger than that cannot be real.
pub(crate) fn budget(path: &str) -> Result<u64> {
    let len = std::fs::metadata(path).map_err(|e| crate::Error::Invalid(format!("{path}: {e}")))?.len();
    Ok(len.saturating_mul(1100).saturating_add(1 << 20))
}

pub(crate) fn check_size(dataset: &H5Dataset, budget: u64) -> Result<()> {
    let elements = dataset.shape().iter().try_fold(1u64, |acc, d| acc.checked_mul(*d as u64));
    let bytes = elements.and_then(|n| n.checked_mul(dataset.element_size() as u64));
    match bytes {
        Some(b) if b <= budget => Ok(()),
        _ => invalid("dataset is larger than the file could possibly hold (corrupt file?)"),
    }
}

/// The software identity written into a file's provenance.
pub(crate) fn software_id() -> String {
    format!("icoschema-rust {}", env!("CARGO_PKG_VERSION"))
}
