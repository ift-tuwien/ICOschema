"""Migration of schema version 1 data to schema version 2.

    from icoschema import migrate, v1

    bundle_v2 = migrate.v1_to_v2(v1.DatasetBundle.from_file("old.hdf5"))
    migrate.convert_file("old.hdf5", "new.hdf5")           # read with v1, write with v2

What changes (see icoschema/v2/schema/dataset.yaml):

- `Source.stu_id`/`sth_id` become `stu_mac`/`sth_mac` (the same values); `Source.description` is left unset.
- `Sensor.phys_min`/`phys_max`/`volt_min`/`volt_max` are dropped, and each channel gets a required `conversion`
  in place of the `compensations` list. Every channel of a v1 file becomes a `LinearConversion` (from ADC voltage
  to the sensor's unit), whatever its v1 conversion or the file's `conversion` attribute says: v1 files were
  never written with a usable one (the attribute and `NoConversion` are not trusted). Gain and offset are, in
  this order:

  1. the channel's `scaling_factor` and `offset` in the file's `sensors` table (`convert_file` reads them; a
     bundle no longer has them when the file said "already converted");
  2. the gain and offset of a v1 `LinearConversion` of the channel;
  3. the sensor's range, `gain = (phys_max - phys_min) / (volt_max - volt_min)` and
     `offset = phys_min - gain * volt_min`;
  4. `gain = 1`, `offset = 0` when none of that is there (e.g. a TDMS file).

  A `PolynomialConversion` of degree 1 (`[offset, gain]`) counts as a `LinearConversion`; any other polynomial, a
  `FrequencyCompensation` and a channel with several compensations have no v2 form and raise `ValueError`.
"""

import dataclasses
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, cast

from linkml_runtime.utils.enumerations import EnumDefinitionImpl

from . import v1, v2
from .v1.schema.generated import dataset as g1
from .v2.schema.generated import dataset as g2

logger = logging.getLogger(__name__)

Scaling = tuple[float, float]  # (gain, offset)

_SLOTS = ("channel1_metadata", "channel2_metadata", "channel3_metadata")

# (v1 class, v1 field) -> v2 field, for fields that only changed their name
_RENAMED = {
    ("Source", "stu_id"): "stu_mac",
    ("Source", "sth_id"): "sth_mac",
}
# (v1 class, v1 field) dropped from v2; the ones that carry information are used by the conversion rules
_DROPPED = {
    ("Sensor", "phys_min"),
    ("Sensor", "phys_max"),
    ("Sensor", "volt_min"),
    ("Sensor", "volt_max"),
    ("ChannelMetadata", "compensations"),
}


def _has_range(sensor: g1.Sensor) -> bool:
    values = (sensor.phys_min, sensor.phys_max, sensor.volt_min, sensor.volt_max)
    return all(value is not None for value in values) and sensor.volt_max != sensor.volt_min


def linear_from_range(sensor: g1.Sensor) -> v2.LinearConversion:
    """The conversion from ADC voltage to the sensor's unit that the range of a v1 `sensor` describes:
    `gain = delta_phys / delta_volt`, `offset = phys_min - gain * volt_min`. Raises `ValueError` without a
    complete range or with `volt_max == volt_min`."""
    values = (sensor.phys_min, sensor.phys_max, sensor.volt_min, sensor.volt_max)
    if any(value is None for value in values):
        raise ValueError(
            f"sensor {sensor.sensor_id!r} has no complete phys/volt range "
            f"(phys_min={sensor.phys_min}, phys_max={sensor.phys_max}, "
            f"volt_min={sensor.volt_min}, volt_max={sensor.volt_max}) to derive a conversion from"
        )
    phys_min, phys_max, volt_min, volt_max = (float(value) for value in values)  # type: ignore[arg-type]
    if volt_max == volt_min:
        raise ValueError(f"sensor {sensor.sensor_id!r}: volt_min == volt_max ({volt_min}), no gain can be derived")
    gain = (phys_max - phys_min) / (volt_max - volt_min)
    return v2.LinearConversion(gain=gain, offset=phys_min - gain * volt_min)


def _close(a: v2.LinearConversion, b: v2.LinearConversion) -> bool:
    """Whether two conversions agree, up to float32 noise."""
    return math.isclose(a.gain, b.gain, rel_tol=1e-4, abs_tol=1e-9) and math.isclose(
        a.offset, b.offset, rel_tol=1e-4, abs_tol=1e-3 * max(1.0, abs(b.gain))
    )


@dataclass
class _Context:
    """Where `_migrate` is: the stored scalings of the file by source name and channel position, and the source
    and channel position of the object being migrated."""

    stored: dict[str, list[Scaling]] = field(default_factory=dict)
    source: str | None = None
    slot: int = 0

    def stored_scaling(self) -> Scaling | None:
        scalings = self.stored.get(self.source or "", [])
        return scalings[self.slot] if self.slot < len(scalings) else None


def _migrate_conversion(metadata: g1.ChannelMetadata, ctx: _Context) -> v2.LinearConversion:
    """The v2 conversion of a v1 channel (always a `LinearConversion`: see the module docstring)."""
    sensor = metadata.sensor
    compensations = sorted(metadata.compensations, key=lambda c: c.order)
    if len(compensations) > 1:
        raise ValueError(
            f"sensor {sensor.sensor_id!r}: {len(compensations)} compensations "
            f"({[type(c).__name__ for c in compensations]}) cannot be migrated, v2 has one conversion per channel"
        )
    compensation = compensations[0] if compensations else g1.NoConversion(order=0)
    linear: v2.LinearConversion | None = None
    if isinstance(compensation, g1.LinearConversion):
        linear = v2.LinearConversion(gain=compensation.gain, offset=compensation.offset)
    elif isinstance(compensation, g1.PolynomialConversion):
        if len(compensation.coefficients) != 2:
            raise ValueError(
                f"sensor {sensor.sensor_id!r}: a polynomial of degree {len(compensation.coefficients) - 1} "
                f"has no v2 form and cannot be migrated"
            )
        offset, gain = compensation.coefficients
        linear = v2.LinearConversion(gain=gain, offset=offset)
    elif not isinstance(compensation, g1.NoConversion):
        raise ValueError(  # noqa: TRY004 (data the migration cannot represent, not a wrong argument type)
            f"sensor {sensor.sensor_id!r}: a {type(compensation).__name__} has no v2 form and cannot be migrated"
        )

    stored = ctx.stored_scaling()
    if stored is not None:
        conversion = v2.LinearConversion(gain=stored[0], offset=stored[1])
    elif linear is not None:
        conversion = linear
    elif _has_range(sensor):
        return linear_from_range(sensor)
    else:
        return v2.LinearConversion(gain=1.0, offset=0.0)
    if _has_range(sensor) and not _close(conversion, linear_from_range(sensor)):
        logger.warning(
            "sensor %r: the stored conversion (gain=%s, offset=%s) differs from the one its phys/volt range "
            "gives; keeping the stored one",
            sensor.sensor_id,
            conversion.gain,
            conversion.offset,
        )
    return conversion


def _migrate(value: Any, ctx: _Context) -> Any:
    """`value` (any v1 object, list or dict) rebuilt from v2 classes of the same names."""
    if isinstance(value, list):
        return [_migrate(item, ctx) for item in value]
    if isinstance(value, dict):
        return {key: _migrate(item, ctx) for key, item in value.items()}
    if isinstance(value, EnumDefinitionImpl):
        return getattr(g2, type(value).__name__)(str(value))
    if isinstance(value, Enum) or not dataclasses.is_dataclass(value):
        return value
    name = type(value).__name__
    target = cast("Callable[..., Any] | None", getattr(v2, name, None) or getattr(g2, name, None))
    if target is None:
        raise ValueError(f"no v2 class for {name}")
    if name == "Source":
        ctx.source = str(value.name)
    target_fields = {f.name for f in dataclasses.fields(target) if f.init}
    kwargs: dict[str, Any] = {}
    for f in dataclasses.fields(value):
        if not f.init or (name, f.name) in _DROPPED:
            continue
        new_name = _RENAMED.get((name, f.name), f.name)
        if new_name not in target_fields:
            raise ValueError(f"{name}.{f.name} has no counterpart in schema version 2")
        if f.name in _SLOTS:
            ctx.slot = _SLOTS.index(f.name)
        kwargs[new_name] = _migrate(getattr(value, f.name), ctx)
    if name == "ChannelMetadata":
        kwargs["conversion"] = _migrate_conversion(value, ctx)
    return target(**kwargs)


def v1_to_v2(bundle: v1.DatasetBundle, *, stored_scalings: dict[str, list[Scaling]] | None = None) -> v2.DatasetBundle:
    """`bundle` of schema version 1 as a schema version 2 `DatasetBundle`; see the module docstring for the
    rules. `stored_scalings` are the (gain, offset) of each channel of each source (by source name) as stored in
    the file the bundle was read from, see `stored_scalings_of`. Raises `ValueError` for data v2 cannot
    represent."""
    return _migrate(bundle, _Context(stored=stored_scalings or {}))


def stored_scalings_of(path: str, bundle: v1.DatasetBundle) -> dict[str, list[Scaling]]:
    """The `scaling_factor` and `offset` of each channel in the `sensors` table(s) of the HDF5 file `path`
    (which `bundle` was read from), by source name. Sources without such a table or columns are left out."""
    import h5py
    import numpy as np

    result: dict[str, list[Scaling]] = {}

    def read(group: h5py.Group, source: str) -> None:
        if "sensors" not in group:
            return
        rows = group["sensors"][()]
        names = rows.dtype.names or ()
        if "scaling_factor" in names and "offset" in names:
            result[source] = [(float(row["scaling_factor"]), float(row["offset"])) for row in rows]

    with h5py.File(path, "r") as f:
        if "sources" in f.attrs and "sources" in f:
            for name in np.atleast_1d(f.attrs["sources"]):
                key = name.decode() if isinstance(name, bytes) else str(name)
                if key in f["sources"]:
                    read(f["sources"][key], key)
        else:
            sources = list(bundle.recording.sources)
            if len(sources) == 1:
                read(f, str(sources[0]))
    return result


def convert_file(source: str, destination: str) -> None:
    """Read the HDF5 or TDMS file `source` with schema version 1 and write it to `destination` as a schema
    version 2 HDF5 file (format 2.0)."""
    bundle = v1.DatasetBundle.from_file(source)
    try:
        stored = stored_scalings_of(source, bundle)
    except OSError:  # not an HDF5 file (TDMS): nothing stored
        stored = {}
    v1_to_v2(bundle, stored_scalings=stored).to_hdf5(destination, format_version="2.0")
