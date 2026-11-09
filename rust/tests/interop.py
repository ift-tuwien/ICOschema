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

from icoschema import DatasetBundle

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

if failures:
    sys.exit("\n".join(failures))
print(f"{len(expected)} fixtures written by Rust and read back by Python; {tdms_checked} TDMS files converted by Rust")
