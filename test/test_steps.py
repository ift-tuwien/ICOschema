"""Tests for ComputationStep records (format 1.2): `DatasetBundle.with_step`
/ `without_steps` / `computations_of` / `unmanaged_keys`, validation, and
the round trip through HDF5."""

import logging
from pathlib import Path

import h5py
import pytest

from icoschema import ComputationStep, DatasetBundle, DerivedDataset

FIXTURE = Path(__file__).resolve().parent / "test_with_sensors.hdf5"


def _derived(key: str) -> DerivedDataset:
    return DerivedDataset(key=key, values=[1.0, 2.0], shape=[2], dtype="float32")


def _step(node: str, *output_keys: str, **fields) -> ComputationStep:
    return ComputationStep(
        node=node, step_index=99, producer=f"{node}@1.0.0", output_keys=list(output_keys), status="ok", **fields
    )


def _bundle_with_two_steps() -> DatasetBundle:
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    for key in ("a/channel1", "a/channel1.sample_range", "b/channel1", "loose/x"):
        bundle = bundle.with_computation(key, _derived(key))
    bundle = bundle.with_step(_step("a", "a/channel1", "a/channel1.sample_range", inputs=["preprocessed"]))
    return bundle.with_step(_step("b", "b/channel1", inputs=["a"]))


# ── model ────────────────────────────────────────────────────────────────────

def test_with_step_appends_and_assigns_step_index():
    bundle = _bundle_with_two_steps()
    assert [(step.node, step.step_index) for step in bundle.steps] == [("a", 0), ("b", 1)]


def test_with_step_rejects_a_duplicate_node():
    bundle = _bundle_with_two_steps()
    with pytest.raises(ValueError, match="duplicate"):
        bundle.with_step(_step("a"))


@pytest.mark.parametrize("node", ["", "a/b", ".hidden"])
def test_with_step_rejects_a_node_that_is_not_one_path_segment(node):
    with pytest.raises(ValueError, match="must be non-empty"):
        DatasetBundle.from_hdf5(str(FIXTURE)).with_step(_step(node))


def test_with_step_requires_its_output_keys_to_exist():
    with pytest.raises(ValueError, match="missing from computations"):
        DatasetBundle.from_hdf5(str(FIXTURE)).with_step(_step("a", "a/channel1"))


def test_computations_of_and_unmanaged_keys():
    bundle = _bundle_with_two_steps()
    assert set(bundle.computations_of("a")) == {"a/channel1", "a/channel1.sample_range"}
    assert bundle.unmanaged_keys() == {"loose/x"}
    with pytest.raises(ValueError, match="no such step"):
        bundle.computations_of("nope")


def test_without_steps_drops_steps_and_their_computations_and_renumbers():
    bundle = _bundle_with_two_steps().without_steps(["a"])
    assert [(step.node, step.step_index) for step in bundle.steps] == [("b", 0)]
    assert set(bundle.computations) == {"b/channel1", "loose/x"}  # no downstream logic: b stays


def test_without_steps_rejects_an_unknown_node():
    with pytest.raises(ValueError, match="no such step"):
        _bundle_with_two_steps().without_steps(["nope"])


def test_copy_helpers_keep_the_steps():
    bundle = _bundle_with_two_steps()
    assert [step.node for step in bundle.with_computation("c", _derived("c")).steps] == ["a", "b"]
    assert [step.node for step in bundle.without_preprocessed().steps] == ["a", "b"]


def test_with_recording_refuses_while_steps_exist():
    bundle = _bundle_with_two_steps()
    with pytest.raises(ValueError, match="without_steps"):
        bundle.with_recording(bundle.recording)
    assert bundle.without_steps(["a", "b"]).with_recording(bundle.recording).steps == []


def test_to_hdf5_rejects_inconsistent_steps(tmp_path):
    bundle = DatasetBundle.from_hdf5(str(FIXTURE))
    broken = DatasetBundle(recording=bundle.recording, steps=[_step("a", "a/missing")])
    with pytest.raises(ValueError):
        broken.to_hdf5(str(tmp_path / "broken.hdf5"))


# ── storage ──────────────────────────────────────────────────────────────────

def test_steps_round_trip_as_format_1_2(tmp_path):
    bundle = _bundle_with_two_steps()
    bundle = bundle.without_steps(["b"]).with_computation("b/channel1", _derived("b/channel1")).with_step(
        _step(
            "b",
            "b/channel1",
            inputs=["a"],
            params='{"window_size": 10}',
            resolved_params='{"sampling_frequency": 9523.8}',
            summary='{"rows": 2}',
            started_at="2026-10-26T12:00:00",
            duration_s=0.25,
            environment='{"icocompute": "0.2.0"}',
        )
    )
    failed = ComputationStep(node="c", step_index=0, producer="c@1.0.0", status="error", error="ValueError: boom")
    bundle = bundle.with_step(failed)
    out_file = tmp_path / "steps.hdf5"
    bundle.to_hdf5(str(out_file))

    with h5py.File(out_file, "r") as f:
        assert f.attrs["icoschema_format_version"] == "1.2"
        assert set(f["steps"]) == {"a", "b", "c"}

    reloaded = DatasetBundle.from_hdf5(str(out_file))
    assert [step.node for step in reloaded.steps] == ["a", "b", "c"]
    b = reloaded.steps[1]
    assert b.step_index == 1
    assert b.producer == "b@1.0.0"
    assert b.inputs == ["a"]
    assert b.output_keys == ["b/channel1"]
    assert str(b.status) == "ok"
    assert b.params == '{"window_size": 10}'
    assert b.resolved_params == '{"sampling_frequency": 9523.8}'
    assert b.summary == '{"rows": 2}'
    assert b.started_at == "2026-10-26T12:00:00"
    assert b.duration_s == pytest.approx(0.25)
    assert b.environment == '{"icocompute": "0.2.0"}'
    c = reloaded.steps[2]
    assert (str(c.status), c.error, c.output_keys, c.inputs, c.params) == ("error", "ValueError: boom", [], [], None)
    assert reloaded.unmanaged_keys() == {"loose/x"}


def test_steps_are_read_in_step_index_order_and_renumbered(tmp_path):
    out_file = tmp_path / "steps.hdf5"
    _bundle_with_two_steps().to_hdf5(str(out_file))
    with h5py.File(out_file, "a") as f:  # alphabetical group order is a, b; make b come first, with a gap
        f["steps/a"].attrs["step_index"] = 7
        f["steps/b"].attrs["step_index"] = 3

    reloaded = DatasetBundle.from_hdf5(str(out_file))
    assert [(step.node, step.step_index) for step in reloaded.steps] == [("b", 0), ("a", 1)]


def test_older_formats_load_without_steps(tmp_path):
    assert DatasetBundle.from_hdf5(str(FIXTURE)).steps == []  # legacy
    out_file = tmp_path / "plain.hdf5"
    DatasetBundle.from_hdf5(str(FIXTURE)).to_hdf5(str(out_file))
    with h5py.File(out_file, "a") as f:
        assert f.attrs["icoschema_format_version"] == "1.0"
        f.create_group("steps").create_group("stray")  # not part of 1.0: ignored
    assert DatasetBundle.from_hdf5(str(out_file)).steps == []


def test_a_malformed_step_is_skipped_by_default_or_raises(tmp_path, caplog):
    out_file = tmp_path / "steps.hdf5"
    _bundle_with_two_steps().to_hdf5(str(out_file))
    with h5py.File(out_file, "a") as f:
        del f["steps/a"].attrs["producer"]

    with caplog.at_level(logging.WARNING):
        reloaded = DatasetBundle.from_hdf5(str(out_file))
    assert [(step.node, step.step_index) for step in reloaded.steps] == [("b", 0)]
    assert "Skipping malformed step 'a'" in caplog.text
    with pytest.raises(ValueError):
        DatasetBundle.from_hdf5(str(out_file), on_error="raise")


def test_a_step_whose_computation_was_skipped_is_dropped_too(tmp_path):
    out_file = tmp_path / "steps.hdf5"
    _bundle_with_two_steps().to_hdf5(str(out_file))
    with h5py.File(out_file, "a") as f:
        del f["computations/b/channel1"]

    assert [step.node for step in DatasetBundle.from_hdf5(str(out_file)).steps] == ["a"]
    with pytest.raises(ValueError, match="missing from computations"):
        DatasetBundle.from_hdf5(str(out_file), on_error="raise")


def test_steps_and_a_preprocessed_table_together(tmp_path):
    from test_preprocessed import _preprocess

    bundle = _bundle_with_two_steps()
    bundle = bundle.with_preprocessed(_preprocess(bundle.recording))
    out_file = tmp_path / "both.hdf5"
    bundle.to_hdf5(str(out_file))

    reloaded = DatasetBundle.from_hdf5(str(out_file))
    assert reloaded.preprocessed is not None
    assert [step.node for step in reloaded.steps] == ["a", "b"]
