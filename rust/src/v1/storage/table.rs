//! A compound HDF5 dataset (PyTables-style table) read into one buffer, with typed column access
//! by member name. Columns are decoded from the dataset's own datatype message, so no row struct
//! is needed and extra or missing columns are fine.

use rust_hdf5::format::messages::datatype::CompoundMember;
use rust_hdf5::{ByteOrder, DatatypeMessage, H5Dataset};

use crate::{invalid, Result};

pub struct Table {
    raw: Vec<u8>,
    row_size: usize,
    members: Vec<CompoundMember>,
}

impl Table {
    pub fn read(dataset: &H5Dataset, budget: u64) -> Result<Self> {
        let DatatypeMessage::Compound { size, members } = dataset.datatype()? else {
            return invalid("dataset is not a table (compound type)");
        };
        super::check_size(dataset, budget)?;
        let raw = dataset.read_raw_bytes()?;
        let row_size = size as usize;
        if row_size == 0 || raw.len() % row_size != 0 {
            return invalid("table data does not match its row size");
        }
        Ok(Self { raw, row_size, members })
    }

    pub fn len(&self) -> usize {
        self.raw.len().checked_div(self.row_size).unwrap_or(0)
    }

    pub fn column_names(&self) -> impl Iterator<Item = &str> {
        self.members.iter().map(|m| m.name.as_str())
    }

    pub fn has(&self, name: &str) -> bool {
        self.members.iter().any(|m| m.name == name)
    }

    fn member(&self, name: &str) -> Result<&CompoundMember> {
        match self.members.iter().find(|m| m.name == name) {
            Some(member) => Ok(member),
            None => invalid(format!("table has no column '{name}'")),
        }
    }

    /// The cells of a column, after checking that `width` bytes at its offset fit in a row.
    fn cells<'a>(&'a self, member: &CompoundMember, width: usize) -> Result<impl Iterator<Item = &'a [u8]> + 'a> {
        let offset = member.offset as usize;
        if width == 0 || offset.checked_add(width).is_none_or(|end| end > self.row_size) {
            return invalid(format!("column '{}' does not fit in a row", member.name));
        }
        Ok(self.raw.chunks_exact(self.row_size).map(move |row| &row[offset..offset + width]))
    }

    /// A numeric column as integers (unsigned values above `i64::MAX` are not expected).
    pub fn i64_column(&self, name: &str) -> Result<Vec<i64>> {
        let member = self.member(name)?;
        let DatatypeMessage::FixedPoint { size, byte_order: ByteOrder::LittleEndian, signed, .. } = member.datatype
        else {
            return invalid(format!("column '{name}' is not a little-endian integer"));
        };
        let width = size as usize;
        if width == 0 || width > 8 {
            return invalid(format!("column '{name}' has an unsupported integer width"));
        }
        Ok(self
            .cells(member, width)?
            .map(|cell| {
                let mut bytes = [0u8; 8];
                bytes[..width].copy_from_slice(cell);
                let value = u64::from_le_bytes(bytes);
                if signed && width < 8 && cell[width - 1] & 0x80 != 0 {
                    (value | (u64::MAX << (8 * width))) as i64
                } else {
                    value as i64
                }
            })
            .collect())
    }

    /// A numeric column as `f64` (integers are converted too).
    pub fn f64_column(&self, name: &str) -> Result<Vec<f64>> {
        let member = self.member(name)?;
        match member.datatype {
            DatatypeMessage::FloatingPoint { size: 4, byte_order: ByteOrder::LittleEndian, .. } => Ok(self
                .cells(member, 4)?
                .map(|c| f64::from(f32::from_le_bytes(c.try_into().unwrap())))
                .collect()),
            DatatypeMessage::FloatingPoint { size: 8, byte_order: ByteOrder::LittleEndian, .. } => Ok(self
                .cells(member, 8)?
                .map(|c| f64::from_le_bytes(c.try_into().unwrap()))
                .collect()),
            DatatypeMessage::FixedPoint { .. } => {
                Ok(self.i64_column(name)?.into_iter().map(|v| v as f64).collect())
            }
            _ => invalid(format!("column '{name}' is not a little-endian number")),
        }
    }

    /// A fixed-length string column (NUL padded), as written by h5py (`S100`).
    pub fn string_column(&self, name: &str) -> Result<Vec<String>> {
        let member = self.member(name)?;
        let DatatypeMessage::FixedString { size, .. } = member.datatype else {
            return invalid(format!("column '{name}' is not a fixed-length string"));
        };
        Ok(self
            .cells(member, size as usize)?
            .map(|c| String::from_utf8_lossy(c).trim_end_matches('\0').to_string())
            .collect())
    }
}
