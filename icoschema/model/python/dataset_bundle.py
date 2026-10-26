"""The public API for a `DatasetBundle`: a `Recording`, its optional
`PreprocessedRecording`, every `DerivedDataset` computed from them, and the
`ComputationStep`s that produced those (see ICOschema/schema/generated/python).
Adds loading from / writing to storage, validation and immutable-update
helpers on top of the generated fields (`recording`, `preprocessed`,
`computations`, `steps`).

This file should never be imported directly, but rather only from the main
entrypoint:

    from icoschema import DatasetBundle

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
    bundle.to_hdf5("some_file.hdf5")

`DerivedDataset` itself has no model-layer wrapper -- like `Sensor` or
`ChannelMetadata`, it's a component type with no behavior beyond what's
generated, used directly via
`ICOschema.schema.generated.python.dataset.DerivedDataset`.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable
from typing import Literal, cast

from icoschema.model.python.preprocessed_recording import PreprocessedRecording
from icoschema.model.python.recording import Recording
from icoschema.schema.generated.python import dataset as generated
from icoschema.schema.generated.python.dataset import ComputationStep, DerivedDataset

_CHANNELS = ("channel1", "channel2", "channel3")


class DatasetBundle(generated.DatasetBundle):
    """A Recording, its optional PreprocessedRecording, every DerivedDataset
    computed from them, and the ComputationSteps that produced those.

    Has every field of `ICOschema.schema.generated.python.dataset.DatasetBundle`
    (`recording`, `preprocessed`, `computations`, `steps`), plus the
    loading/writing and immutable-update methods defined below. Construct via
    a `from_XXX` classmethod (e.g. `from_hdf5`) rather than the bare
    constructor when loading from storage.

    `steps` is a list ordered by `step_index` (0, 1, 2, ...). Add steps only
    through `with_step`, which assigns the index and validates the step.
    """

    @classmethod
    def from_hdf5(cls, path: str, *, on_error: Literal["skip", "raise"] = "skip") -> DatasetBundle:
        """Load a DatasetBundle from an HDF5 file.

        `computations` is empty and `preprocessed` is `None` if the file has
        none. A malformed computation entry is logged and skipped by default;
        pass `on_error="raise"` to fail the whole read instead. A
        preprocessed table that doesn't fit the recording always raises
        `ValueError` (see `with_preprocessed`), whatever `on_error` says --
        it's primary data, not an optional extra. See
        ICOschema.storage.python.hdf5 for the accepted file layout.
        """
        from icoschema.storage.python import hdf5

        loaded = hdf5.load_dataset_bundle(path, on_error=on_error)
        bundle = cls(
            recording=_as_model_recording(loaded.recording),
            computations=dict(loaded.computations),
            steps=list(loaded.steps),
        )
        if loaded.preprocessed is not None:
            bundle = bundle.with_preprocessed(loaded.preprocessed)
        return bundle

    def to_hdf5(self, path: str) -> None:
        """Write this bundle (recording, preprocessed table, every
        computation) to a fresh HDF5 file.

        See ICOschema.storage.python.hdf5 for the file layout this
        produces -- each computation is stored in its true N-D shape under
        a `/computations/` group. Raises `ValueError` if `preprocessed`
        doesn't fit `recording` (see `with_preprocessed`).
        """
        from icoschema.storage.python import hdf5

        if self.preprocessed is not None:
            validate_preprocessed(_as_model_recording(self.recording), self.preprocessed)
        validate_steps(self._steps(), self.computations)
        hdf5.save_dataset_bundle(self, path)

    def with_recording(self, recording: Recording) -> DatasetBundle:
        """A copy of this bundle with `recording` replaced.

        Raises `ValueError` while the bundle has a `preprocessed` table or
        any `steps`, which were built from the current recording and would
        silently go stale -- drop them first (`without_preprocessed()`,
        `without_steps(...)`).
        """
        if self.preprocessed is not None:
            raise ValueError(
                "cannot replace the recording of a bundle with a preprocessed table "
                "(it was built from the current recording) -- call without_preprocessed() first"
            )
        if self.steps:
            raise ValueError(
                "cannot replace the recording of a bundle with computation steps "
                "(they were computed from the current recording) -- call without_steps() first"
            )
        return DatasetBundle(recording=recording, computations=dict(self.computations))

    def with_preprocessed(self, preprocessed: generated.PreprocessedRecording) -> DatasetBundle:
        """A copy of this bundle with `preprocessed` set (added or replaced).

        Raises `ValueError` if the table doesn't fit `recording` (see
        `validate_preprocessed`).
        """
        recording = _as_model_recording(self.recording)
        model_preprocessed = _as_model_preprocessed(preprocessed)
        validate_preprocessed(recording, model_preprocessed)
        return DatasetBundle(
            recording=recording,
            preprocessed=model_preprocessed,
            computations=dict(self.computations),
            steps=list(self._steps()),
        )

    def without_preprocessed(self) -> DatasetBundle:
        """A copy of this bundle without a `preprocessed` table (steps and
        computations are kept -- dropping what was computed from the table is
        up to the caller)."""
        return DatasetBundle(recording=self.recording, computations=dict(self.computations), steps=list(self._steps()))

    def with_computation(self, key: str, derived: DerivedDataset) -> DatasetBundle:
        """A copy of this bundle with one computation added/replaced under `key`."""
        computations = dict(self.computations)
        computations[key] = derived
        return DatasetBundle(
            recording=self.recording,
            preprocessed=self.preprocessed,
            computations=computations,
            steps=list(self._steps()),
        )

    def with_step(self, step: ComputationStep) -> DatasetBundle:
        """A copy of this bundle with `step` appended as the last step.

        `step.step_index` is assigned here (`len(steps)`); whatever it was is
        overwritten. Raises `ValueError` if `step.node` is already taken or
        isn't a single HDF5 path segment, or if an `output_keys` entry isn't
        in `computations` -- add the step's computations first.
        """
        appended = dataclasses.replace(step, step_index=len(self.steps))
        steps = [*self._steps(), appended]
        validate_steps(steps, self.computations)
        return DatasetBundle(
            recording=self.recording,
            preprocessed=self.preprocessed,
            computations=dict(self.computations),
            steps=steps,
        )

    def without_steps(self, nodes: Iterable[str]) -> DatasetBundle:
        """A copy of this bundle without the steps named `nodes` and the
        computations they list in `output_keys`. The remaining steps keep
        their order and are renumbered 0, 1, 2, ... Nothing else is dropped:
        what depends on a removed step is up to the caller. Raises
        `ValueError` for an unknown node."""
        nodes = set(nodes)
        unknown = nodes - {step.node for step in self._steps()}
        if unknown:
            raise ValueError(f"no such step(s): {sorted(unknown)}")
        removed_keys = {key for step in self._steps() if step.node in nodes for key in step.output_keys}
        kept = [step for step in self._steps() if step.node not in nodes]
        return DatasetBundle(
            recording=self.recording,
            preprocessed=self.preprocessed,
            computations={k: v for k, v in self.computations.items() if k not in removed_keys},
            steps=[dataclasses.replace(step, step_index=i) for i, step in enumerate(kept)],
        )

    def computations_of(self, node: str) -> dict[str, DerivedDataset]:
        """The computations step `node` wrote (its `output_keys`), by key.
        Raises `ValueError` for an unknown node."""
        for step in self._steps():
            if step.node == node:
                return {key: self.computations[key] for key in step.output_keys}
        raise ValueError(f"no such step: {node!r}")

    def unmanaged_keys(self) -> set[str]:
        """Computation keys no step lists in its `output_keys` (e.g. from
        older files or code that adds computations without recording a step)."""
        managed = {key for step in self._steps() for key in step.output_keys}
        return set(self.computations) - managed

    def _steps(self) -> list[ComputationStep]:
        """`steps`, typed: the generated field also admits dict/str forms
        before `__post_init__` normalizes it to a list."""
        return cast(list[ComputationStep], self.steps)


def validate_preprocessed(recording: Recording, preprocessed: generated.PreprocessedRecording) -> None:
    """Raises `ValueError` unless `preprocessed` fits `recording`: one row
    per gap-free grid position (`recording.sample_index()[-1] + 1`), the same
    set of channels, every column of equal length, and a positive finite
    `channel_sampling_frequency`."""
    grid_length = int(recording.sample_index()[-1]) + 1
    raw_channels = [name for name in _CHANNELS if getattr(recording, name).size > 0]
    preprocessed_channels = [name for name in _CHANNELS if len(getattr(preprocessed, name)) > 0]
    if preprocessed_channels != raw_channels:
        raise ValueError(
            f"preprocessed table has channels {preprocessed_channels}, but the recording has {raw_channels}"
        )
    for column in ("timestamp", *raw_channels):
        length = len(getattr(preprocessed, column))
        if length != grid_length:
            raise ValueError(
                f"preprocessed {column} has {length} rows, but the recording's gap-free grid has {grid_length}"
            )
    frequency = preprocessed.channel_sampling_frequency
    if not (math.isfinite(frequency) and frequency > 0):
        raise ValueError(f"preprocessed channel_sampling_frequency must be positive and finite, got {frequency}")


def validate_steps(steps: list[ComputationStep], computations: dict[str, DerivedDataset]) -> None:
    """Raises `ValueError` unless `steps` are numbered 0, 1, 2, ... in order,
    every node name is unique and a single HDF5 path segment, and every
    `output_keys` entry is in `computations`."""
    seen: set[str] = set()
    for position, step in enumerate(steps):
        node = str(step.node)
        if not node or "/" in node or node.startswith("."):
            raise ValueError(f"step name {node!r} must be non-empty, contain no '/' and not start with '.'")
        if node in seen:
            raise ValueError(f"duplicate step name {node!r}")
        seen.add(node)
        if step.step_index != position:
            raise ValueError(f"step {node!r} has step_index {step.step_index}, expected {position}")
        missing = [key for key in step.output_keys if key not in computations]
        if missing:
            raise ValueError(f"step {node!r} lists output_keys missing from computations: {missing}")


def _as_model_recording(recording: generated.Recording) -> Recording:
    if isinstance(recording, Recording):
        return recording
    return Recording(
        hardware_metadata=recording.hardware_metadata,
        recording_metadata=recording.recording_metadata,
        recording_data=recording.recording_data,
    )


def _as_model_preprocessed(preprocessed: generated.PreprocessedRecording) -> PreprocessedRecording:
    if isinstance(preprocessed, PreprocessedRecording):
        return preprocessed
    return PreprocessedRecording(
        timestamp=preprocessed.timestamp,
        channel1=preprocessed.channel1,
        channel2=preprocessed.channel2,
        channel3=preprocessed.channel3,
        channel_sampling_frequency=preprocessed.channel_sampling_frequency,
        sampling_frequency_source=preprocessed.sampling_frequency_source,
        fill_method=preprocessed.fill_method,
        producer=preprocessed.producer,
    )
