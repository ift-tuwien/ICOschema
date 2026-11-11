"""The v1 -> v2 migration (`icoschema.migrate`): every channel becomes a LinearConversion, whatever v1 said."""

from pathlib import Path

import h5py
import pytest

from icoschema import migrate, v1, v2

ROOT = Path(__file__).resolve().parent
V1_DATA = ROOT / "v1" / "data"
FIXTURE = ROOT / "v1" / "test_with_sensors.hdf5"


def sensor(**changes) -> v1.Sensor:
    values = {"sensor_id": "s1", "unit": "g", "phys_min": -100.0, "phys_max": 100.0, "volt_min": 0.33, "volt_max": 2.97}
    return v1.Sensor(**{**values, **changes})


def channel(compensation, **sensor_changes) -> v1.ChannelMetadata:
    return v1.ChannelMetadata(sensor=sensor(**sensor_changes), compensations=[compensation])


def convert(metadata: v1.ChannelMetadata, stored: migrate.Scaling | None = None) -> v2.LinearConversion:
    ctx = migrate._Context(stored={"a": [stored]} if stored else {}, source="a")
    return migrate._migrate_conversion(metadata, ctx)


def test_the_range_gives_gain_and_offset_as_delta_phys_over_delta_volt() -> None:
    conversion = migrate.linear_from_range(sensor())
    assert conversion.gain == pytest.approx(200.0 / 2.64)
    assert conversion.offset == pytest.approx(-100.0 - conversion.gain * 0.33)
    # the ends of the range map onto each other
    assert conversion.gain * 0.33 + conversion.offset == pytest.approx(-100.0)
    assert conversion.gain * 2.97 + conversion.offset == pytest.approx(100.0)


@pytest.mark.parametrize("missing", ["phys_min", "phys_max", "volt_min", "volt_max"])
def test_an_incomplete_range_cannot_give_a_conversion(missing: str) -> None:
    with pytest.raises(ValueError, match="no complete phys/volt range"):
        migrate.linear_from_range(sensor(**{missing: None}))


def test_an_empty_voltage_range_cannot_give_a_conversion() -> None:
    with pytest.raises(ValueError, match="volt_min == volt_max"):
        migrate.linear_from_range(sensor(volt_min=1.0, volt_max=1.0))


def test_the_stored_scaling_wins_over_everything() -> None:
    metadata = channel(v1.LinearConversion(order=0, gain=2.0, offset=3.0))
    assert convert(metadata, (5.0, 6.0)) == v2.LinearConversion(gain=5.0, offset=6.0)
    # also for a channel v1 called NoConversion (the file said "already converted")
    assert convert(channel(v1.NoConversion(order=0)), (5.0, 6.0)) == v2.LinearConversion(gain=5.0, offset=6.0)


def test_a_linear_conversion_without_stored_scaling_is_kept() -> None:
    metadata = channel(v1.LinearConversion(order=0, gain=2.0, offset=3.0), phys_min=None)
    assert convert(metadata) == v2.LinearConversion(gain=2.0, offset=3.0)


def test_no_conversion_without_stored_scaling_takes_the_range() -> None:
    assert convert(channel(v1.NoConversion(order=0))) == migrate.linear_from_range(sensor())


def test_no_conversion_without_scaling_or_range_is_gain_one_offset_zero() -> None:
    metadata = channel(v1.NoConversion(order=0), phys_min=None)
    assert convert(metadata) == v2.LinearConversion(gain=1.0, offset=0.0)
    assert convert(channel(v1.NoConversion(order=0), phys_min=None, volt_max=None)) == v2.LinearConversion(gain=1.0, offset=0.0)


def test_a_stored_scaling_that_differs_from_the_range_is_kept_with_a_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING"):
        assert convert(channel(v1.NoConversion(order=0)), (2.0, 3.0)) == v2.LinearConversion(gain=2.0, offset=3.0)
    assert "keeping the stored one" in caplog.text


def test_a_stored_scaling_matching_the_range_is_silent(caplog: pytest.LogCaptureFixture) -> None:
    derived = migrate.linear_from_range(sensor())
    with caplog.at_level("WARNING"):
        convert(channel(v1.NoConversion(order=0)), (derived.gain, derived.offset))
    assert not caplog.records


def test_a_polynomial_of_degree_one_is_linear() -> None:
    metadata = channel(v1.PolynomialConversion(order=0, coefficients=[3.0, 2.0]), phys_min=None)
    assert convert(metadata) == v2.LinearConversion(gain=2.0, offset=3.0)


@pytest.mark.parametrize(
    "compensations",
    [
        [v1.PolynomialConversion(order=0, coefficients=[1.0, 2.0, 3.0])],
        [v1.LinearConversion(order=0, gain=1.0, offset=0.0), v1.LinearConversion(order=1, gain=2.0, offset=0.0)],
    ],
)
def test_what_v2_cannot_represent_raises(compensations) -> None:
    metadata = v1.ChannelMetadata(sensor=sensor(), compensations=compensations)
    with pytest.raises(ValueError, match="cannot be migrated|no v2 form"):
        convert(metadata)


def test_the_real_file_ignores_its_conversion_attribute(tmp_path: Path) -> None:
    """The file says conversion = "true" (v1 reads NoConversion), but is migrated with its stored scaling."""
    assert h5py.File(FIXTURE)["acceleration"].attrs["conversion"] == b"true"
    destination = tmp_path / "converted.hdf5"
    migrate.convert_file(str(FIXTURE), str(destination))
    migrated = v2.DatasetBundle.from_hdf5(str(destination), on_error="raise")
    source = next(iter(migrated.recording.sources.values()))
    conversion = source.hardware_metadata.channel1_metadata.conversion
    assert isinstance(conversion, v2.LinearConversion)
    assert conversion.gain == pytest.approx(75.757576, rel=1e-6)  # the file's scaling_factor
    assert conversion.offset == pytest.approx(-125.0, rel=1e-6)
    assert not hasattr(source.hardware_metadata.channel1_metadata.sensor, "phys_min")


def test_the_values_are_not_changed() -> None:
    bundle = v1.DatasetBundle.from_hdf5(str(FIXTURE))
    old = next(iter(bundle.recording.sources.values()))
    new = next(iter(migrate.v1_to_v2(bundle).recording.sources.values()))
    assert new.recording_data.channel1 == old.recording_data.channel1
    assert new.recording_data.timestamp == old.recording_data.timestamp


def test_the_ids_become_macs() -> None:
    bundle = v1.DatasetBundle.from_hdf5(str(V1_DATA / "hdf5_1.4_1ch.hdf5"))
    old = next(iter(bundle.recording.sources.values()))
    new = next(iter(migrate.v1_to_v2(bundle).recording.sources.values()))
    assert (new.stu_mac, new.sth_mac, new.description) == (old.stu_id, old.sth_id, None)


def test_a_tdms_file_gets_gain_one_offset_zero(tmp_path: Path) -> None:
    destination = tmp_path / "converted.hdf5"
    migrate.convert_file(str(V1_DATA / "tdms_legacy_3ch.tdms"), str(destination))
    source = next(iter(v2.DatasetBundle.from_hdf5(str(destination)).recording.sources.values()))
    for slot in ("channel1_metadata", "channel2_metadata", "channel3_metadata"):
        assert getattr(source.hardware_metadata, slot).conversion == v2.LinearConversion(gain=1.0, offset=0.0)


@pytest.mark.parametrize("path", sorted(V1_DATA.glob("hdf5_*")), ids=lambda p: p.name)
def test_every_stored_v1_hdf5_file_gets_its_stored_scalings(path: Path, tmp_path: Path) -> None:
    destination = tmp_path / "converted.hdf5"
    migrate.convert_file(str(path), str(destination))
    converted = v2.DatasetBundle.from_hdf5(str(destination), on_error="raise")
    original = v1.DatasetBundle.from_file(str(path))
    stored = migrate.stored_scalings_of(str(path), original)
    assert list(converted.recording.sources) == list(original.recording.sources)
    for name, old in original.recording.sources.items():
        new = converted.recording.sources[name]
        assert new.recording_data.timestamp == old.recording_data.timestamp
        assert new.recording_data.channel1 == pytest.approx(old.recording_data.channel1)
        for index, slot in enumerate(("channel1_metadata", "channel2_metadata", "channel3_metadata")):
            conversion = getattr(new.hardware_metadata, slot)
            if conversion is None:
                continue
            conversion = conversion.conversion
            assert isinstance(conversion, v2.LinearConversion)
            if str(name) in stored:
                gain, offset = stored[str(name)][index]
                assert (conversion.gain, conversion.offset) == pytest.approx((gain, offset))
    assert len(converted.steps) == len(original.steps)
    assert set(converted.computations) == set(original.computations)


@pytest.mark.parametrize("path", sorted(V1_DATA.glob("tdms_*")), ids=lambda p: p.name)
def test_every_stored_v1_tdms_file_converts(path: Path, tmp_path: Path) -> None:
    destination = tmp_path / "converted.hdf5"
    migrate.convert_file(str(path), str(destination))
    converted = v2.DatasetBundle.from_hdf5(str(destination), on_error="raise")
    assert list(converted.recording.sources) == list(v1.DatasetBundle.from_file(str(path)).recording.sources)
