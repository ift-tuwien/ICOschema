"""Builds tests/fixtures/malformed_computation.h5, a schema version 2 file with a malformed computation.

    uv run python rust/tests/gen_malformed_fixtures.py

It starts from the stored synthetic file `test/v2/data/hdf5_2.0_1ch.hdf5` (one source, the computation `rms/ch1`
and the step `rms`) and adds

- the computation `bad/text`, a dataset of strings: not numeric, so not a `DerivedDataset`;
- the step `uses_bad`, which lists `bad/text` as an output, so it is dropped with the computation it needs.

The Rust reader must skip both with `OnError::Skip` and fail with `OnError::Raise` (tests/features.rs). The script
also checks that the Python reader does the same, so the file is malformed for both.
"""

import shutil
from pathlib import Path

import h5py

from icoschema import v2

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent.parent / "test" / "v2" / "data" / "hdf5_2.0_1ch.hdf5"
TARGET = HERE / "fixtures" / "malformed_computation.h5"

shutil.copyfile(SOURCE, TARGET)
with h5py.File(TARGET, "r+") as f:
    f["computations"].create_dataset("bad/text", data=["not", "numbers"], dtype=h5py.string_dtype())
    step = f["steps"].create_group("uses_bad")
    step.attrs["step_index"] = 1
    step.attrs["producer"] = "synthetic"
    step.attrs.create("output_keys", ["bad/text"], dtype=h5py.string_dtype())

# the Python reader skips them by default and raises on request
skipped = v2.DatasetBundle.from_hdf5(str(TARGET))
assert sorted(skipped.computations) == ["rms/ch1"], sorted(skipped.computations)
assert [step.node for step in skipped.steps] == ["rms"], [step.node for step in skipped.steps]
try:
    v2.DatasetBundle.from_hdf5(str(TARGET), on_error="raise")
except Exception as error:  # noqa: BLE001 (any error is a failed read)
    print(f"wrote {TARGET.relative_to(HERE.parent.parent)} (Python on_error='raise': {type(error).__name__})")
else:
    raise SystemExit("the Python reader did not raise on the malformed computation")
