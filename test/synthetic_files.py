"""Synthetic test files, one per parser version, stored in `test/data/`.

Every file holds 10 seconds of sine waves sampled at 1 kHz (see `signal`). The files are committed so they can
be checked out and opened with other tools; the tests read the stored files. To rewrite them after changing
this module:

    uv run python test/synthetic_files.py

`test_parser_versions.py` regenerates every file into a temporary directory and compares it with the stored one,
so a stale file fails the tests.

The HDF5 files are built by hand with h5py, not with the package's writer: each builder lays the file out the way
its format version is documented in `icoschema/storage/python/hdf5.py`, so the readers are tested against an
independent description of the layout. TDMS files are written with the minimal writer in `tdms_writer.py`.

File names: `<format>_<version>_<n>ch[_multi].<ext>`, e.g. `hdf5_1.3_3ch_multi.hdf5`. `_multi` files have two
sources (`stu1`, `stu2`); the second starts one second after the first and its sine waves are twice as fast.
"""

import datetime
import sys
from pathlib import Path

import h5py
import numpy as np
from hdf5_helpers import SENSOR_DTYPE
from tdms_writer import ChannelObject, GroupObject, RootObject, TdmsWriter

DATA_DIR = Path(__file__).resolve().parent / "data"

SAMPLING_FREQUENCY = 1000.0
DURATION_S = 10
N_ROWS = int(SAMPLING_FREQUENCY * DURATION_S)
TIMESTAMPS = [i * 1000 for i in range(N_ROWS)]  # microseconds
COUNTERS = [i % 256 for i in range(N_ROWS)]  # the counter is one byte and wraps
START_TIME = "2026-03-04T05:06:07"
SECOND_START_TIME = "2026-03-04T05:06:08"  # the second source of a multi-source file
QUALITY_FREQUENCY = 10.0  # Hz: 100 values over the 10 seconds
QUALITY = [100.0 - 10.0 * (i % 5 == 0) for i in range(int(QUALITY_FREQUENCY * DURATION_S))]
SOURCES = ("stu1", "stu2")

# The version names a parser is registered under, in the order they were introduced.
VERSIONS = ["legacy", "1.0", "1.1", "1.2", "1.3", "1.4"]
CHANNEL_COUNTS = [1, 3]


def signal(channel: int, source: int = 0) -> list[float]:
    """The sine wave of channel `channel` (1-based) of source `source` (0-based): amplitude `channel`, frequency
    `5 * channel * (source + 1)` Hz, as float32 (what the files store)."""
    t = np.arange(N_ROWS) / SAMPLING_FREQUENCY
    wave = channel * np.sin(2 * np.pi * 5 * channel * (source + 1) * t)
    return wave.astype(np.float32).astype(float).tolist()


def sensor_name(channel: int) -> str:
    return f"Sensor {channel}"


def _sensors(channels: int) -> np.ndarray:
    rows = np.zeros(channels, dtype=SENSOR_DTYPE)
    for i in range(channels):
        rows[i]["name"] = sensor_name(i + 1)
        rows[i]["sensor_id"] = f"s{i + 1}"
        rows[i]["sensor_type"] = "SYNTH"
        rows[i]["dimension"] = "Acceleration"
        rows[i]["unit"] = "g"
        rows[i]["scaling_factor"] = 1.0
        rows[i]["offset"] = 0.0
        rows[i]["phys_min"], rows[i]["phys_max"] = -100.0, 100.0
        rows[i]["volt_min"], rows[i]["volt_max"] = 0.0, 3.3
    return rows


def _dataset(group: h5py.Group, name: str, data: np.ndarray) -> h5py.Dataset:
    return group.create_dataset(name, data=data, compression="gzip", compression_opts=4, shuffle=True)


def _primary(
    group: h5py.Group, name: str, channels: int, *, source: int = 0, counter: bool = True, start: str = START_TIME
) -> h5py.Dataset:
    """The primary table `name` (+ the `sensors` table) in `group`, as every version stores it."""
    columns = ([("counter", "u1")] if counter else []) + [("timestamp", "<u8")]
    columns += [(f"ch{c}", "<f4") for c in range(1, channels + 1)]
    table = np.zeros(N_ROWS, dtype=columns)
    if counter:
        table["counter"] = COUNTERS
    table["timestamp"] = TIMESTAMPS
    for c in range(1, channels + 1):
        table[f"ch{c}"] = signal(c, source)
    ds = _dataset(group, name, table)
    ds.attrs["Start_Time"] = start
    ds.attrs["adc_reference_voltage"] = "3.3"
    ds.attrs["conversion"] = "true"
    group.create_dataset("sensors", data=_sensors(channels))
    return ds


def _preprocessed(group: h5py.Group, name: str, channels: int, source: int = 0) -> None:
    columns = [("timestamp", "<u8")] + [(f"channel{c}", "<f4") for c in range(1, channels + 1)]
    table = np.zeros(N_ROWS, dtype=columns)
    table["timestamp"] = TIMESTAMPS
    for c in range(1, channels + 1):
        table[f"channel{c}"] = signal(c, source)
    ds = _dataset(group, name, table)
    ds.attrs["channel_sampling_frequency"] = SAMPLING_FREQUENCY
    ds.attrs["sampling_frequency_source"] = "hardware"
    ds.attrs["fill_method"] = "linear"
    ds.attrs["producer"] = "synthetic"


def _steps_and_computations(f: h5py.File) -> None:
    step = f.create_group("steps").create_group("rms")
    step.attrs["step_index"] = 0
    step.attrs["producer"] = "synthetic"
    step.attrs.create("inputs", ["recording"], dtype=h5py.string_dtype())
    step.attrs.create("output_keys", ["rms/ch1"], dtype=h5py.string_dtype())
    ds = f.create_group("computations").create_dataset("rms/ch1", data=np.array([1.5, 2.5]))
    ds.attrs["unit"] = "g"


def _quality(group: h5py.Group) -> None:
    ds = group.create_dataset("quality", data=np.array(QUALITY, dtype=np.float32))
    ds.attrs["sampling_frequency"] = QUALITY_FREQUENCY


def write_legacy(path: Path, channels: int) -> None:
    """No `icoschema_format_version`; the primary table is always called `acceleration`."""
    with h5py.File(path, "w") as f:
        _primary(f, "acceleration", channels)


def write_1_0(path: Path, channels: int) -> None:
    """The primary table's name is the root attribute `primary_table`."""
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "1.0"
        f.attrs["primary_table"] = "vibration"
        _primary(f, "vibration", channels)


def write_1_1(path: Path, channels: int) -> None:
    """1.0 plus an optional preprocessed table named by `preprocessed_table`."""
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "1.1"
        f.attrs["primary_table"] = "vibration"
        _primary(f, "vibration", channels)
        f.attrs["preprocessed_table"] = "preprocessed"
        _preprocessed(f, "preprocessed", channels)


def write_1_2(path: Path, channels: int) -> None:
    """1.1 plus `/steps/` (and the `/computations/` they point to)."""
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "1.2"
        f.attrs["primary_table"] = "vibration"
        _primary(f, "vibration", channels)
        f.attrs["preprocessed_table"] = "preprocessed"
        _preprocessed(f, "preprocessed", channels)
        _steps_and_computations(f)


def write_1_3_multi(path: Path, channels: int) -> None:
    """Two sources under `/sources/<name>/`, listed in order by the root attribute `sources`; only the first has
    a preprocessed table. (1.3 is the first version with several sources, so there is no single-source 1.3 file:
    the writer uses 1.0-1.2 for one.)"""
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "1.3"
        f.attrs["primary_table"] = "vibration"
        f.attrs["sources"] = list(SOURCES)
        f.attrs["preprocessed_table"] = "preprocessed"
        group = f.create_group("sources")
        for index, (name, start) in enumerate(zip(SOURCES, (START_TIME, SECOND_START_TIME))):
            _primary(group.create_group(name), "vibration", channels, source=index, start=start)
        _preprocessed(group[SOURCES[0]], "preprocessed", channels)
        _steps_and_computations(f)


def write_1_4(path: Path, channels: int) -> None:
    """One source with what a TDMS file has: no counter, its own rate and quality, opaque additional data and an
    always-stored name (the 1.0 layout at the root)."""
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "1.4"
        f.attrs["primary_table"] = "waveform"
        ds = _primary(f, "waveform", channels, counter=False)
        ds.attrs["source_name"] = "tdms-like"
        ds.attrs["sampling_frequency"] = SAMPLING_FREQUENCY
        ds.attrs["additional_data"] = '{"file": "x.tdms"}'
        _quality(f)


def write_1_4_multi(path: Path, channels: int) -> None:
    """1.4 with two sources: the 1.3 layout, each source in the 1.4 style (own rate and quality, no counter)."""
    with h5py.File(path, "w") as f:
        f.attrs["icoschema_format_version"] = "1.4"
        f.attrs["primary_table"] = "waveform"
        f.attrs["sources"] = list(SOURCES)
        group = f.create_group("sources")
        for index, (name, start) in enumerate(zip(SOURCES, (START_TIME, SECOND_START_TIME))):
            source_group = group.create_group(name)
            ds = _primary(source_group, "waveform", channels, source=index, counter=False, start=start)
            ds.attrs["sampling_frequency"] = SAMPLING_FREQUENCY
            _quality(source_group)


HDF5_WRITERS = {
    ("legacy", False): write_legacy,
    ("1.0", False): write_1_0,
    ("1.1", False): write_1_1,
    ("1.2", False): write_1_2,
    ("1.3", True): write_1_3_multi,
    ("1.4", False): write_1_4,
    ("1.4", True): write_1_4_multi,
}


# ── TDMS (legacy layout) ─────────────────────────────────────────────────────

TDMS_START = datetime.datetime(2026, 3, 4, 5, 6, 7)


def _waveform(increment: float, start: datetime.datetime, **extra) -> dict:
    return {"wf_increment": increment, "wf_start_time": start, "wf_start_offset": 0.0, **extra}


def _quality_channel(group: str, start: datetime.datetime) -> list:
    return [
        GroupObject(group),
        ChannelObject(
            group, "signalQuality", np.array(QUALITY, dtype=np.float32), _waveform(1 / QUALITY_FREQUENCY, start)
        ),
    ]


def write_tdms(path: Path, channels: int) -> None:
    """One source: a `system` group with the quality, and the `rawdata` group with 1 to 3 channels."""
    objects: list = _quality_channel("system", TDMS_START)
    objects += [GroupObject("rawdata")]
    for c in range(1, channels + 1):
        data = np.array(signal(c), dtype=np.float32)
        objects.append(
            ChannelObject("rawdata", f"Channel{c}", data, _waveform(1 / SAMPLING_FREQUENCY, TDMS_START, unit_string="g"))
        )
    with TdmsWriter(str(path)) as writer:
        writer.write_segment([RootObject({"name": "synthetic"}), *objects])


def write_tdms_multi(path: Path, channels: int) -> None:
    """Two STUs: a quality group per STU, and `rawdata` channels named `STU1_Channel1`, ... by their STU."""
    starts = (TDMS_START, TDMS_START + datetime.timedelta(seconds=1))
    objects: list = []
    for index in range(2):
        objects += _quality_channel(f"STU{index + 1}", starts[index])
    objects.append(GroupObject("rawdata"))
    for index in range(2):
        for c in range(1, channels + 1):
            data = np.array(signal(c, index), dtype=np.float32)
            name = f"STU{index + 1}_Channel{c}"
            objects.append(
                ChannelObject("rawdata", name, data, _waveform(1 / SAMPLING_FREQUENCY, starts[index], unit_string="g"))
            )
    with TdmsWriter(str(path)) as writer:
        writer.write_segment([RootObject({"name": "synthetic"}), *objects])


TDMS_WRITERS = {False: write_tdms, True: write_tdms_multi}


# ── the stored files ─────────────────────────────────────────────────────────


def hdf5_name(version: str, channels: int, multi: bool = False) -> str:
    return f"hdf5_{version}_{channels}ch{'_multi' if multi else ''}.hdf5"


def tdms_name(channels: int, multi: bool = False) -> str:
    return f"tdms_legacy_{channels}ch{'_multi' if multi else ''}.tdms"


def write_all(directory: Path) -> list[Path]:
    """Write every synthetic file into `directory` and return their paths."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for channels in CHANNEL_COUNTS:
        for (version, multi), writer in HDF5_WRITERS.items():
            paths.append(directory / hdf5_name(version, channels, multi))
            writer(paths[-1], channels)
        for multi, tdms_writer in TDMS_WRITERS.items():
            paths.append(directory / tdms_name(channels, multi))
            tdms_writer(paths[-1], channels)
    return paths


if __name__ == "__main__":
    for written in write_all(Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR):
        print(f"wrote {written} ({written.stat().st_size} bytes)")
