"""Files written by the Rust writer, read by libhdf5 (h5py) and the Python icoschema.

    uv run python rust/tests/interop.py

For every fixture: read it with Rust, write it again with Rust, read the new file with the Python
icoschema and require exactly what Python itself reads after rewriting the fixture
(`expected_roundtrip.json`). Also walks the file with h5py, which uses the reference HDF5 C
library, so a file the Rust writer got subtly wrong at the format level fails here.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import h5py

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dump import dump

FIXTURES = HERE / "fixtures"
expected = json.loads((FIXTURES / "expected_roundtrip.json").read_text())

subprocess.run(["cargo", "build", "-q", "--example", "rewrite"], check=True, cwd=HERE.parent)
binary = HERE.parent.parent / "target/debug/examples/rewrite"

failures = []
with tempfile.TemporaryDirectory() as tmp:
    for name, want in expected.items():
        source, target = FIXTURES / name, Path(tmp) / name
        written = subprocess.run([binary, source, target], capture_output=True, text=True, check=False)
        if "write_error" in want:
            if written.returncode == 0:
                failures.append(f"{name}: Python cannot write it back but Rust did")
            continue
        if written.returncode != 0:
            failures.append(f"{name}: Rust failed to write: {written.stderr.strip()}")
            continue
        with h5py.File(target) as f:  # every dataset and attribute must be readable by libhdf5
            f.visititems(lambda _, obj: (obj[()] if isinstance(obj, h5py.Dataset) else None, dict(obj.attrs)))
        got = json.loads(json.dumps(dump(target), default=str))
        if got != want:
            differing = [k for k in want if got.get(k) != want[k]]
            failures.append(f"{name}: Python reads different {differing} from the Rust-written file")
        else:
            print(f"ok  {name}")

# TDMS files: Rust reads them and writes HDF5; Python must read that as it reads its own HDF5 of the file
import warnings

from icoschema.v1 import DatasetBundle

tdms_checked = 0
with tempfile.TemporaryDirectory() as tmp:
    for source in sorted((FIXTURES / "tdms").glob("*.tdms")):
        if source.name.startswith("err_") or source.name in ("dual_stu.tdms", "single_stu_empty_quality.tdms"):
            continue  # rejected files; the 1 MB real file (compared by hash in tests/tdms.rs); a file tedium panics on
        target = Path(tmp) / (source.stem + ".h5")
        written = subprocess.run([binary, source, target], capture_output=True, text=True, check=False)
        if written.returncode != 0:
            failures.append(f"{source.name}: Rust failed to read the TDMS file and write HDF5: {written.stderr.strip()}")
            continue
        reference = Path(tmp) / (source.stem + ".python.h5")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            DatasetBundle.from_tdms(str(source)).to_hdf5(str(reference))
        with h5py.File(target) as f:
            f.visititems(lambda _, obj: (obj[()] if isinstance(obj, h5py.Dataset) else None, dict(obj.attrs)))
        got, want = (json.loads(json.dumps(dump(path), default=str)) for path in (target, reference))
        if got != want:
            failures.append(f"{source.name}: Python reads different {[k for k in want if got.get(k) != want[k]]} from the Rust-written HDF5")
        else:
            tdms_checked += 1
            print(f"ok  {source.name} (TDMS -> Rust -> HDF5)")

# Schema version 2: the stored synthetic files of the Python package, rewritten by Rust (mode 2), must read in
# Python as the originals do; v1 files converted by Rust (mode "convert") must read as Python's own migration.
import dataclasses

import icoschema
from icoschema import v2

ROOT = HERE.parent.parent
v2_checked = 0


def through_hdf5(bundle, path):
    """What Python reads back after writing `bundle` as HDF5 (values are stored as float32)."""
    bundle.to_hdf5(str(path))
    return v2.DatasetBundle.from_hdf5(str(path), on_error="raise")


def same_sources(a, b) -> bool:
    """The sources are equal; their `additional_data` JSON texts by value (Rust and Python print JSON differently)."""
    if list(a.recording.sources) != list(b.recording.sources):
        return False
    for name, x in a.recording.sources.items():
        y = b.recording.sources[name]
        texts = (x.additional_data, y.additional_data)
        if (texts[0] is None) != (texts[1] is None) or (
            texts[0] is not None and json.loads(texts[0]) != json.loads(texts[1])
        ):
            return False
        if dataclasses.replace(x, additional_data=None) != dataclasses.replace(y, additional_data=None):
            return False
    return True


def same(a, b) -> bool:
    return (
        same_sources(a, b)
        and a.preprocessed_tables == b.preprocessed_tables
        and a.computations == b.computations
        and a.steps == b.steps
    )


with tempfile.TemporaryDirectory() as tmp:
    for source in sorted((ROOT / "test/v2/data").iterdir()):
        target = Path(tmp) / (source.stem + ".v2.hdf5")
        written = subprocess.run([binary, source, target, "2"], capture_output=True, text=True, check=False)
        if written.returncode != 0:
            failures.append(f"{source.name}: Rust failed to rewrite it as schema version 2: {written.stderr.strip()}")
            continue
        with h5py.File(target) as f:
            f.visititems(lambda _, obj: (obj[()] if isinstance(obj, h5py.Dataset) else None, dict(obj.attrs)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            original = through_hdf5(v2.DatasetBundle.from_file(str(source)), Path(tmp) / "reference.v2.hdf5")
        got = v2.DatasetBundle.from_hdf5(str(target), on_error="raise")
        if not same(original, got):
            failures.append(f"{source.name}: Python (schema version 2) reads the Rust-written file differently")
        else:
            v2_checked += 1
            print(f"ok  {source.name} (schema version 2)")

    for source in sorted((ROOT / "test/v1/data").iterdir()):
        target = Path(tmp) / (source.stem + ".converted.hdf5")
        written = subprocess.run([binary, source, target, "convert"], capture_output=True, text=True, check=False)
        if written.returncode != 0:
            failures.append(f"{source.name}: Rust failed to convert it to schema version 2: {written.stderr.strip()}")
            continue
        with h5py.File(target) as f:
            f.visititems(lambda _, obj: (obj[()] if isinstance(obj, h5py.Dataset) else None, dict(obj.attrs)))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            migrated = through_hdf5(icoschema.read(str(source)), Path(tmp) / "reference.migrated.hdf5")
        got = v2.DatasetBundle.from_hdf5(str(target), on_error="raise")
        if not same(migrated, got):
            failures.append(f"{source.name}: Rust's migration to schema version 2 differs from Python's")
        else:
            v2_checked += 1
            print(f"ok  {source.name} (schema version 1 -> 2)")

if failures:
    sys.exit("\n".join(failures))
print(
    f"{len(expected)} fixtures written by Rust and read back by Python; {tdms_checked} TDMS files converted by Rust; "
    f"{v2_checked} schema version 2 files and migrations checked"
)
