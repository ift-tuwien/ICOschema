# ICOschema

Backend-agnostic data model for sensor/hardware recordings and their derived computations.

## Install

```sh
uv venv --allow-existing
uv sync
```

## Usage

**Note:** In the example below we assume you installed Matplotlib:

```sh
uv pip install matplotlib
```

Other codebases should only import `Recording`/`DatasetBundle` from the top-level package:

```python
from icoschema import Recording, DatasetBundle

import matplotlib.pyplot as plt

recording = Recording.from_hdf5("test/test_with_sensors.hdf5")
df = recording.to_dataframe()
plt.plot(recording.timestamps, recording.channel1)
plt.show()
recording.to_hdf5("some_file.hdf5")

bundle = DatasetBundle.from_hdf5("some_file.hdf5")  # recording + any DerivedDataset computations
# Note: The code below does not work, since `derived` is not defined
#       Adding the code for `derived` from the example below will not work,
#       since then `my_wavelet_transform` is not defined.
bundle = bundle.with_computation("wavelet_coefficients/channel1/details", derived)
bundle.to_hdf5("some_file.hdf5")
```

### TDMS files (read-only)

`DatasetBundle.from_tdms(path)` / `Recording.from_tdms(path)` read an NI TDMS file, and
`DatasetBundle.from_file(path)` takes either format, told apart by the file's first bytes. Like HDF5, reading dispatches
on a format version, here the root property `icoschema_format_version`; a file without one is read with the *legacy*
layout (`rawdata` group, `signalQuality` channels, one source per STU group), documented in
`icoschema/storage/python/tdms.py`. A TDMS waveform has no packet counter, so a TDMS source has none: its
`sampling_frequency` is `1 / wf_increment`, its `timestamp`s are built from it, its `quality` is the file's
`signalQuality` channel (own rate; `Source.signal_loss_percentage` is `100 - mean(quality)`), each channel's `Sensor`
has the TDMS channel name and `unit_string`, and `additional_data` (opaque JSON) keeps the file's, group's and
channels' properties. Channels of a source must have equal length. `DatasetBundle.provenance` says where the data was
read from (`source_format`, `source_format_version`, `reader`, and `writer` for an HDF5 file). Sources have independent
clocks; `Recording.start_offsets()` and `Recording.time_axis(source)` place them against each other by their start
times without touching their own timestamps. There is no TDMS writer: save results with `to_hdf5` (format `1.4`).

### Sources (STU/STH combinations)

A `Recording` holds one or more independent `Source`s, one per STU/STH combination, each with its own clock
(`start_time`), packet counter, ADC settings (so its own sampling frequency) and sensors. Start times of different
sources are not synchronized. For a single-source recording (everything read from today's files) the usual
shortcuts keep working; with several sources they raise a `ValueError` and you pick a source:

```python
recording.channel1                          # single source only
source = recording.sources["source1"]       # files without a stored name read as "source1"
source.channel1, source.channel_sampling_frequency(), source.signal_loss_percentage
recording.to_dataframe(source="source1")
```

### Example use cases

**Inspect a recording without loading a full DataFrame:**

```python
recording = Recording.from_hdf5("some_file.hdf5")
print(recording.signal_loss_percentage)
print(recording.summary())                # JSON-encodable dict: per-channel min/max/mean/std, sensor info
```

**Add a derived computation and persist it alongside the recording:**

```python
from icoschema.schema.generated.python.dataset import DerivedDataset

bundle = DatasetBundle.from_hdf5("some_file.hdf5")
coeffs = my_wavelet_transform(bundle.recording.channel1)
derived = DerivedDataset(
    key="wavelet_coefficients/channel1/details",
    values=coeffs.flatten().tolist(),
    shape=list(coeffs.shape),
    dtype=str(coeffs.dtype),
    produced_by="wavelet_transform@1.0.0",
)
bundle = bundle.with_computation(derived.key, derived)
bundle.to_hdf5("processed_file.hdf5")
```

**Place samples on the gap-free grid and get the sampling frequency:**

```python
recording = Recording.from_hdf5("some_file.hdf5")
recording.sample_index()                 # grid position of every received row (lost packets leave holes)
recording.filled_mask()                  # True where a packet was lost, over the whole grid
recording.channel_sampling_frequency()   # (Hz per channel, "hardware" | "default")
```

The total sampling frequency is the ADC rate, shared by all channels:
`38.4 MHz / ((adc_prescaler + 1) * (adc_acquisition_time + 13) * adc_oversample_rate)`,
from the `adc_*` settings recorded in the file, or from the default settings (2, 8, 64 → 9523.81 Hz) when the file
doesn't record them. The per-channel frequency is that divided by the number of channels.

**Store a preprocessed table (lost packets filled, timestamps on the 1 / f_s grid):**

```python
from icoschema import PreprocessedRecording

bundle = DatasetBundle.from_hdf5("some_file.hdf5")
preprocessed = PreprocessedRecording(
    timestamp=...,                     # first raw timestamp + round(j * 1e6 / channel_sampling_frequency)
    channel1=...,                      # raw channel1 on the grid, not converted
    channel_sampling_frequency=fs,     # Hz per channel
    sampling_frequency_source="default",
    fill_method="forward_fill",
    producer="my_tool@1.0",
)
bundle = bundle.with_preprocessed(preprocessed)   # raises if it doesn't fit the recording
bundle.to_hdf5("some_file.hdf5")
```

The preprocessed channels mean exactly what the raw channels mean (same sensors and compensations). The raw recording
stays untouched; while a bundle has a preprocessed table, `with_recording` raises — call `without_preprocessed()`
first.

With several sources, a bundle holds one preprocessed table per source (each with its own grid and
`channel_sampling_frequency`), and `bundle.preprocessed` — the shortcut for a single source — raises:

```python
bundle = bundle.with_preprocessed(preprocessed, source="source2")   # or set `PreprocessedRecording.source`
bundle.preprocessed_for("source2")                                  # None if that source has none
bundle = bundle.without_preprocessed("source2")                     # no argument: drop all
```

A step says where it read from with one name, `ComputationStep.source_node`, from a single namespace:

| `source_node` | reads |
|---|---|
| `"source2"` | the raw recording of that source |
| `"preprocessed:source2"` | the preprocessed table of that source (`"preprocessed"` if there is only one source) |
| `"rms_source2"` | the computations of the earlier step with that `node` |
| `None` | the raw recording of a single-source file |

A step reading several things lists them in `inputs`. There is no separate "source" on steps or computations: a step's
source follows from what it reads. `bundle.source_of(name)` traces any of the names above back to its source (`None`
for a step over several sources), and `bundle.computations_for_source("source2")` selects what descends from one source.
Step names must not collide with source names or the reserved `preprocessed` names; whether a `source_node` names a
recorded step is not checked (it may have failed unrecorded). With several sources, run one step per source (e.g.
`rms_source1`, `rms_source2`) so that computation keys stay unique.

**Record the steps that produced the computations:**

```python
from icoschema import ComputationStep

bundle = bundle.with_computation("rms/channel1", derived)          # add the step's data first
bundle = bundle.with_step(ComputationStep(
    node="rms",                        # unique, one HDF5 path segment
    step_index=0,                      # assigned by with_step
    producer="rms@1.0.0",
    params='{"window_size": 200}',
    output_keys=["rms/channel1"],      # authoritative link from the step to its data
    status="ok",
))
bundle.computations_of("rms")          # {"rms/channel1": ...}
bundle.unmanaged_keys()                # computations no step lists
bundle = bundle.without_steps(["rms"]) # drops the step and its output_keys; the rest is renumbered
```

`steps` is a list ordered by `step_index`. `with_step` raises for a duplicate or malformed node name, or an
`output_keys` entry that isn't in `computations`. How steps are named or how keys relate to node names is up to the
producer.

### File format

- `1.0`: the recording (primary table + `sensors`) and optional `/computations/`.
- `1.1`: additionally a preprocessed table. Written only when the bundle has one, so files without it stay readable
  by older versions, which reject `1.1` instead of silently dropping the table.
- `1.2`: additionally a `/steps/` group (one attribute-only group per step). Written only when the bundle has steps;
  read back ordered by `step_index`. A malformed step, or one whose `output_keys` are missing, is skipped (or raises
  with `on_error="raise"`).
- `1.3`: several sources (one per STU/STH combination). The root attribute `sources` lists their names in order, and
  `/sources/<name>/` holds each source's table and `sensors` table the way a `1.0` file holds them at the root. May also
  have `/steps/` and `/computations/`. Written only when the recording has more than one source: a single source keeps
  the `1.0`-`1.2` layout (its name and STU/STH ids are stored as optional table attributes), so those files stay
  readable by older versions. A preprocessed table, if a source has one, is stored in that source's group.
- `1.4`: for sources that are not packet recordings (TDMS): the primary table may have no `counter` column and the
  table attributes `sampling_frequency` and `additional_data`; a `quality` dataset (attribute `sampling_frequency`) sits
  next to the table; a single source's name is always stored. Either layout (`sources` attribute or not) as in `1.0`-`1.3`.
  Written only when a source needs it. Every file also gets the root attribute `writer`, and `source_format`,
  `source_format_version`, `reader` when the bundle has a provenance (older readers ignore them).
- Legacy files (no version, table `acceleration`) are read as before.
- A file with an empty or missing `sensors` table (old recordings) is read with an unspecified `Sensor()` (every field
  `None`) per channel and no conversion, as long as its `conversion` attribute is `true`; if it isn't, there is no
  scaling to take from the sensor rows and reading raises. Such a recording is written back without a `sensors` table.
  Any other mismatch between channel columns and sensor rows still raises.
- The first acquisition tools' files (table `acceleration` of physical values in g, only `Start_Time` and
  `Sensor_Range` such as `± 100.0 g₀` as metadata) are read too: no `conversion` attribute (without sensor rows) means
  converted, a missing `adc_reference_voltage` is `None`, and `Sensor_Range` becomes each channel's sensor unit and
  range (`g`, -100..100). A `conversion`-less file that does have sensor rows raises.
- All datasets with more than one element are gzip-compressed. The `pre_metadata`/`post_metadata` attributes of the
  primary table are preserved.

## Development

Regenerate the Python dataclasses after editing the schema:

```
uv run gen-python icoschema/schema/linkml/dataset.yaml > icoschema/schema/generated/python/dataset.py
```

Run the tests:

```
uv run pytest
```

## Schema

```mermaid
classDiagram
    class Recording {
        +Map~string, Source~ sources
    }
    class Source {
        +string name
        +string stu_id
        +string sth_id
        +HardwareMetadata hardware_metadata
        +RecordingMetadata recording_metadata
        +RecordingData recording_data
    }
    class RecordingMetadata {
        +string start_time
        +string pre_metadata
        +string post_metadata
    }
    class RecordingData {
        +int[] timestamp
        +int[] counter
        +float[] channel1
        +float[] channel2
        +float[] channel3
    }
    class HardwareMetadata {
        +string revision
        +string adc_reference_voltage
        +int adc_prescaler
        +int adc_acquisition_time
        +int adc_oversample_rate
        +ChannelMetadata channel1_metadata
        +ChannelMetadata channel2_metadata
        +ChannelMetadata channel3_metadata
    }
    class ChannelMetadata {
        +Sensor sensor
        +Compensation[] compensations
    }
    class Sensor {
        +string sensor_id
        +string sensor_type
        +string name
        +string unit
        +string dimension
        +float phys_min
        +float phys_max
        +float volt_min
        +float volt_max
    }
    class Compensation {
        <<abstract>>
        +int order
    }
    class Conversion {
        <<abstract>>
    }
    class NoConversion
    class LinearConversion {
        +float gain
        +float offset
    }
    class PolynomialConversion {
        +float[] coefficients
    }
    class FrequencyCompensation {
        <<abstract>>
    }
    class DerivedDataset {
        +string key
        +float[] values
        +int[] shape
        +string dtype
        +string unit
        +string produced_by
        +string produced_at
        +string params
        +string description
    }
    class PreprocessedRecording {
        +string source
        +int[] timestamp
        +float[] channel1
        +float[] channel2
        +float[] channel3
        +float channel_sampling_frequency
        +SamplingFrequencySource sampling_frequency_source
        +string fill_method
        +string producer
    }
    class ComputationStep {
        +string node
        +int step_index
        +string producer
        +string params
        +string resolved_params
        +string source_node
        +string[] inputs
        +ComputationStatus status
        +string error
        +string summary
        +string[] output_keys
        +string started_at
        +float duration_s
        +string environment
    }
    class DatasetBundle {
        +Recording recording
        +PreprocessedRecording[] preprocessed_tables
        +Map~string, DerivedDataset~ computations
        +ComputationStep[] steps
    }

    Compensation <|-- Conversion
    Compensation <|-- FrequencyCompensation
    Conversion <|-- NoConversion
    Conversion <|-- LinearConversion
    Conversion <|-- PolynomialConversion

    Recording *-- "1..*" Source
    Source *-- HardwareMetadata
    Source *-- RecordingMetadata
    Source *-- RecordingData
    HardwareMetadata *-- "1" ChannelMetadata : channel1_metadata
    HardwareMetadata o-- "0..1" ChannelMetadata : channel2_metadata
    HardwareMetadata o-- "0..1" ChannelMetadata : channel3_metadata
    ChannelMetadata *-- Sensor
    ChannelMetadata *-- "1..*" Compensation : compensations
    DatasetBundle *-- Recording
    DatasetBundle o-- "0..*" PreprocessedRecording : preprocessed_tables (one per source)
    DatasetBundle o-- "0..*" DerivedDataset : computations
    DatasetBundle o-- "0..*" ComputationStep : steps
```

## Open questions

- All channels of one `Source` share one `timestamp`/`counter` array set, i.e. one sample rate per source. Mixing sensors with different data rates on different channels of the same STU/STH combination isn't representable — would likely need a per-channel rate/timestamp. Different *sources* may have different rates.

## Development

In the text below we assume that you installed:

- [`just`](https://just.systems)
- [`uv`](https://docs.astral.sh/uv)

and that you want to release version `<VERSION>` of the package. Please just replace this version number with the version that you want to release (e.g. `0.1.0`).

### Release

1. Change the version number and commit your changes:

   ```sh
   just release <VERSION>
   ```

   **Note:** [GitHub Actions](https://github.com/ift-tuwien/ICOschema/actions) will publish a package based on the tagged commit and upload it to [PyPi](https://pypi.org/project/icoschema/).

2. Create a new release [here](https://github.com/ift-tuwien/ICOschema/releases/new)
   1. Insert the version number `<VERSION>` into the tag field
   2. For the release title use “Version `<VERSION>`”
   3. Paste the [release notes](doc/releases) for the lastest release into the main text field
   4. Click on “Publish Release”

   **Note:** Alternatively you can also use the [`gh`](https://cli.github.com) command:

   ```sh
   gh release create <VERSION>
   ```

   to create the release notes.
