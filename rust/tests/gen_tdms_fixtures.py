"""Builds the TDMS fixtures in tests/fixtures/tdms and expected_tdms.json from the *Python* icoschema.

    uv run python rust/tests/gen_tdms_fixtures.py          # from the repository root

The files are written with the test writer `test/tdms_writer.py` (the layouts of the real examples: one STU with a `system` group,
several STUs with a quality group each, scaled channels, several segments) plus the real
`test/test_dual_stu.tdms`. expected_tdms.json is what the Rust reader must reproduce: for every
source its rate, quality, start time, properties, loss, and a length and FNV-1a hash of its
timestamps and channels (so the file stays small whatever the sample count). Where Python raises,
Rust must refuse the file too.
"""

import datetime
import json
import shutil
import sys
import warnings
from pathlib import Path

import numpy as np

from icoschema import DatasetBundle

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "test"))
from tdms_writer import ChannelObject, GroupObject, RootObject, TdmsWriter

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "fixtures" / "tdms"
OUT.mkdir(parents=True, exist_ok=True)

INCREMENT = 0.00010499790004199917
START = datetime.datetime(2025, 4, 17, 14, 8, 29, 342295)


def waveform(increment=INCREMENT, start=START, **extra):
    return {"wf_increment": increment, "wf_start_time": start, "wf_start_offset": 0.0, **extra}


def write(name, objects, root=None, segments=1):
    with TdmsWriter(str(OUT / name)) as writer:
        for _ in range(segments):
            writer.write_segment([RootObject({"name": "t", **(root or {})}), *objects])


def signal(n, dtype=np.int16, offset=0):
    return ((np.arange(n) * 7 + offset) % 1000 - 500).astype(dtype)


def single_stu(name, quality=(100.0, 99.0, 98.0), n=3000, dtype=np.int16, root=None, **channel_props):
    objects = []
    if quality is not None:
        objects += [GroupObject("system", {"deviceName": "Tool_01"}),
                    ChannelObject("system", "signalQuality", np.array(quality, dtype=np.float32), waveform(0.1))]
    objects += [GroupObject("rawdata"), ChannelObject("rawdata", "Channel1", signal(n, dtype), waveform(**channel_props))]
    write(name, objects, root)


# 1. one STU with a `system` group
single_stu("single_stu.tdms", unit_string="g")
single_stu("single_stu_no_quality.tdms", quality=None)
single_stu("single_stu_empty_quality.tdms", quality=[])
single_stu("single_float32.tdms", dtype=np.float32)

# 2. several STUs, one quality group each
write("two_stus.tdms", [
    GroupObject("STU1", {"deviceName": "A"}),
    ChannelObject("STU1", "signalQuality", np.array([100.0] * 3, dtype=np.float32), waveform(0.1)),
    GroupObject("STU2", {"deviceName": "B"}),
    ChannelObject("STU2", "signalQuality", np.array([90.0, 80.0, 100.0], dtype=np.float32), waveform(0.1)),
    GroupObject("rawdata"),
    ChannelObject("rawdata", "STU1_Channel1", np.linspace(0, 1, 3000, dtype=np.float32), waveform()),
    ChannelObject("rawdata", "STU2_Channel1", np.linspace(1, 2, 2970, dtype=np.float32), waveform()),
    GroupObject("info", {"Dashboard": "x", "Count": 3, "Ratio": 0.5, "Flag": True}),
])

# 3. the longest group name wins, own rate/start/channels per STU, STUs not in alphabetical order
later = waveform(0.0005, START + datetime.timedelta(seconds=7))
write("stu_prefixes.tdms", [
    GroupObject("STU2"),
    ChannelObject("STU2", "signalQuality", np.array([95.0], dtype=np.float32), waveform(0.1)),
    GroupObject("STU10"),
    ChannelObject("STU10", "signalQuality", np.array([100.0], dtype=np.float32), waveform(0.1)),
    GroupObject("rawdata"),
    ChannelObject("rawdata", "STU2_z", np.zeros(100, dtype=np.float32), waveform()),
    ChannelObject("rawdata", "STU10_y", np.ones(50, dtype=np.float32), later),
    ChannelObject("rawdata", "STU10_a", np.arange(50, dtype=np.float32), later),
])

# 4. channel order is file order, not alphabetical
write("channel_order.tdms", [
    GroupObject("rawdata"),
    ChannelObject("rawdata", "zeta", np.full(20, 1.0, dtype=np.float32), waveform()),
    ChannelObject("rawdata", "alpha", np.full(20, 2.0, dtype=np.float32), waveform()),
    ChannelObject("rawdata", "mid", np.full(20, 3.0, dtype=np.float32), waveform()),
])

# 5. start offset
write("start_offset.tdms", [GroupObject("rawdata"), ChannelObject("rawdata", "c", np.zeros(5), waveform(wf_start_offset=2.5))])

# 6. NI scaling
linear = {"NI_Number_Of_Scales": 1, "NI_Scale[0]_Scale_Type": "Linear", "NI_Scale[0]_Linear_Slope": 2.0,
          "NI_Scale[0]_Linear_Y_Intercept": 10.0, "NI_Scale[0]_Linear_Input_Source": np.uint32(0xFFFFFFFF)}
single_stu("scaled_linear.tdms", unit_string="g", **linear)
single_stu("scaled_linear_float32.tdms", dtype=np.float32, **{**linear, "NI_Scale[0]_Linear_Slope": 0.1})
polynomial = {"NI_Number_Of_Scales": 2,
              "NI_Scale[0]_Scale_Type": "Polynomial", "NI_Scale[0]_Polynomial_Coefficients_Size": 3,
              "NI_Scale[0]_Polynomial_Coefficients[0]": 1.0, "NI_Scale[0]_Polynomial_Coefficients[1]": 0.5,
              "NI_Scale[0]_Polynomial_Coefficients[2]": 0.001, "NI_Scale[0]_Polynomial_Input_Source": np.uint32(0xFFFFFFFF),
              "NI_Scale[1]_Scale_Type": "Linear", "NI_Scale[1]_Linear_Slope": -1.0, "NI_Scale[1]_Linear_Y_Intercept": 3.0,
              "NI_Scale[1]_Linear_Input_Source": np.uint32(0)}
single_stu("scaled_chain.tdms", **polynomial)
single_stu("scaled_already.tdms", **{**linear, "NI_Scaling_Status": "scaled"})
write("scaled_group_level.tdms", [
    GroupObject("rawdata", dict(linear)),
    ChannelObject("rawdata", "c", np.array([1, 2, 3], dtype=np.int16), waveform())])

# 7. several segments of one channel set
with TdmsWriter(str(OUT / "segments.tdms")) as writer:
    for k in range(4):
        writer.write_segment([RootObject({"name": "t"}), GroupObject("rawdata"),
                              ChannelObject("rawdata", "Channel1", signal(1000, offset=1000 * k), waveform()),
                              ChannelObject("rawdata", "Channel2", signal(1000, offset=77 * k), waveform())])

# 8. quality groups
write("quality_mismatch.tdms", [
    GroupObject("A"), ChannelObject("A", "signalQuality", np.array([50.0], dtype=np.float32), waveform(0.1)),
    GroupObject("rawdata"), ChannelObject("rawdata", "x", np.zeros(10, dtype=np.float32), waveform()),
    ChannelObject("rawdata", "y", np.zeros(10, dtype=np.float32), waveform())])
write("quality_worst.tdms", [
    GroupObject("A"), ChannelObject("A", "signalQuality", np.array([100.0, 100.0], dtype=np.float32), waveform(0.1)),
    GroupObject("B"), ChannelObject("B", "signalQuality", np.array([60.0, 80.0], dtype=np.float32), waveform(0.1)),
    GroupObject("rawdata"), ChannelObject("rawdata", "x", np.zeros(10, dtype=np.float32), waveform()),
    ChannelObject("rawdata", "y", np.zeros(10, dtype=np.float32), waveform())])

# 9. the real file: 254 segments, 60 of which carry metadata without a new object list
shutil.copyfile(HERE.parents[1] / "test/test_dual_stu.tdms", OUT / "dual_stu.tdms")

# 10. rejected files
write("err_no_rawdata.tdms", [GroupObject("other"), ChannelObject("other", "x", np.zeros(3), waveform())])
write("err_mixed_increments.tdms", [GroupObject("rawdata"), ChannelObject("rawdata", "a", np.zeros(5), waveform(0.001)),
                                    ChannelObject("rawdata", "b", np.zeros(5), waveform(0.002))])
write("err_four_channels.tdms", [GroupObject("rawdata")] + [ChannelObject("rawdata", f"c{i}", np.zeros(5), waveform()) for i in range(4)])
write("err_unequal_lengths.tdms", [GroupObject("rawdata"), ChannelObject("rawdata", "a", np.zeros(5), waveform()),
                                   ChannelObject("rawdata", "b", np.zeros(4), waveform())])
write("err_no_increment.tdms", [GroupObject("rawdata"), ChannelObject("rawdata", "a", np.zeros(5))])
write("err_version.tdms", [GroupObject("rawdata"), ChannelObject("rawdata", "a", np.zeros(5), waveform())],
      root={"icoschema_format_version": "9.9"})


def fnv1a(data: bytes) -> str:
    h = 0xCBF29CE484222325
    for byte in data:
        h = ((h ^ byte) * 0x100000001B3) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


# numpy's polynomial evaluation rounds differently from run to run of the same data (its SIMD loops depend on
# the array's alignment and length), so these are compared value by value with a tolerance, not by hash.
APPROXIMATE = {"scaled_chain.tdms"}


def dump_source(s, approximate=False):
    ts = np.asarray(s.timestamps, dtype="<i8")
    channels = [getattr(s, f"channel{i}") for i in (1, 2, 3)]
    first = channels[0]
    sensors = []
    for slot in ("channel1_metadata", "channel2_metadata", "channel3_metadata"):
        m = getattr(s.hardware_metadata, slot)
        sensors.append(None if m is None else [m.sensor.name, m.sensor.unit])
    return {
        "name": str(s.name), "stu_id": s.stu_id, "sampling_frequency": s.sampling_frequency,
        "quality": None if s.quality is None else {"values": [float(v) for v in s.quality.values],
                                                    "sampling_frequency": s.quality.sampling_frequency},
        "additional_data": json.loads(s.additional_data), "start_time": s.recording_metadata.start_time,
        "channel_count": s.channel_count, "sensors": sensors, "rows": len(ts),
        "timestamps_hash": fnv1a(ts.tobytes()), "timestamps_head": [int(v) for v in ts[:4]],
        "channel_hashes": [fnv1a(np.asarray(c, dtype="<f8").tobytes()) if c.size else None for c in channels],
        "channel1_head": [float(v) for v in first[:4]], "channel1_tail": [float(v) for v in first[-3:]],
        "has_counter": s.has_counter, "signal_loss_percentage": float(s.signal_loss_percentage),
        "signal_loss_measured": s.signal_loss_measured,
        "channel_fs": list(s.channel_sampling_frequency()),
        **({"channel1_values": [float(v) for v in first]} if approximate else {}),
    }


def dump(path):
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            bundle = DatasetBundle.from_tdms(str(path))
        except Exception as error:  # noqa: BLE001
            return {"load_error": type(error).__name__}
    return {
        "provenance": {"source_format": bundle.provenance.source_format,
                       "source_format_version": bundle.provenance.source_format_version},
        "warnings": [str(w.message) for w in caught],
        "sources": [dump_source(s, path.name in APPROXIMATE) for s in bundle.recording.sources.values()],
        "start_offsets": [[n, o] for n, o in bundle.recording.start_offsets().items()],
    }


expected = {p.name: dump(p) for p in sorted(OUT.glob("*.tdms"))}
(OUT / "expected_tdms.json").write_text(json.dumps(expected, indent=1))
for name, value in expected.items():
    print(f"{name:34} {'LOAD ERROR ' + value['load_error'] if 'load_error' in value else str(len(value['sources'])) + ' source(s)'}")
