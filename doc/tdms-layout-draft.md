# TDMS file layout for ICOschema: draft for review

Status: **draft, not implemented.** ICOschema already reads the two layouts the acquisition software writes today
(called *legacy* below, recognised by the absence of a version property). This draft defines a clean, versioned layout
so the reader no longer has to guess. We would like the acquisition team to check every rule and answer the questions
in the last section.

## 1. Principles

- **Same structure as the ICOschema HDF5 file (format 1.4).** Every piece of information sits on the TDMS node that
  corresponds to its HDF5 node, under the same name where TDMS allows it (section 2). Someone who knows the HDF5 file
  finds everything in the same place; the reader is a direct mapping, and a TDMS file converts to HDF5 without
  reinterpretation.
- **Root = the file, group = a source, channel = a channel.** General information is on the root, everything about one
  source (one STU/STH combination) on its group, everything about one sensor/channel on that channel.
- A source is a **gap-free waveform**: sample *i* is at `start + i * wf_increment`. As in HDF5 1.4 there is no packet
  counter, and no timestamp channel is stored; ICOschema derives the timestamps.
- The file's own start time is not stored. Each source has its own start; differences between sources are computed by
  the reader from those start times.
- Sources are independent: each has its own start, rate, length and quality.

## 2. Layout, side by side with HDF5

```
TDMS                                          HDF5 (format 1.4)
File (root)                                   root attributes
  icoschema_format_version = "1.4"              icoschema_format_version
  writer = "acquisition 3.2"                    writer
  (any other property)                          -

Group "STU1"  (a source: has channel1)        /sources/STU1/  (group, name = source name; order = file order)
  stu_id, sth_id                                primary table attributes stu_id, sth_id
  adc_reference_voltage                         primary table attribute adc_reference_voltage
  adc_prescaler, adc_acquisition_time,          primary table attributes of the same names
    adc_oversample_rate
  (any other property)                          -
  Channel "channel1"   waveform                 primary table column channel1
    name, unit_string, dimension,               row 1 of the `sensors` table (name, unit,
    sensor_id, sensor_type,                       dimension, sensor_id, sensor_type,
    phys_min, phys_max, volt_min, volt_max        phys_min/max, volt_min/max)
    wf_increment                                primary table attribute sampling_frequency (= 1 / wf_increment)
    wf_start_time (+ wf_start_offset)           primary table attribute Start_Time
  Channel "channel2", "channel3"                columns channel2, channel3 and sensor rows 2, 3
  Channel "quality"    optional, own rate       dataset `quality`
    wf_increment                                  its attribute sampling_frequency (= 1 / wf_increment)

Group "STU2"                                  /sources/STU2/
  ... same structure ...
```

Mapping rules behind the picture:

- **Root** holds what is about the file as a whole: the format version and who wrote it. The root
  carries no per-source data and no start time.
- **Group** holds what is about the source as a whole: identification (`stu_id`, `sth_id`) and the hardware settings
  of that STU, exactly the attributes of the HDF5 primary table.
- **Channel** holds what is about one sensor: the sensor description (the HDF5 `sensors` row) and the waveform
  description. The waveform properties (`wf_*`) are the standard TDMS ones, so every TDMS tool can read the file; they
  are the TDMS spelling of the HDF5 attributes `sampling_frequency` and `Start_Time`.
- **Names:** channels are named `channel1..channel3` like the HDF5 columns; the sensor name is the channel property
  `name` (the `sensors` row's `name`). The quality channel is called `quality` like the HDF5 dataset.
- **Not in a TDMS file:** `primary_table`, `preprocessed_table`, `conversion`, `source_name`, steps, computations,
  `pre_metadata`/`post_metadata` (HDF5 bookkeeping or results of later processing; the reader fills them in, e.g.
  `conversion` is always `true` because TDMS values are final). The provenance attributes (`source_format`,
  `source_format_version`, `reader`) are not stored either: the reader creates them, like `writer` for HDF5 files it
  writes.

### 2.1 Root

| Property | Required | HDF5 | Meaning |
|---|---|---|---|
| `icoschema_format_version` | yes | root attribute, same name | `"1.4"` for this layout. Absent means legacy |
| `writer` | no | root attribute, same name | The software that wrote the file, e.g. `"acquisition 3.2"` |
| anything else (`name`, `description`, `author`, ...) | no | - | kept as-is in `Source.additional_data` (key `file`) |

No start time at the root.

### 2.2 Source group

A group is a source if and only if it has a waveform channel `channel1`. Sources are in file order (HDF5 stores that
order in the root attribute `sources`; a TDMS file needs no such list because group order is kept). General information is not
put in a group of its own but on the root. A file may still contain other groups (the legacy files have `info`); they
are not sources, the layout does not define them, and the reader keeps their properties in `Source.additional_data`.

| Rule / property | Required | HDF5 | Detail |
|---|---|---|---|
| Name | yes | the group name `/sources/<name>/` | The source name. Non-empty, unique in the file, no `/`, not starting with `.` |
| `stu_id`, `sth_id` | no | primary table attributes | identify the STU and STH |
| `adc_reference_voltage` | no | primary table attribute | volts |
| `adc_prescaler`, `adc_acquisition_time`, `adc_oversample_rate` | no | primary table attributes | integers; all three or none |
| Channels | yes | table columns | 1 to 3 waveform channels `channel1..channel3` (consecutive, starting at 1), plus optionally `quality` |
| other properties | no | - | kept unchanged in `Source.additional_data` (key `group`) |

### 2.3 Waveform channel (`channel1..channel3`)

Sensor description, the same fields as a row of the HDF5 `sensors` table:

| Property | Required | HDF5 `sensors` column | Meaning |
|---|---|---|---|
| `name` | no | `name` | sensor name |
| `unit_string` | no | `unit` | unit of the stored values (standard TDMS property) |
| `dimension` | no | `dimension` | physical dimension, e.g. `Acceleration` |
| `sensor_id`, `sensor_type` | no | same | sensor identification |
| `phys_min`, `phys_max` | no | same | sensor range in `unit_string` |
| `volt_min`, `volt_max` | no | same | sensor range in volts |

Waveform description (standard TDMS properties):

| Property | Required | HDF5 | Meaning |
|---|---|---|---|
| `wf_increment` | yes | `sampling_frequency` | seconds between samples, > 0, **identical for all channels of the group**. The sampling rate is `1 / wf_increment` |
| `wf_start_time` | yes | `Start_Time` | start of the first sample, **UTC**, **identical for all channels of the group** |
| `wf_start_offset` | no (default 0) | added to `Start_Time` | seconds added to `wf_start_time` |

Scaling: the HDF5 `sensors` rows have `scaling_factor` and `offset`; in TDMS the standard NI scaling properties
(`NI_Scale[...]`) play that role. If present, the values are read **already scaled** (standard TDMS behaviour) and are
taken to be in `unit_string`; the scaling properties are kept in `Source.additional_data`. Writers that store final
values need no scaling properties.

Data: numeric, **all channels of a group have exactly the same number of samples** (otherwise the file is rejected,
nothing is cut). At least one sample.

### 2.4 Quality channel (`quality`)

| Property | Required | HDF5 | Meaning |
|---|---|---|---|
| `wf_increment` | recommended | attribute `sampling_frequency` of dataset `quality` | seconds between quality values (its own rate, e.g. 0.1 s) |

Values are percentages 0 to 100, **100 = nothing lost**. ICOschema reports the signal loss of the source as
`100 - mean(values)`. Without this channel the loss is unknown and reported as an assumed 0 (flagged as not measured).
The acquisition software currently calls this channel `signalQuality`; the legacy reader keeps accepting that name.

## 3. What ICOschema makes of it

| In the file | In ICOschema |
|---|---|
| group name (file order) | `Recording.sources` keys, `Source.name` |
| `stu_id`, `sth_id` (group) | `Source.stu_id`, `Source.sth_id` |
| `adc_*` (group) | `HardwareMetadata.adc_*` |
| `1 / wf_increment` (channels) | `Source.sampling_frequency` (Hz per channel) |
| `wf_start_time` + `wf_start_offset` | `RecordingMetadata.start_time` of the source |
| channel values | `channel1..3` |
| `name`, `unit_string`, `dimension`, `sensor_id`, `sensor_type`, `phys_*`, `volt_*` (channel) | `ChannelMetadata.sensor`; no conversion (values are final) |
| `quality` | `Source.quality` (values and own rate) |
| `writer` (root) | `Provenance.writer` |
| all other properties and groups | `Source.additional_data` (opaque JSON: `file`, `group`, `channels`, `other_groups`) |
| (derived) `round(i * 1e6 / fs)` | `timestamp` in microseconds |

Converting such a file with `to_hdf5` gives a `1.4` file with the structure in section 2 (`sources` attribute only when
there are several sources).

## 4. Rejected files

A file is rejected with a clear error when: the version is unknown; the file has no source; a source has channels that are not
`channel1..channelN` without gaps, or more than 3 channels; `wf_increment` is missing, not positive or differs between
channels of a group; `wf_start_time` differs between channels of a group; channel lengths differ; a channel has no
data.

## 5. Legacy files

Files without `icoschema_format_version` keep working unchanged: the reader accepts a `rawdata` group with
`signalQuality` channels in a `system` group (one source) or in one group per STU, with `rawdata` channels named
`STU1_...`, `STU2_...` (several sources). The new layout makes this name matching unnecessary. Differences to the new
layout: all waveforms are in one `rawdata` group, the sensor name is the channel name, the quality channel is
`signalQuality`, and there is no `channel1` marking a source.

## 6. Questions for the acquisition team

1. **Lost packets.** When packets are lost, does the software write filler samples (zeros or repeated values) so the
   waveform stays gap-free, or does it leave them out? If left out, the time axis of that source would be wrong.
2. **Meaning of quality values.** Is each value the percentage of packets received in its interval? What interval, and
   is it always `wf_increment` of the quality channel?
3. **Start time.** Is `wf_start_time` UTC, and identical on all channels of an STU? May it differ between STUs
   (we assume yes)?
4. **Channels per STU.** Is 3 the maximum? Do all channels of an STU always have the same rate and length? If a slower
   auxiliary signal (e.g. temperature) must be stored, it would have to go in its own group (its own source).
5. **Names.** Can the software write channels as `channel1..channel3` with the sensor name in a `name` property, and
   the quality channel as `quality`, to match the HDF5 files (today the sensor name is the channel name and the quality
   channel is `signalQuality`)? Should group names equal the STU id?
6. **Where the data comes from.** Can the software put `stu_id`, `sth_id` and the ADC settings (`adc_reference_voltage`,
   `adc_prescaler`, `adc_acquisition_time`, `adc_oversample_rate`) on the source group, and the sensor properties
   (`sensor_id`, `sensor_type`, `dimension`, `phys_*`, `volt_*`) on the channels? Which of them does it know today?
7. **Scaling.** Are values stored raw (int16) with NI scaling, or already scaled floats?
8. **Version numbering.** Is sharing the version numbers with the HDF5 format (`1.4`) acceptable, or should TDMS have
   its own?
