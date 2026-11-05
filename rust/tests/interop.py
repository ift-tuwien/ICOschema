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

if failures:
    sys.exit("\n".join(failures))
print(f"{len(expected)} fixtures written by Rust and read back by Python")
