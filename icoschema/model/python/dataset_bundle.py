"""The public API for a `DatasetBundle`: a `Recording`, its optional
`PreprocessedRecording`s (at most one per source), every `DerivedDataset`
computed from them, and the `ComputationStep`s that produced those (see
ICOschema/schema/generated/python).
Adds loading from / writing to storage, validation and immutable-update
helpers on top of the generated fields (`recording`, `preprocessed_tables`,
`computations`, `steps`).

This file should never be imported directly, but rather only from the main
entrypoint:

    from icoschema import DatasetBundle

    bundle = DatasetBundle.from_hdf5("some_file.hdf5")
    bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
    bundle.to_hdf5("some_file.hdf5")

For a bundle whose recording has a single source, `bundle.preprocessed` is
that source's preprocessed table (or `None`) and `preprocessed=` is accepted
by the constructor; with several sources use `preprocessed_for(source)` and
`with_preprocessed(table, source=...)`.

`DerivedDataset` itself has no model-layer wrapper -- like `Sensor` or
`ChannelMetadata`, it's a component type with no behavior beyond what's
generated, used directly via
`ICOschema.schema.generated.python.dataset.DerivedDataset`.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any, Literal, cast

from icoschema.model.python.preprocessed_recording import PreprocessedRecording
from icoschema.model.python.recording import Recording
from icoschema.model.python.source import Source
from icoschema.schema.generated.python import dataset as generated
from icoschema.schema.generated.python.dataset import ComputationStep, DerivedDataset

if TYPE_CHECKING:
    from icoschema.storage.python.hdf5 import FormatVersion

_CHANNELS = ("channel1", "channel2", "channel3")

HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"
TDMS_SIGNATURE = b"TDSm"

PREPROCESSED_NODE = "preprocessed"
"""`source_node` for the preprocessed table of a single-source recording."""
PREPROCESSED_PREFIX = "preprocessed:"
"""`source_node` prefix for the preprocessed table of a named source."""


class DatasetBundle(generated.DatasetBundle):
    """A Recording, its optional PreprocessedRecordings, every DerivedDataset
    computed from them, and the ComputationSteps that produced those.

    Has every field of `ICOschema.schema.generated.python.dataset.DatasetBundle`
    (`recording`, `preprocessed_tables`, `computations`, `steps`), plus the
    loading/writing and immutable-update methods defined below. Construct via
    a `from_XXX` classmethod (e.g. `from_hdf5`) rather than the bare
    constructor when loading from storage.

    `preprocessed_tables` holds at most one table per source, each with its
    `source` set (a table given without one is assigned to the recording's
    only source). `steps` is a list ordered by `step_index` (0, 1, 2, ...).
    Add steps only through `with_step`, which assigns the index and
    validates the step.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if "preprocessed" in kwargs:
            table = kwargs.pop("preprocessed")
            if "preprocessed_tables" in kwargs:
                raise TypeError("pass either `preprocessed` or `preprocessed_tables`, not both")
            kwargs["preprocessed_tables"] = [] if table is None else [table]
        super().__init__(*args, **kwargs)

    def __post_init__(self, *args: Any, **kwargs: Any) -> None:
        super().__post_init__(*args, **kwargs)
        self.recording = _as_model_recording(self.recording)
        sources = self.recording.sources
        tables: list[PreprocessedRecording] = []
        for table in self.preprocessed_tables:
            model_table = _as_model_preprocessed(table)
            if model_table.source is None:
                if len(sources) != 1:
                    raise ValueError(
                        f"preprocessed table has no `source` and the recording has {len(sources)} sources "
                        f"({[str(name) for name in sources]})"
                    )
                model_table = dataclasses.replace(model_table, source=str(next(iter(sources))))
            tables.append(model_table)
        names = [str(table.source) for table in tables]
        unknown = sorted(set(names) - {str(name) for name in sources})
        if unknown:
            raise ValueError(f"preprocessed table(s) for unknown source(s): {unknown}")
        if len(set(names)) != len(names):
            raise ValueError(f"more than one preprocessed table for a source: {names}")
        self.preprocessed_tables = tables

    @classmethod
    def from_hdf5(cls, path: str, *, on_error: Literal["skip", "raise"] = "skip") -> DatasetBundle:
        """Load a DatasetBundle from an HDF5 file.

        `computations` is empty and there are no preprocessed tables if the
        file has none. A malformed computation entry is logged and skipped by
        default; pass `on_error="raise"` to fail the whole read instead. A
        preprocessed table that doesn't fit its source always raises
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
            provenance=loaded.provenance,
        )
        for table in loaded.preprocessed_tables:
            bundle = bundle.with_preprocessed(table)
        return bundle

    @classmethod
    def from_tdms(cls, path: str) -> DatasetBundle:
        """Load a DatasetBundle (just the recording) from an NI TDMS file.

        TDMS is read-only: save results with `to_hdf5`. See ICOschema.storage.python.tdms for the accepted layouts.
        """
        from icoschema._version import software_id
        from icoschema.storage.python import tdms

        recording, version = tdms.load(path)
        return cls(
            recording=_as_model_recording(recording),
            provenance=generated.Provenance(
                source_format="tdms", source_format_version=version, reader=software_id()
            ),
        )

    @classmethod
    def from_file(cls, path: str) -> DatasetBundle:
        """Load a DatasetBundle from an HDF5 or TDMS file, told apart by the
        file's first bytes (not its name)."""
        with open(path, "rb") as f:
            head = f.read(8)
        if head.startswith(TDMS_SIGNATURE):
            return cls.from_tdms(path)
        if head == HDF5_SIGNATURE:
            return cls.from_hdf5(path)
        raise ValueError(f"{path!r} is neither an HDF5 nor a TDMS file")

    def to_hdf5(self, path: str, *, format_version: FormatVersion | None = None) -> None:
        """Write this bundle (recording, preprocessed tables, every
        computation) to a fresh HDF5 file.

        `format_version` picks the file format version; by default it is the oldest one that can hold the
        bundle (so files stay readable by older readers). Raises `ValueError`, before writing anything, if
        the version is unknown or can't hold the bundle (e.g. steps in "1.1"). See `hdf5_format_versions()`.

        See ICOschema.storage.python.hdf5 for the file layout this
        produces -- each computation is stored in its true N-D shape under
        a `/computations/` group. Raises `ValueError` if a preprocessed
        table doesn't fit its source (see `with_preprocessed`).
        """
        from icoschema.storage.python import hdf5

        recording = _as_model_recording(self.recording)
        for table in self._tables():
            validate_preprocessed(cast(Source, recording.sources[str(table.source)]), table)
        validate_steps(self._steps(), self.computations, recording)
        hdf5.save_dataset_bundle(self, path, format_version=format_version)

    # ── preprocessed ───────────────────────────────────────────────────────

    @property
    def preprocessed(self) -> PreprocessedRecording | None:
        """The preprocessed table of the only source, or `None` if it has none.
        Raises `ValueError` if the recording has several sources -- use
        `preprocessed_for(source)`."""
        sources = self.recording.sources
        if len(sources) != 1:
            raise ValueError(
                f"recording has {len(sources)} sources ({[str(name) for name in sources]}); "
                "use preprocessed_for(source)"
            )
        return self.preprocessed_for(str(next(iter(sources))))

    def preprocessed_for(self, source: str) -> PreprocessedRecording | None:
        """The preprocessed table of `source`, or `None` if it has none.
        Raises `ValueError` for an unknown source."""
        if source not in self.recording.sources:
            raise ValueError(f"no such source: {source!r}")
        for table in self._tables():
            if table.source == source:
                return table
        return None

    def with_recording(self, recording: Recording) -> DatasetBundle:
        """A copy of this bundle with `recording` replaced.

        Raises `ValueError` while the bundle has a preprocessed table or
        any `steps`, which were built from the current recording and would
        silently go stale -- drop them first (`without_preprocessed()`,
        `without_steps(...)`).
        """
        if self.preprocessed_tables:
            raise ValueError(
                "cannot replace the recording of a bundle with a preprocessed table "
                "(it was built from the current recording) -- call without_preprocessed() first"
            )
        if self.steps:
            raise ValueError(
                "cannot replace the recording of a bundle with computation steps "
                "(they were computed from the current recording) -- call without_steps() first"
            )
        return DatasetBundle(
            recording=recording, computations=dict(self.computations), provenance=self.provenance
        )

    def with_preprocessed(
        self, preprocessed: generated.PreprocessedRecording, source: str | None = None
    ) -> DatasetBundle:
        """A copy of this bundle with `preprocessed` set (added, or replacing
        that source's table).

        The source is `source`, else `preprocessed.source`, else the
        recording's only source; it's an error to name two different ones, or
        to name none for a recording with several. Raises `ValueError` if the
        table doesn't fit that source (see `validate_preprocessed`).
        """
        recording = _as_model_recording(self.recording)
        model_preprocessed = _as_model_preprocessed(preprocessed)
        if source is not None and model_preprocessed.source not in (None, source):
            raise ValueError(f"table is for source {model_preprocessed.source!r}, not {source!r}")
        name = source if source is not None else model_preprocessed.source
        if name is None:
            if len(recording.sources) != 1:
                raise ValueError(
                    f"recording has {len(recording.sources)} sources ({[str(n) for n in recording.sources]}); "
                    "say which one the preprocessed table is for"
                )
            name = str(next(iter(recording.sources)))
        if name not in recording.sources:
            raise ValueError(f"no such source: {name!r}")
        model_preprocessed = dataclasses.replace(model_preprocessed, source=name)
        validate_preprocessed(cast(Source, recording.sources[name]), model_preprocessed)
        kept = [table for table in self._tables() if table.source != name]
        order = [str(n) for n in recording.sources]
        tables = sorted([*kept, model_preprocessed], key=lambda table: order.index(str(table.source)))
        return self._copy(preprocessed_tables=tables)

    def without_preprocessed(self, source: str | None = None) -> DatasetBundle:
        """A copy of this bundle without the preprocessed table of `source`,
        or without any if none is named (steps and computations are kept --
        dropping what was computed from the table is up to the caller).
        Raises `ValueError` if `source` is unknown or has no table."""
        if source is None:
            return self._copy(preprocessed_tables=[])
        if self.preprocessed_for(source) is None:
            raise ValueError(f"source {source!r} has no preprocessed table")
        return self._copy(preprocessed_tables=[table for table in self._tables() if table.source != source])

    # ── computations and steps ────────────────────────────────────────────

    def with_computation(self, key: str, derived: DerivedDataset) -> DatasetBundle:
        """A copy of this bundle with one computation added/replaced under
        `key`."""
        computations = dict(self.computations)
        computations[key] = derived
        return self._copy(computations=computations)

    def with_step(self, step: ComputationStep) -> DatasetBundle:
        """A copy of this bundle with `step` appended as the last step.

        `step.step_index` is assigned here (`len(steps)`); whatever it was is
        overwritten. Raises `ValueError` if `step.node` is already taken or
        isn't a single HDF5 path segment, or if an `output_keys` entry isn't
        in `computations` -- add the step's computations first.
        """
        appended = dataclasses.replace(step, step_index=len(self.steps))
        steps = [*self._steps(), appended]
        validate_steps(steps, self.computations, _as_model_recording(self.recording))
        return self._copy(steps=steps)

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
        return self._copy(
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

    def source_of(self, node: str) -> str | None:
        """The name of the Source that `node` ultimately comes from.

        `node` is anything a step can name in `source_node`: a Source name,
        "preprocessed" (single source only), "preprocessed:<source>" or the
        `node` of a recorded step, which is followed back through its
        `source_node` (or its `inputs`, if they all share one source) to its
        root. Returns `None` for a step that can't be traced to one source
        (e.g. one over inputs from several sources). Raises `ValueError` for a name
        that is none of these -- including a step that wasn't recorded."""
        sources = [str(name) for name in self.recording.sources]
        steps = {str(step.node): step for step in self._steps()}
        seen: set[str] = set()
        current: str | None = node
        while True:
            if current is None:
                return sources[0] if len(sources) == 1 else None
            if current in sources:
                return current
            if current == PREPROCESSED_NODE:
                if len(sources) != 1:
                    raise ValueError(f"{PREPROCESSED_NODE!r} is ambiguous with sources {sources}; name one")
                return sources[0]
            if current.startswith(PREPROCESSED_PREFIX):
                name = current[len(PREPROCESSED_PREFIX) :]
                if name not in sources:
                    raise ValueError(f"{current!r} names unknown source {name!r}")
                return name
            if current not in steps or current in seen:
                raise ValueError(f"{current!r} is not a source, a preprocessed table or a recorded step")
            seen.add(current)
            step = steps[current]
            if step.source_node is not None:
                current = str(step.source_node)
            elif step.inputs:
                origins = {self.source_of(str(name)) for name in step.inputs}
                return origins.pop() if len(origins) == 1 else None
            else:
                current = None

    def computations_for_source(self, source: str) -> dict[str, DerivedDataset]:
        """The computations of the steps that trace back to `source` (see
        `source_of`), by key. Raises `ValueError` for an unknown source."""
        if source not in self.recording.sources:
            raise ValueError(f"no such source: {source!r}")
        found: dict[str, DerivedDataset] = {}
        for step in self._steps():
            try:
                origin = self.source_of(str(step.node))
            except ValueError:
                continue
            if origin == source:
                found.update({key: self.computations[key] for key in step.output_keys})
        return found

    def unmanaged_keys(self) -> set[str]:
        """Computation keys no step lists in its `output_keys` (e.g. from
        older files or code that adds computations without recording a step)."""
        managed = {key for step in self._steps() for key in step.output_keys}
        return set(self.computations) - managed

    def _copy(self, **changes: Any) -> DatasetBundle:
        fields: dict[str, Any] = {
            "recording": self.recording,
            "preprocessed_tables": list(self._tables()),
            "computations": dict(self.computations),
            "steps": list(self._steps()),
            "provenance": self.provenance,
        }
        fields.update(changes)
        return DatasetBundle(**fields)

    def _steps(self) -> list[ComputationStep]:
        """`steps`, typed: the generated field also admits dict/str forms
        before `__post_init__` normalizes it to a list."""
        return cast(list[ComputationStep], self.steps)

    def _tables(self) -> list[PreprocessedRecording]:
        """`preprocessed_tables`, typed (see `_steps`)."""
        return cast(list[PreprocessedRecording], self.preprocessed_tables)


def validate_preprocessed(source: Source, preprocessed: generated.PreprocessedRecording) -> None:
    """Raises `ValueError` unless `preprocessed` fits `source`: one row
    per gap-free grid position (`source.sample_index()[-1] + 1`), the same
    set of channels, every column of equal length, and a positive finite
    `channel_sampling_frequency`."""
    grid_length = int(source.sample_index()[-1]) + 1
    raw_channels = [name for name in _CHANNELS if getattr(source, name).size > 0]
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


def validate_steps(
    steps: list[ComputationStep], computations: dict[str, DerivedDataset], recording: Recording | None = None
) -> None:
    """Raises `ValueError` unless `steps` are numbered 0, 1, 2, ... in order,
    every node name is unique and a single HDF5 path segment, and every
    `output_keys` entry is in `computations`. Step names share one namespace
    with the reserved "preprocessed" names and, given `recording`, its source
    names; a `source_node` of the form "preprocessed:<source>" must name one
    of its sources. (Whether a `source_node` names a recorded step is never
    checked: that step may have failed and not been recorded.)"""
    source_names = {str(name) for name in recording.sources} if recording is not None else set()
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
        if node == PREPROCESSED_NODE or node.startswith(PREPROCESSED_PREFIX) or node in source_names:
            raise ValueError(f"step name {node!r} is reserved: it names a source or a preprocessed table")
        origin = step.source_node
        if (
            recording is not None
            and origin is not None
            and origin.startswith(PREPROCESSED_PREFIX)
            and origin[len(PREPROCESSED_PREFIX) :] not in source_names
        ):
            raise ValueError(f"step {node!r} reads {origin!r}, but there is no such source")


def _as_model_recording(recording: generated.Recording) -> Recording:
    if isinstance(recording, Recording):
        return recording
    return Recording(sources=list(recording.sources.values()))


def _as_model_preprocessed(preprocessed: generated.PreprocessedRecording) -> PreprocessedRecording:
    if isinstance(preprocessed, PreprocessedRecording):
        return preprocessed
    return PreprocessedRecording(
        source=preprocessed.source,
        timestamp=preprocessed.timestamp,
        channel1=preprocessed.channel1,
        channel2=preprocessed.channel2,
        channel3=preprocessed.channel3,
        channel_sampling_frequency=preprocessed.channel_sampling_frequency,
        sampling_frequency_source=preprocessed.sampling_frequency_source,
        fill_method=preprocessed.fill_method,
        producer=preprocessed.producer,
    )
