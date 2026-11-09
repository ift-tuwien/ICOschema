"""Tests for multi-source recordings (one source per STU/STH combination)."""

import json

import h5py
import pytest

from icoschema.model.python.dataset_bundle import DatasetBundle
from icoschema.model.python.preprocessed_recording import PreprocessedRecording
from icoschema.model.python.recording import DEFAULT_SOURCE_NAME, Recording, Source
from icoschema.schema.generated.python import dataset as generated


def _source(name: str, *, counter: list[int], start_time: str, adc: tuple[int, int, int] | None = None, **ids) -> Source:
    channel = generated.ChannelMetadata(
        sensor=generated.Sensor(sensor_id=f"sensor_{name}", unit="g"), compensations=[generated.NoConversion(order=0)]
    )
    prescaler, acquisition_time, oversample_rate = adc or (None, None, None)
    return Source(
        name=name,
        hardware_metadata=generated.HardwareMetadata(
            adc_prescaler=prescaler,
            adc_acquisition_time=acquisition_time,
            adc_oversample_rate=oversample_rate,
            channel1_metadata=channel,
        ),
        recording_metadata=generated.RecordingMetadata(start_time=start_time),
        recording_data=generated.RecordingData(
            timestamp=[i * 100 for i in range(len(counter))], counter=counter, channel1=[float(c) for c in counter]
        ),
        **ids,
    )


def _two_sources() -> Recording:
    return Recording(
        sources=[
            _source("a", counter=[0, 1, 2, 3], start_time="2026-01-01T00:00:00", stu_id="stu1", sth_id="sth1"),
            # Own clock, own ADC settings (half the default rate), and lost packets.
            _source("b", counter=[0, 1, 3, 4], start_time="2026-01-01T00:00:07", adc=(5, 8, 64), stu_id="stu2"),
        ]
    )


def test_sources_are_keyed_by_name_and_are_model_sources():
    recording = _two_sources()
    assert list(recording.sources) == ["a", "b"]
    assert all(isinstance(source, Source) for source in recording.sources.values())
    assert recording.sources["b"].stu_id == "stu2"
    assert recording.sources["b"].sth_id is None


def test_sources_have_independent_clocks_loss_and_sampling_frequency():
    a, b = _two_sources().sources["a"], _two_sources().sources["b"]
    assert a.recording_metadata.start_time != b.recording_metadata.start_time
    assert a.signal_loss_percentage == 0
    assert b.signal_loss_percentage > 0
    (fs_a, source_a), (fs_b, source_b) = a.channel_sampling_frequency(), b.channel_sampling_frequency()
    assert (source_a, source_b) == ("default", "hardware")
    assert fs_a == pytest.approx(38_400_000 / (3 * 21 * 64))
    assert fs_b == pytest.approx(38_400_000 / (6 * 21 * 64))


def test_single_source_shortcuts_raise_for_several_sources():
    recording = _two_sources()
    for access in (
        lambda: recording.channel1,
        lambda: recording.hardware_metadata,
        lambda: recording.signal_loss_percentage,
        lambda: recording.channel_sampling_frequency(),
        lambda: recording.to_dataframe(),
    ):
        with pytest.raises(ValueError, match=r"2 sources .*'a'.*'b'"):
            access()
    assert list(recording.to_dataframe(source="b").columns) == ["timestamp", "counter", "channel1"]


def test_legacy_constructor_makes_one_default_source():
    source = _source("x", counter=[0, 1], start_time="2026-01-01T00:00:00")
    recording = Recording(
        hardware_metadata=source.hardware_metadata,
        recording_metadata=source.recording_metadata,
        recording_data=source.recording_data,
    )
    assert list(recording.sources) == [DEFAULT_SOURCE_NAME]
    assert list(recording.channel1) == [0.0, 1.0]
    with pytest.raises(TypeError):
        Recording(hardware_metadata=source.hardware_metadata)


def test_generated_sources_are_converted_and_names_validated():
    plain = generated.Source(**{f: getattr(_source("a", counter=[0], start_time="t"), f) for f in
                                ("name", "hardware_metadata", "recording_metadata", "recording_data")})
    assert isinstance(Recording(sources=[plain]).sources["a"], Source)
    for bad in ("", "a/b", ".hidden"):
        with pytest.raises(ValueError, match="source name"):
            _source(bad, counter=[0], start_time="t")


def test_summary_is_per_source_for_several_sources_and_json_encodable():
    summary = _two_sources().summary()
    assert set(summary["sources"]) == {"a", "b"}
    assert summary["sources"]["a"]["stu_id"] == "stu1"
    assert summary["sources"]["b"]["start_time"] == "2026-01-01T00:00:07"
    json.dumps(summary)
    # A single source keeps the flat shape.
    assert "channels" in Recording(sources=[_source("a", counter=[0, 1], start_time="t")]).summary()


def test_single_source_name_and_ids_round_trip_through_hdf5(tmp_path):
    original = Recording(sources=[_source("tool", counter=[0, 1, 2], start_time="2026-01-01T00:00:00",
                                          stu_id="stu9", sth_id="sth9")])
    path = tmp_path / "one.hdf5"
    original.to_hdf5(str(path))
    reloaded = Recording.from_hdf5(str(path))
    source = reloaded.sources["tool"]
    assert (source.stu_id, source.sth_id) == ("stu9", "sth9")

    # The default name isn't stored, and reads back as the default.
    default = Recording(sources=[_source(DEFAULT_SOURCE_NAME, counter=[0, 1], start_time="t")])
    default.to_hdf5(str(path))
    assert list(Recording.from_hdf5(str(path)).sources) == [DEFAULT_SOURCE_NAME]


def _version(path) -> str:
    with h5py.File(path, "r") as f:
        return f.attrs["icoschema_format_version"]


def test_several_sources_round_trip_as_format_1_3(tmp_path):
    original = _two_sources()
    path = tmp_path / "two.hdf5"
    original.to_hdf5(str(path))
    assert _version(path) == "1.3"

    reloaded = Recording.from_hdf5(str(path))
    assert list(reloaded.sources) == ["a", "b"]  # order kept, not alphabetical-by-accident
    for name in ("a", "b"):
        before, after = original.sources[name], reloaded.sources[name]
        assert after.recording_metadata.start_time == before.recording_metadata.start_time
        assert (after.stu_id, after.sth_id) == (before.stu_id, before.sth_id)
        assert after.recording_data.counter == before.recording_data.counter
        assert after.recording_data.timestamp == before.recording_data.timestamp
        assert after.recording_data.channel1 == pytest.approx(before.recording_data.channel1)
        assert after.hardware_metadata.channel1_metadata.sensor.sensor_id == f"sensor_{name}"
    # Per-source ADC settings survive, so sampling frequencies still differ.
    assert reloaded.sources["a"].channel_sampling_frequency()[1] == "default"
    assert reloaded.sources["b"].channel_sampling_frequency()[1] == "hardware"


def test_source_order_is_not_alphabetical(tmp_path):
    recording = Recording(
        sources=[_source("z", counter=[0, 1], start_time="t"), _source("a", counter=[0, 1], start_time="t")]
    )
    recording.to_hdf5(str(tmp_path / "order.hdf5"))
    assert list(Recording.from_hdf5(str(tmp_path / "order.hdf5")).sources) == ["z", "a"]


def test_single_source_keeps_the_old_layout(tmp_path):
    Recording(sources=[_source("a", counter=[0, 1], start_time="t")]).to_hdf5(str(tmp_path / "one.hdf5"))
    assert _version(tmp_path / "one.hdf5") == "1.0"


def test_bundle_with_sources_steps_and_computations_round_trips(tmp_path):
    derived = generated.DerivedDataset(key="rms/a", values=[1.0, 2.0], shape=[2], dtype="float64")
    bundle = DatasetBundle(recording=_two_sources()).with_computation("rms/a", derived)
    bundle = bundle.with_step(generated.ComputationStep(node="rms", step_index=0, producer="rms@1", output_keys=["rms/a"]))
    path = tmp_path / "bundle.hdf5"
    bundle.to_hdf5(str(path))
    assert _version(path) == "1.3"

    reloaded = DatasetBundle.from_hdf5(str(path), on_error="raise")
    assert list(reloaded.recording.sources) == ["a", "b"]
    assert list(reloaded.computations) == ["rms/a"]
    assert [str(step.node) for step in reloaded.steps] == ["rms"]


def _table(length: int, fs: float, source: str | None = None, **overrides) -> PreprocessedRecording:
    return PreprocessedRecording(
        source=source,
        timestamp=[round(i * 1e6 / fs) for i in range(length)],
        channel1=[float(i) for i in range(length)],
        channel_sampling_frequency=fs,
        sampling_frequency_source="default",
        fill_method="forward_fill",
        producer="test@1",
        **overrides,
    )


def _preprocessed_bundle() -> DatasetBundle:
    # "a" has a 4-row gap-free grid, "b" (one lost packet) has 5.
    bundle = DatasetBundle(recording=_two_sources())
    return bundle.with_preprocessed(_table(4, 9523.8, "a")).with_preprocessed(_table(5, 4761.9), source="b")


def test_preprocessed_tables_are_per_source():
    bundle = _preprocessed_bundle()
    assert [t.source for t in bundle.preprocessed_tables] == ["a", "b"]
    assert len(bundle.preprocessed_for("a")) == 4
    assert len(bundle.preprocessed_for("b")) == 5
    assert bundle.preprocessed_for("b").channel_sampling_frequency == pytest.approx(4761.9)
    assert bundle.without_preprocessed().preprocessed_tables == []
    only_a = bundle.without_preprocessed("b")
    assert only_a.preprocessed_for("b") is None and only_a.preprocessed_for("a") is not None
    # Replacing a source's table keeps one table per source.
    assert len(bundle.with_preprocessed(_table(4, 1.0, "a")).preprocessed_tables) == 2


def test_preprocessed_needs_an_unambiguous_source_that_fits():
    bundle = DatasetBundle(recording=_two_sources())
    with pytest.raises(ValueError, match="say which one"):
        bundle.with_preprocessed(_table(4, 1.0))
    with pytest.raises(ValueError, match="not 'b'"):
        bundle.with_preprocessed(_table(4, 1.0, "a"), source="b")
    with pytest.raises(ValueError, match="no such source"):
        bundle.with_preprocessed(_table(4, 1.0), source="nope")
    with pytest.raises(ValueError, match="rows"):  # b's grid has 5 rows, not 4
        bundle.with_preprocessed(_table(4, 1.0), source="b")
    with pytest.raises(ValueError, match="several sources|2 sources"):
        _ = bundle.preprocessed
    with pytest.raises(ValueError, match="no such source"):
        bundle.preprocessed_for("nope")
    with pytest.raises(ValueError, match="no preprocessed table"):
        bundle.without_preprocessed("a")
    with pytest.raises(ValueError, match="preprocessed table"):
        _preprocessed_bundle().with_recording(_two_sources())


def test_single_source_preprocessed_shortcuts_keep_working():
    recording = Recording(sources=[_source("tool", counter=[0, 1, 2], start_time="t")])
    table = _table(3, 1.0)
    for bundle in (
        DatasetBundle(recording=recording, preprocessed=table),
        DatasetBundle(recording=recording).with_preprocessed(table),
    ):
        assert bundle.preprocessed.source == "tool"
        assert bundle.preprocessed_tables == [bundle.preprocessed]
    assert DatasetBundle(recording=recording).preprocessed is None


def test_preprocessed_tables_round_trip_per_source_as_1_3(tmp_path):
    path = str(tmp_path / "pre.hdf5")
    _preprocessed_bundle().to_hdf5(path)
    assert _version(path) == "1.3"
    reloaded = DatasetBundle.from_hdf5(path)
    assert [t.source for t in reloaded.preprocessed_tables] == ["a", "b"]
    assert reloaded.preprocessed_for("b").channel1 == [0.0, 1.0, 2.0, 3.0, 4.0]
    assert reloaded.preprocessed_for("a").channel_sampling_frequency == pytest.approx(9523.8)

    # Only some sources preprocessed.
    _preprocessed_bundle().without_preprocessed("a").to_hdf5(path)
    reloaded = DatasetBundle.from_hdf5(path)
    assert [t.source for t in reloaded.preprocessed_tables] == ["b"]


def test_single_source_preprocessed_still_writes_1_1_and_keeps_the_source(tmp_path):
    recording = Recording(sources=[_source("tool", counter=[0, 1, 2], start_time="t")])
    path = str(tmp_path / "one.hdf5")
    DatasetBundle(recording=recording, preprocessed=_table(3, 1.0)).to_hdf5(path)
    assert _version(path) == "1.1"
    assert DatasetBundle.from_hdf5(path).preprocessed.source == "tool"


def test_a_table_for_a_source_the_file_lacks_is_rejected(tmp_path):
    path = str(tmp_path / "pre.hdf5")
    _preprocessed_bundle().to_hdf5(path)
    with h5py.File(path, "a") as f:
        del f["sources"]["a"]["preprocessed"]
        del f["sources"]["b"]["preprocessed"]
    with pytest.raises(ValueError, match="does not exist"):
        DatasetBundle.from_hdf5(path)


def _derived(key: str) -> generated.DerivedDataset:
    return generated.DerivedDataset(key=key, values=[1.0, 2.0], shape=[2], dtype="float64")


def _written(tmp_path) -> str:
    path = str(tmp_path / "two.hdf5")
    _two_sources().to_hdf5(path)
    return path


def test_a_listed_source_without_a_group_is_rejected(tmp_path):
    path = _written(tmp_path)
    with h5py.File(path, "a") as f:
        del f["sources"]["b"]
    with pytest.raises(ValueError, match="no group"):
        Recording.from_hdf5(path)


def test_an_empty_or_duplicated_sources_list_is_rejected(tmp_path):
    path = _written(tmp_path)
    with h5py.File(path, "a") as f:
        f.attrs.create("sources", ["a", "a"], dtype=h5py.string_dtype())
    with pytest.raises(ValueError, match="duplicate"):
        Recording.from_hdf5(path)
    with h5py.File(path, "a") as f:
        f.attrs.create("sources", [], dtype=h5py.string_dtype())
    with pytest.raises(ValueError, match="at least one"):
        Recording.from_hdf5(path)


def test_an_unlisted_group_is_ignored_with_a_warning(tmp_path, caplog):
    path = _written(tmp_path)
    with h5py.File(path, "a") as f:
        f["sources"].create_group("stray")
    assert list(Recording.from_hdf5(path).sources) == ["a", "b"]
    assert "stray" in caplog.text


def _step(node: str, **fields) -> generated.ComputationStep:
    return generated.ComputationStep(node=node, step_index=0, producer="rms@1", **fields)


def _chain() -> DatasetBundle:
    """rms_a (on a's preprocessed table) -> smooth_a; rms_b on b's; one step reading both raw sources."""
    bundle = DatasetBundle(recording=_two_sources())
    for key in ("rms_a/channel1", "smooth_a/channel1", "rms_b/channel1", "both/channel1"):
        bundle = bundle.with_computation(key, _derived(key))
    bundle = bundle.with_step(_step("rms_a", source_node="preprocessed:a", output_keys=["rms_a/channel1"]))
    bundle = bundle.with_step(
        _step("smooth_a", source_node="rms_a", inputs=["rms_a"], output_keys=["smooth_a/channel1"])
    )
    bundle = bundle.with_step(_step("rms_b", source_node="b", output_keys=["rms_b/channel1"]))
    return bundle.with_step(_step("both", inputs=["a", "b"], output_keys=["both/channel1"]))


def test_source_nodes_round_trip_and_trace_back_to_their_source(tmp_path):
    path = str(tmp_path / "steps.hdf5")
    _chain().to_hdf5(path)
    bundle = DatasetBundle.from_hdf5(path, on_error="raise")
    assert [(s.node, s.source_node) for s in bundle.steps] == [
        ("rms_a", "preprocessed:a"), ("smooth_a", "rms_a"), ("rms_b", "b"), ("both", None),
    ]
    assert [bundle.source_of(n) for n in ("a", "preprocessed:b", "rms_a", "smooth_a", "rms_b")] == [
        "a", "b", "a", "a", "b",
    ]
    assert bundle.source_of("both") is None  # reads both sources
    assert list(bundle.computations_for_source("a")) == ["rms_a/channel1", "smooth_a/channel1"]
    assert list(bundle.computations_for_source("b")) == ["rms_b/channel1"]


def test_source_of_rejects_unknown_and_ambiguous_names():
    bundle = _chain()
    for name in ("nope", "preprocessed:nope", "preprocessed"):
        with pytest.raises(ValueError):
            bundle.source_of(name)
    with pytest.raises(ValueError, match="no such source"):
        bundle.computations_for_source("nope")


def test_source_of_for_a_single_source_recording():
    bundle = DatasetBundle(recording=Recording(sources=[_source(DEFAULT_SOURCE_NAME, counter=[0, 1], start_time="t")]))
    bundle = bundle.with_step(_step("raw"))
    assert bundle.source_of("preprocessed") == bundle.source_of("raw") == DEFAULT_SOURCE_NAME


def test_source_node_is_not_checked_against_recorded_steps():
    # Names a step that was never recorded (e.g. it failed): allowed.
    bundle = DatasetBundle(recording=_two_sources())
    bundle = bundle.with_step(_step("skipped", source_node="failed_upstream", inputs=["failed_upstream"]))
    assert bundle.steps[0].source_node == "failed_upstream"


def test_step_names_may_not_collide_with_sources_or_preprocessed_names():
    bundle = DatasetBundle(recording=_two_sources())
    for name in ("a", "preprocessed", "preprocessed:a"):
        with pytest.raises(ValueError, match="reserved"):
            bundle.with_step(_step(name))
    with pytest.raises(ValueError, match="no such source"):
        bundle.with_step(_step("x", source_node="preprocessed:nope"))
