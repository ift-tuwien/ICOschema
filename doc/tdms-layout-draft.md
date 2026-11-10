# TDMS file layout for ICOschema: draft for review

Status: **draft, not implemented.** ICOschema already reads the two layouts the acquisition software writes today
(called *legacy* below, recognised by the absence of a version property). This draft defines a clean, versioned layout
so the reader no longer has to guess. We would like the acquisition team to check every rule and answer the questions
in the last section.

## 1. Principles

- One **group per source** (one STU/STH combination). Everything belonging to a source is inside its group.
- A source is a **gap-free waveform**: sample *i* is at `start + i * wf_increment`. No timestamp or packet counter
  channel is stored; ICOschema derives the timestamps.
- The file's own start time is not stored. Each source has its own start; differences between sources are computed by
  the reader from those start times.
- Sources are independent: each has its own start, rate, length and quality.

## 2. Layout

```
File (root)
  icoschema_format_version = "1.4"      required
  name, description, author, ...        optional, kept as-is

Group "STU1"                            one per source; the group name is the source name
  stu_id            = "STU1"            optional
  sth_id            = "..."             optional
  revision          = "..."             optional (hardware revision)
  adc_reference_voltage = ...           optional
  (any other property)                  kept as-is, not interpreted
  Channel "ch1"     waveform, 1..3 per group
  Channel "ch2"
  Channel "ch3"
  Channel "signalQuality"               optional, own rate

Group "STU2"
  ... same structure ...

Group "info" (any other group)          not a source: no waveform channels with wf_increment
  (properties only)                     kept as-is, not interpreted
```

A group is a **source** if it holds at least one waveform channel other than `signalQuality`.

### 2.1 Root

| Property | Required | Meaning |
|---|---|---|
| `icoschema_format_version` | yes | `"1.4"` for this layout. Absent means legacy. Same property name as the HDF5 files. |
| anything else | no | kept as-is |

No start time at the root.

### 2.2 Source group

| Rule | Detail |
|---|---|
| Name | The source name. Non-empty, unique in the file, no `/`, not starting with `.` |
| Channels | 1 to 3 waveform channels, in file order they become `channel1..3`; the channel name is kept |
| `stu_id`, `sth_id` | optional properties, identify the STU and STH |
| `revision`, `adc_reference_voltage` | optional hardware properties |
| Other properties | kept unchanged |

### 2.3 Waveform channel (`ch1..ch3`)

| Property | Required | Meaning |
|---|---|---|
| `wf_increment` | yes | seconds between samples, > 0, **identical for all channels of the group**. The sampling rate is `1 / wf_increment` |
| `wf_start_time` | yes | start of the first sample, **UTC**, **identical for all channels of the group** |
| `wf_start_offset` | no (default 0) | seconds added to `wf_start_time` |
| `unit_string` | no | unit of the stored values |
| `sensor_id`, `sensor_type`, `dimension` | no | sensor description |
| `phys_min`, `phys_max`, `volt_min`, `volt_max` | no | sensor range, in `unit_string` / volts |
| NI scaling (`NI_Scale[...]`) | no | if present, the values are read **already scaled** (standard TDMS behaviour) and are taken to be in `unit_string`. The scaling properties are kept |

Data: numeric, **all channels of a group have exactly the same number of samples** (otherwise the file is rejected,
nothing is cut). At least one sample.

### 2.4 Quality channel (`signalQuality`)

| Property | Required | Meaning |
|---|---|---|
| `wf_increment` | recommended | seconds between quality values (its own rate, e.g. 0.1 s) |

Values are percentages 0 to 100, **100 = nothing lost**. ICOschema reports the signal loss of the source as
`100 - mean(values)`. Without this channel the loss is unknown and reported as an assumed 0 (flagged as not measured).

## 3. What ICOschema makes of it

| In the file | In ICOschema |
|---|---|
| group name | `Source.name` |
| `stu_id`, `sth_id` | `Source.stu_id`, `Source.sth_id` |
| `1 / wf_increment` | `Source.sampling_frequency` (Hz per channel) |
| `wf_start_time` + `wf_start_offset` | `RecordingMetadata.start_time` of the source |
| channel values (in file order) | `channel1..3` |
| channel name, `unit_string` | `Sensor.name`, `Sensor.unit`; no conversion (values are final) |
| `signalQuality` | `Source.quality` (values and own rate) |
| all other properties and groups | `Source.additional_data` (opaque JSON) |
| (derived) `round(i * 1e6 / fs)` | `timestamp` in microseconds |

## 4. Rejected files

A file is rejected with a clear error when: the version is unknown; a source has no waveform channel; a source has
more than 3 channels; `wf_increment` is missing, not positive or differs between channels of a group; channel lengths
differ; a channel has no data.

## 5. Legacy files

Files without `icoschema_format_version` keep working unchanged: the reader accepts a `rawdata` group with
`signalQuality` channels in a `system` group (one source) or in one group per STU, with `rawdata` channels named
`STU1_...`, `STU2_...` (several sources). The new layout makes this name matching unnecessary.

## 6. Questions for the acquisition team

1. **Lost packets.** When packets are lost, does the software write filler samples (zeros or repeated values) so the
   waveform stays gap-free, or does it leave them out? If left out, the time axis of that source would be wrong.
2. **Meaning of quality values.** Is each value the percentage of packets received in its interval? What interval, and
   is it always `wf_increment` of the quality channel?
3. **Start time.** Is `wf_start_time` UTC, and identical on all channels of an STU? May it differ between STUs
   (we assume yes)?
4. **Channels per STU.** Is 3 the maximum? Do all channels of an STU always have the same rate and length? If a slower
   auxiliary signal (e.g. temperature) must be stored, it would have to go in its own group (its own source).
5. **Names.** Fixed channel names (`ch1..ch3`) or free? Source names: should group names equal the STU id?
6. **Sensor data.** Which of the sensor properties (`sensor_id`, `sensor_type`, range) can the software write today?
7. **Scaling.** Are values stored raw (int16) with NI scaling, or already scaled floats?
8. **Version numbering.** Is sharing the version numbers with the HDF5 format (`1.4`) acceptable, or should TDMS have
   its own?
9. **Additional groups.** Keep groups such as `info`, with properties only?
