"""Makes `test_with_sensors.hdf5` of schema version 2 from the real acquisition file of schema version 1
(`test/v1/test_with_sensors.hdf5`, a legacy-layout file), once:

    cd test && uv run python -m v2.make_fixture

What this conversion does is specific to that file and not a general migration of v1 to v2:

- the sensor keeps `sensor_id`, `sensor_type`, `name`, `unit` and `dimension`; the physical and voltage ranges
  are dropped;
- the channel's v1 `NoConversion` ("values already in the sensor's unit") becomes an identity `LinearConversion`
  (gain 1, offset 0), as `NoConversion` means raw voltage values in schema version 2;
- the MAC addresses of the STU and STH, which the file only has inside its opaque `pre_metadata`, become the
  source's `stu_mac` and `sth_mac`.
"""

import json
import sys
from pathlib import Path

from icoschema import v1, v2

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "v1" / "test_with_sensors.hdf5"
TARGET = HERE / "test_with_sensors.hdf5"


def convert_conversion(conversion: object) -> v2.Conversion:
    if isinstance(conversion, v1.NoConversion):
        return v2.LinearConversion(gain=1.0, offset=0.0)
    if isinstance(conversion, v1.LinearConversion):
        return v2.LinearConversion(gain=conversion.gain, offset=conversion.offset)
    raise ValueError(f"no conversion of {type(conversion).__name__} in this file")


def convert_channel(channel: v1.ChannelMetadata | None) -> v2.ChannelMetadata | None:
    if channel is None:
        return None
    (conversion,) = channel.compensations
    sensor = channel.sensor
    return v2.ChannelMetadata(
        sensor=v2.Sensor(
            sensor_id=sensor.sensor_id,
            sensor_type=sensor.sensor_type,
            name=sensor.name,
            unit=sensor.unit,
            dimension=sensor.dimension,
        ),
        conversion=convert_conversion(conversion),
    )


def convert_source(source: v1.Source) -> v2.Source:
    hardware = source.hardware_metadata
    parameters = json.loads(source.recording_metadata.pre_metadata)["parameters"]
    return v2.Source(
        name=source.name,
        stu_mac=parameters["stu_mac"],
        sth_mac=parameters["sth_mac"],
        sampling_frequency=source.sampling_frequency,
        additional_data=source.additional_data,
        hardware_metadata=v2.HardwareMetadata(
            revision=hardware.revision,
            adc_reference_voltage=hardware.adc_reference_voltage,
            adc_prescaler=hardware.adc_prescaler,
            adc_acquisition_time=hardware.adc_acquisition_time,
            adc_oversample_rate=hardware.adc_oversample_rate,
            channel1_metadata=convert_channel(hardware.channel1_metadata),
            channel2_metadata=convert_channel(hardware.channel2_metadata),
            channel3_metadata=convert_channel(hardware.channel3_metadata),
        ),
        recording_metadata=v2.RecordingMetadata(
            start_time=source.recording_metadata.start_time,
            pre_metadata=source.recording_metadata.pre_metadata,
            post_metadata=source.recording_metadata.post_metadata,
        ),
        recording_data=v2.RecordingData(
            timestamp=source.recording_data.timestamp,
            counter=source.recording_data.counter,
            channel1=source.recording_data.channel1,
            channel2=source.recording_data.channel2,
            channel3=source.recording_data.channel3,
        ),
    )


def main(target: Path = TARGET) -> None:
    old = v1.Recording.from_hdf5(str(SOURCE))
    v2.Recording(sources=[convert_source(source) for source in old.sources.values()]).to_hdf5(str(target))
    print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else TARGET)
