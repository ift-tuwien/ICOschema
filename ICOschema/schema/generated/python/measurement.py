# Auto generated from measurement.yaml by pythongen.py version: 0.0.1
# Generation date: 2026-07-07T15:04:59
# Schema: measurement
#
# id: measurement_schema
# description: Schema for a complete measurement.
# license: https://creativecommons.org/publicdomain/zero/1.0/

import dataclasses
import re
from dataclasses import dataclass
from datetime import (
    date,
    datetime,
    time
)
from typing import (
    Any,
    ClassVar,
    Dict,
    List,
    Optional,
    Union
)

from jsonasobj2 import (
    JsonObj,
    as_dict
)
from linkml_runtime.linkml_model.meta import (
    EnumDefinition,
    PermissibleValue,
    PvFormulaOptions
)
from linkml_runtime.utils.curienamespace import CurieNamespace
from linkml_runtime.utils.enumerations import EnumDefinitionImpl
from linkml_runtime.utils.formatutils import (
    camelcase,
    sfx,
    underscore
)
from linkml_runtime.utils.metamodelcore import (
    bnode,
    empty_dict,
    empty_list
)
from linkml_runtime.utils.slot import Slot
from linkml_runtime.utils.yamlutils import (
    YAMLRoot,
    extended_float,
    extended_int,
    extended_str
)
from rdflib import (
    Namespace,
    URIRef
)

from linkml_runtime.linkml_model.types import Float, Integer, String

metamodel_version = "1.11.0"
version = "0.0.1"

# Namespaces
LINKML = CurieNamespace('linkml', 'https://w3id.org/linkml/')
MEASUREMENT = CurieNamespace('measurement', 'https://example.org/measurement/')
DEFAULT_ = MEASUREMENT


# Types

# Class references



@dataclass(repr=False)
class MeasurementMetadata(YAMLRoot):
    """
    Metadata for a measurement.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["MeasurementMetadata"]
    class_class_curie: ClassVar[str] = "measurement:MeasurementMetadata"
    class_name: ClassVar[str] = "MeasurementMetadata"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.MeasurementMetadata

    start_time: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self.start_time is not None and not isinstance(self.start_time, str):
            self.start_time = str(self.start_time)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class HardwareMetadata(YAMLRoot):
    """
    Metadata containing information about the hardware used to perform the measurement.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["HardwareMetadata"]
    class_class_curie: ClassVar[str] = "measurement:HardwareMetadata"
    class_name: ClassVar[str] = "HardwareMetadata"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.HardwareMetadata

    channel1_metadata: Union[dict, "ChannelMetadata"] = None
    revision: Optional[str] = None
    adc_reference_voltage: Optional[str] = None
    channel2_metadata: Optional[Union[dict, "ChannelMetadata"]] = None
    channel3_metadata: Optional[Union[dict, "ChannelMetadata"]] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.channel1_metadata):
            self.MissingRequiredField("channel1_metadata")
        if not isinstance(self.channel1_metadata, ChannelMetadata):
            self.channel1_metadata = ChannelMetadata(**as_dict(self.channel1_metadata))

        if self.revision is not None and not isinstance(self.revision, str):
            self.revision = str(self.revision)

        if self.adc_reference_voltage is not None and not isinstance(self.adc_reference_voltage, str):
            self.adc_reference_voltage = str(self.adc_reference_voltage)

        if self.channel2_metadata is not None and not isinstance(self.channel2_metadata, ChannelMetadata):
            self.channel2_metadata = ChannelMetadata(**as_dict(self.channel2_metadata))

        if self.channel3_metadata is not None and not isinstance(self.channel3_metadata, ChannelMetadata):
            self.channel3_metadata = ChannelMetadata(**as_dict(self.channel3_metadata))

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class ChannelMetadata(YAMLRoot):
    """
    Metadata describing a single sensor channel: which physical Sensor produced it, and the compensations to apply to
    its raw MeasurementData values to obtain a value in sensor.unit.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["ChannelMetadata"]
    class_class_curie: ClassVar[str] = "measurement:ChannelMetadata"
    class_name: ClassVar[str] = "ChannelMetadata"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.ChannelMetadata

    sensor: Union[dict, "Sensor"] = None
    compensations: Union[Union[dict, "Compensation"], list[Union[dict, "Compensation"]]] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.sensor):
            self.MissingRequiredField("sensor")
        if not isinstance(self.sensor, Sensor):
            self.sensor = Sensor(**as_dict(self.sensor))

        if self._is_empty(self.compensations):
            self.MissingRequiredField("compensations")
        self._normalize_inlined_as_list(slot_name="compensations", slot_type=Compensation, key_name="order", keyed=False)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Sensor(YAMLRoot):
    """
    A physical sensor device that can produce channel data.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["Sensor"]
    class_class_curie: ClassVar[str] = "measurement:Sensor"
    class_name: ClassVar[str] = "Sensor"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.Sensor

    sensor_id: Optional[str] = None
    sensor_type: Optional[str] = None
    name: Optional[str] = None
    unit: Optional[str] = None
    dimension: Optional[str] = None
    phys_min: Optional[float] = None
    phys_max: Optional[float] = None
    volt_min: Optional[float] = None
    volt_max: Optional[float] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self.sensor_id is not None and not isinstance(self.sensor_id, str):
            self.sensor_id = str(self.sensor_id)

        if self.sensor_type is not None and not isinstance(self.sensor_type, str):
            self.sensor_type = str(self.sensor_type)

        if self.name is not None and not isinstance(self.name, str):
            self.name = str(self.name)

        if self.unit is not None and not isinstance(self.unit, str):
            self.unit = str(self.unit)

        if self.dimension is not None and not isinstance(self.dimension, str):
            self.dimension = str(self.dimension)

        if self.phys_min is not None and not isinstance(self.phys_min, float):
            self.phys_min = float(self.phys_min)

        if self.phys_max is not None and not isinstance(self.phys_max, float):
            self.phys_max = float(self.phys_max)

        if self.volt_min is not None and not isinstance(self.volt_min, float):
            self.volt_min = float(self.volt_min)

        if self.volt_max is not None and not isinstance(self.volt_max, float):
            self.volt_max = float(self.volt_max)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Compensation(YAMLRoot):
    """
    A single compensation/correction step applied to a channel's raw MeasurementData values. A channel can have
    several compensations of different kinds (e.g. a time-domain Conversion and a FrequencyCompensation); `order`
    records the sequence they were applied in.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["Compensation"]
    class_class_curie: ClassVar[str] = "measurement:Compensation"
    class_name: ClassVar[str] = "Compensation"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.Compensation

    order: int = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.order):
            self.MissingRequiredField("order")
        if not isinstance(self.order, int):
            self.order = int(self.order)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Conversion(Compensation):
    """
    A time-domain conversion of a channel's raw MeasurementData values into the physical unit of its associated
    Sensor. Concrete conversions are represented by subclasses, each declaring the parameters its kind of conversion
    needs.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["Conversion"]
    class_class_curie: ClassVar[str] = "measurement:Conversion"
    class_name: ClassVar[str] = "Conversion"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.Conversion

    order: int = None

@dataclass(repr=False)
class NoConversion(Conversion):
    """
    No conversion is applied; values are raw ADC values.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["NoConversion"]
    class_class_curie: ClassVar[str] = "measurement:NoConversion"
    class_name: ClassVar[str] = "NoConversion"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.NoConversion

    order: int = None

@dataclass(repr=False)
class LinearConversion(Conversion):
    """
    A linear conversion: converted = raw * gain + offset.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["LinearConversion"]
    class_class_curie: ClassVar[str] = "measurement:LinearConversion"
    class_name: ClassVar[str] = "LinearConversion"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.LinearConversion

    order: int = None
    gain: float = None
    offset: float = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.gain):
            self.MissingRequiredField("gain")
        if not isinstance(self.gain, float):
            self.gain = float(self.gain)

        if self._is_empty(self.offset):
            self.MissingRequiredField("offset")
        if not isinstance(self.offset, float):
            self.offset = float(self.offset)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class PolynomialConversion(Conversion):
    """
    A polynomial conversion: converted = sum(coefficients[i] * raw**i for i in range(len(coefficients))), i.e.
    coefficients are ordered from the constant term upward.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["PolynomialConversion"]
    class_class_curie: ClassVar[str] = "measurement:PolynomialConversion"
    class_name: ClassVar[str] = "PolynomialConversion"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.PolynomialConversion

    order: int = None
    coefficients: Union[float, list[float]] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.coefficients):
            self.MissingRequiredField("coefficients")
        if not isinstance(self.coefficients, list):
            self.coefficients = [self.coefficients] if self.coefficients is not None else []
        self.coefficients = [v if isinstance(v, float) else float(v) for v in self.coefficients]

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class FrequencyCompensation(Compensation):
    """
    A frequency-domain compensation applied to a channel's data (e.g. filtering or a frequency-response correction).
    Concrete compensations are represented by subclasses; none are defined yet.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["FrequencyCompensation"]
    class_class_curie: ClassVar[str] = "measurement:FrequencyCompensation"
    class_name: ClassVar[str] = "FrequencyCompensation"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.FrequencyCompensation

    order: int = None

@dataclass(repr=False)
class MeasurementData(YAMLRoot):
    """
    Columnar data from a measurement. Each attribute is an array of per-sample values; arrays are aligned by index
    (the i-th entry of every column belongs to the same sample), regardless of how a given adapter stores or retrieves
    them (e.g. an HDF5 table with one column per attribute, or a database query result assembled into these arrays).
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["MeasurementData"]
    class_class_curie: ClassVar[str] = "measurement:MeasurementData"
    class_name: ClassVar[str] = "MeasurementData"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.MeasurementData

    timestamp: Union[int, list[int]] = None
    counter: Union[int, list[int]] = None
    channel1: Union[float, list[float]] = None
    channel2: Optional[Union[float, list[float]]] = empty_list()
    channel3: Optional[Union[float, list[float]]] = empty_list()

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.timestamp):
            self.MissingRequiredField("timestamp")
        if not isinstance(self.timestamp, list):
            self.timestamp = [self.timestamp] if self.timestamp is not None else []
        self.timestamp = [v if isinstance(v, int) else int(v) for v in self.timestamp]

        if self._is_empty(self.counter):
            self.MissingRequiredField("counter")
        if not isinstance(self.counter, list):
            self.counter = [self.counter] if self.counter is not None else []
        self.counter = [v if isinstance(v, int) else int(v) for v in self.counter]

        if self._is_empty(self.channel1):
            self.MissingRequiredField("channel1")
        if not isinstance(self.channel1, list):
            self.channel1 = [self.channel1] if self.channel1 is not None else []
        self.channel1 = [v if isinstance(v, float) else float(v) for v in self.channel1]

        if not isinstance(self.channel2, list):
            self.channel2 = [self.channel2] if self.channel2 is not None else []
        self.channel2 = [v if isinstance(v, float) else float(v) for v in self.channel2]

        if not isinstance(self.channel3, list):
            self.channel3 = [self.channel3] if self.channel3 is not None else []
        self.channel3 = [v if isinstance(v, float) else float(v) for v in self.channel3]

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Measurement(YAMLRoot):
    """
    A measurement.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = MEASUREMENT["Measurement"]
    class_class_curie: ClassVar[str] = "measurement:Measurement"
    class_name: ClassVar[str] = "Measurement"
    class_model_uri: ClassVar[URIRef] = MEASUREMENT.Measurement

    hardware_metadata: Union[dict, HardwareMetadata] = None
    measurement_metadata: Union[dict, MeasurementMetadata] = None
    measurement_data: Union[dict, MeasurementData] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.hardware_metadata):
            self.MissingRequiredField("hardware_metadata")
        if not isinstance(self.hardware_metadata, HardwareMetadata):
            self.hardware_metadata = HardwareMetadata(**as_dict(self.hardware_metadata))

        if self._is_empty(self.measurement_metadata):
            self.MissingRequiredField("measurement_metadata")
        if not isinstance(self.measurement_metadata, MeasurementMetadata):
            self.measurement_metadata = MeasurementMetadata(**as_dict(self.measurement_metadata))

        if self._is_empty(self.measurement_data):
            self.MissingRequiredField("measurement_data")
        if not isinstance(self.measurement_data, MeasurementData):
            self.measurement_data = MeasurementData(**as_dict(self.measurement_data))

        super().__post_init__(**kwargs)


# Enumerations


# Slots
class slots:
    pass

slots.measurementMetadata__start_time = Slot(uri=MEASUREMENT.start_time, name="measurementMetadata__start_time", curie=MEASUREMENT.curie('start_time'),
                   model_uri=MEASUREMENT.measurementMetadata__start_time, domain=None, range=Optional[str])

slots.hardwareMetadata__revision = Slot(uri=MEASUREMENT.revision, name="hardwareMetadata__revision", curie=MEASUREMENT.curie('revision'),
                   model_uri=MEASUREMENT.hardwareMetadata__revision, domain=None, range=Optional[str])

slots.hardwareMetadata__adc_reference_voltage = Slot(uri=MEASUREMENT.adc_reference_voltage, name="hardwareMetadata__adc_reference_voltage", curie=MEASUREMENT.curie('adc_reference_voltage'),
                   model_uri=MEASUREMENT.hardwareMetadata__adc_reference_voltage, domain=None, range=Optional[str])

slots.hardwareMetadata__channel1_metadata = Slot(uri=MEASUREMENT.channel1_metadata, name="hardwareMetadata__channel1_metadata", curie=MEASUREMENT.curie('channel1_metadata'),
                   model_uri=MEASUREMENT.hardwareMetadata__channel1_metadata, domain=None, range=Union[dict, ChannelMetadata])

slots.hardwareMetadata__channel2_metadata = Slot(uri=MEASUREMENT.channel2_metadata, name="hardwareMetadata__channel2_metadata", curie=MEASUREMENT.curie('channel2_metadata'),
                   model_uri=MEASUREMENT.hardwareMetadata__channel2_metadata, domain=None, range=Optional[Union[dict, ChannelMetadata]])

slots.hardwareMetadata__channel3_metadata = Slot(uri=MEASUREMENT.channel3_metadata, name="hardwareMetadata__channel3_metadata", curie=MEASUREMENT.curie('channel3_metadata'),
                   model_uri=MEASUREMENT.hardwareMetadata__channel3_metadata, domain=None, range=Optional[Union[dict, ChannelMetadata]])

slots.channelMetadata__sensor = Slot(uri=MEASUREMENT.sensor, name="channelMetadata__sensor", curie=MEASUREMENT.curie('sensor'),
                   model_uri=MEASUREMENT.channelMetadata__sensor, domain=None, range=Union[dict, Sensor])

slots.channelMetadata__compensations = Slot(uri=MEASUREMENT.compensations, name="channelMetadata__compensations", curie=MEASUREMENT.curie('compensations'),
                   model_uri=MEASUREMENT.channelMetadata__compensations, domain=None, range=Union[Union[dict, Compensation], list[Union[dict, Compensation]]])

slots.sensor__sensor_id = Slot(uri=MEASUREMENT.sensor_id, name="sensor__sensor_id", curie=MEASUREMENT.curie('sensor_id'),
                   model_uri=MEASUREMENT.sensor__sensor_id, domain=None, range=Optional[str])

slots.sensor__sensor_type = Slot(uri=MEASUREMENT.sensor_type, name="sensor__sensor_type", curie=MEASUREMENT.curie('sensor_type'),
                   model_uri=MEASUREMENT.sensor__sensor_type, domain=None, range=Optional[str])

slots.sensor__name = Slot(uri=MEASUREMENT.name, name="sensor__name", curie=MEASUREMENT.curie('name'),
                   model_uri=MEASUREMENT.sensor__name, domain=None, range=Optional[str])

slots.sensor__unit = Slot(uri=MEASUREMENT.unit, name="sensor__unit", curie=MEASUREMENT.curie('unit'),
                   model_uri=MEASUREMENT.sensor__unit, domain=None, range=Optional[str])

slots.sensor__dimension = Slot(uri=MEASUREMENT.dimension, name="sensor__dimension", curie=MEASUREMENT.curie('dimension'),
                   model_uri=MEASUREMENT.sensor__dimension, domain=None, range=Optional[str])

slots.sensor__phys_min = Slot(uri=MEASUREMENT.phys_min, name="sensor__phys_min", curie=MEASUREMENT.curie('phys_min'),
                   model_uri=MEASUREMENT.sensor__phys_min, domain=None, range=Optional[float])

slots.sensor__phys_max = Slot(uri=MEASUREMENT.phys_max, name="sensor__phys_max", curie=MEASUREMENT.curie('phys_max'),
                   model_uri=MEASUREMENT.sensor__phys_max, domain=None, range=Optional[float])

slots.sensor__volt_min = Slot(uri=MEASUREMENT.volt_min, name="sensor__volt_min", curie=MEASUREMENT.curie('volt_min'),
                   model_uri=MEASUREMENT.sensor__volt_min, domain=None, range=Optional[float])

slots.sensor__volt_max = Slot(uri=MEASUREMENT.volt_max, name="sensor__volt_max", curie=MEASUREMENT.curie('volt_max'),
                   model_uri=MEASUREMENT.sensor__volt_max, domain=None, range=Optional[float])

slots.compensation__order = Slot(uri=MEASUREMENT.order, name="compensation__order", curie=MEASUREMENT.curie('order'),
                   model_uri=MEASUREMENT.compensation__order, domain=None, range=int)

slots.linearConversion__gain = Slot(uri=MEASUREMENT.gain, name="linearConversion__gain", curie=MEASUREMENT.curie('gain'),
                   model_uri=MEASUREMENT.linearConversion__gain, domain=None, range=float)

slots.linearConversion__offset = Slot(uri=MEASUREMENT.offset, name="linearConversion__offset", curie=MEASUREMENT.curie('offset'),
                   model_uri=MEASUREMENT.linearConversion__offset, domain=None, range=float)

slots.polynomialConversion__coefficients = Slot(uri=MEASUREMENT.coefficients, name="polynomialConversion__coefficients", curie=MEASUREMENT.curie('coefficients'),
                   model_uri=MEASUREMENT.polynomialConversion__coefficients, domain=None, range=Union[float, list[float]])

slots.measurementData__timestamp = Slot(uri=MEASUREMENT.timestamp, name="measurementData__timestamp", curie=MEASUREMENT.curie('timestamp'),
                   model_uri=MEASUREMENT.measurementData__timestamp, domain=None, range=Union[int, list[int]])

slots.measurementData__counter = Slot(uri=MEASUREMENT.counter, name="measurementData__counter", curie=MEASUREMENT.curie('counter'),
                   model_uri=MEASUREMENT.measurementData__counter, domain=None, range=Union[int, list[int]])

slots.measurementData__channel1 = Slot(uri=MEASUREMENT.channel1, name="measurementData__channel1", curie=MEASUREMENT.curie('channel1'),
                   model_uri=MEASUREMENT.measurementData__channel1, domain=None, range=Union[float, list[float]])

slots.measurementData__channel2 = Slot(uri=MEASUREMENT.channel2, name="measurementData__channel2", curie=MEASUREMENT.curie('channel2'),
                   model_uri=MEASUREMENT.measurementData__channel2, domain=None, range=Optional[Union[float, list[float]]])

slots.measurementData__channel3 = Slot(uri=MEASUREMENT.channel3, name="measurementData__channel3", curie=MEASUREMENT.curie('channel3'),
                   model_uri=MEASUREMENT.measurementData__channel3, domain=None, range=Optional[Union[float, list[float]]])

slots.measurement__hardware_metadata = Slot(uri=MEASUREMENT.hardware_metadata, name="measurement__hardware_metadata", curie=MEASUREMENT.curie('hardware_metadata'),
                   model_uri=MEASUREMENT.measurement__hardware_metadata, domain=None, range=Union[dict, HardwareMetadata])

slots.measurement__measurement_metadata = Slot(uri=MEASUREMENT.measurement_metadata, name="measurement__measurement_metadata", curie=MEASUREMENT.curie('measurement_metadata'),
                   model_uri=MEASUREMENT.measurement__measurement_metadata, domain=None, range=Union[dict, MeasurementMetadata])

slots.measurement__measurement_data = Slot(uri=MEASUREMENT.measurement_data, name="measurement__measurement_data", curie=MEASUREMENT.curie('measurement_data'),
                   model_uri=MEASUREMENT.measurement__measurement_data, domain=None, range=Union[dict, MeasurementData])

