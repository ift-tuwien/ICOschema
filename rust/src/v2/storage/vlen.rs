//! Shim for variable-length string *arrays* (attributes `inputs`, `output_keys`).
//!
//! rust-hdf5 0.7 returns only the first element of such an attribute. Every element is stored as
//! a reference `{ length: u32, heap address: offset-sized, object index: u32 }` into a *global
//! heap collection* elsewhere in the file. This module resolves those references with plain file
//! reads. The widths of offsets and lengths and the base address (user block) come from the
//! superblock, whose versions 0 to 3 are understood. Anything unexpected is an error, never a
//! wrong value.

use std::fs::File;
use std::io::{Read, Seek, SeekFrom};

use crate::{invalid, Error, Result};

const SIGNATURE: [u8; 8] = [0x89, b'H', b'D', b'F', b'\r', b'\n', 0x1a, b'\n'];

struct Layout {
    offset_size: usize,
    length_size: usize,
    base: u64,
}

fn io(e: std::io::Error) -> Error {
    Error::Invalid(format!("reading the file: {e}"))
}

fn uint(bytes: &[u8]) -> u64 {
    bytes.iter().rev().fold(0, |acc, b| (acc << 8) | u64::from(*b))
}

/// The superblock is at offset 0, or 512, 1024, 2048, ... when the file has a user block.
fn layout(file: &mut File) -> Result<Layout> {
    let mut at = 0u64;
    loop {
        let mut head = [0u8; 64];
        file.seek(SeekFrom::Start(at)).map_err(io)?;
        let read = file.read(&mut head).map_err(io)?;
        if read >= 32 && head[..8] == SIGNATURE {
            let (offset_size, length_size, base_at) = match head[8] {
                0 => (head[13], head[14], 24),
                1 => (head[13], head[14], 28),
                2 | 3 => (head[9], head[10], 12),
                v => return invalid(format!("unsupported HDF5 superblock version {v}")),
            };
            let (offset_size, length_size) = (offset_size as usize, length_size as usize);
            if !matches!(offset_size, 2 | 4 | 8) || !matches!(length_size, 2 | 4 | 8) {
                return invalid("unsupported HDF5 offset or length size");
            }
            // Addresses in the file are relative to the superblock, like libhdf5 (which also
            // ignores a stale stored base address and uses where the superblock actually is).
            let _stored_base = &head[base_at..base_at + offset_size];
            return Ok(Layout { offset_size, length_size, base: at });
        }
        if at >= 1 << 20 {
            return invalid("not an HDF5 file (no superblock found)");
        }
        at = if at == 0 { 512 } else { at * 2 };
    }
}

pub fn strings(path: &str, raw: &[u8]) -> Result<Vec<String>> {
    let mut file = File::open(path).map_err(io)?;
    let layout = layout(&mut file)?;
    let reference = 4 + layout.offset_size + 4;
    if raw.len() % reference != 0 {
        return invalid("variable-length string attribute has an unexpected layout");
    }
    raw.chunks_exact(reference)
        .map(|r| {
            let length = uint(&r[..4]) as usize;
            let address = uint(&r[4..4 + layout.offset_size]);
            let index = uint(&r[4 + layout.offset_size..]) as u32;
            read_object(&mut file, &layout, address, index, length)
        })
        .collect()
}

/// Object `index` of the global heap collection at `address`.
fn read_object(file: &mut File, layout: &Layout, address: u64, index: u32, length: usize) -> Result<String> {
    let l = layout.length_size;
    file.seek(SeekFrom::Start(layout.base + address)).map_err(io)?;
    let mut header = vec![0u8; 8 + l]; // "GCOL", version, 3 reserved, collection size
    file.read_exact(&mut header).map_err(io)?;
    if &header[0..4] != b"GCOL" || header[4] != 1 {
        return invalid("global heap collection not found (unsupported file layout)");
    }
    let size = uint(&header[8..]) as usize;
    let mut body = vec![0u8; size.saturating_sub(header.len())];
    file.read_exact(&mut body).map_err(io)?;

    // Objects: index u16, reference count u16, reserved u32, size (length-sized), data padded to 8.
    let object_header = 8 + l;
    let mut at = 0;
    while at + object_header <= body.len() {
        let id = uint(&body[at..at + 2]) as u32;
        let object_size = uint(&body[at + 8..at + 8 + l]) as usize;
        if id == 0 {
            break; // free space
        }
        let data = at + object_header;
        if id == index {
            if object_size < length || data + length > body.len() {
                return invalid("global heap object is shorter than its reference says");
            }
            return String::from_utf8(body[data..data + length].to_vec())
                .or_else(|_| invalid("string attribute is not valid UTF-8"));
        }
        at = data + object_size.div_ceil(8) * 8;
    }
    invalid(format!("global heap object {index} not found"))
}
