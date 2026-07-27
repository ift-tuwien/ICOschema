# Auto generated from dataset.yaml by pythongen.py version: 0.0.1
# Generation date: 2026-07-21T14:36:54
# Schema: dataset
#
# id: dataset_schema
# description: Schema for a recording, its derived computations, and the bundle that combines them.
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
DATASET = CurieNamespace('dataset', 'https://example.org/dataset/')
LINKML = CurieNamespace('linkml', 'https://w3id.org/linkml/')
DEFAULT_ = DATASET


# Types

# Class references
class DerivedDatasetKey(extended_str):
    pass


@dataclass(repr=False)
class RecordingMetadata(YAMLRoot):
    """
    Metadata for a recording.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["RecordingMetadata"]
    class_class_curie: ClassVar[str] = "dataset:RecordingMetadata"
    class_name: ClassVar[str] = "RecordingMetadata"
    class_model_uri: ClassVar[URIRef] = DATASET.RecordingMetadata

    start_time: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self.start_time is not None and not isinstance(self.start_time, str):
            self.start_time = str(self.start_time)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class HardwareMetadata(YAMLRoot):
    """
    Metadata containing information about the hardware used to perform the recording.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["HardwareMetadata"]
    class_class_curie: ClassVar[str] = "dataset:HardwareMetadata"
    class_name: ClassVar[str] = "HardwareMetadata"
    class_model_uri: ClassVar[URIRef] = DATASET.HardwareMetadata

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
    its raw RecordingData values to obtain a value in sensor.unit.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["ChannelMetadata"]
    class_class_curie: ClassVar[str] = "dataset:ChannelMetadata"
    class_name: ClassVar[str] = "ChannelMetadata"
    class_model_uri: ClassVar[URIRef] = DATASET.ChannelMetadata

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

    class_class_uri: ClassVar[URIRef] = DATASET["Sensor"]
    class_class_curie: ClassVar[str] = "dataset:Sensor"
    class_name: ClassVar[str] = "Sensor"
    class_model_uri: ClassVar[URIRef] = DATASET.Sensor

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
    A single compensation/correction step applied to a channel's raw RecordingData values. A channel can have several
    compensations of different kinds (e.g. a time-domain Conversion and a FrequencyCompensation); `order` records the
    sequence they were applied in.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["Compensation"]
    class_class_curie: ClassVar[str] = "dataset:Compensation"
    class_name: ClassVar[str] = "Compensation"
    class_model_uri: ClassVar[URIRef] = DATASET.Compensation

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
    A time-domain conversion of a channel's raw RecordingData values into the physical unit of its associated Sensor.
    Concrete conversions are represented by subclasses, each declaring the parameters its kind of conversion needs.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["Conversion"]
    class_class_curie: ClassVar[str] = "dataset:Conversion"
    class_name: ClassVar[str] = "Conversion"
    class_model_uri: ClassVar[URIRef] = DATASET.Conversion

    order: int = None

@dataclass(repr=False)
class NoConversion(Conversion):
    """
    No conversion is applied; values are raw ADC values.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["NoConversion"]
    class_class_curie: ClassVar[str] = "dataset:NoConversion"
    class_name: ClassVar[str] = "NoConversion"
    class_model_uri: ClassVar[URIRef] = DATASET.NoConversion

    order: int = None

@dataclass(repr=False)
class LinearConversion(Conversion):
    """
    A linear conversion: converted = raw * gain + offset.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["LinearConversion"]
    class_class_curie: ClassVar[str] = "dataset:LinearConversion"
    class_name: ClassVar[str] = "LinearConversion"
    class_model_uri: ClassVar[URIRef] = DATASET.LinearConversion

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

    class_class_uri: ClassVar[URIRef] = DATASET["PolynomialConversion"]
    class_class_curie: ClassVar[str] = "dataset:PolynomialConversion"
    class_name: ClassVar[str] = "PolynomialConversion"
    class_model_uri: ClassVar[URIRef] = DATASET.PolynomialConversion

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

    class_class_uri: ClassVar[URIRef] = DATASET["FrequencyCompensation"]
    class_class_curie: ClassVar[str] = "dataset:FrequencyCompensation"
    class_name: ClassVar[str] = "FrequencyCompensation"
    class_model_uri: ClassVar[URIRef] = DATASET.FrequencyCompensation

    order: int = None

@dataclass(repr=False)
class RecordingData(YAMLRoot):
    """
    Columnar data from a recording. Each attribute is an array of per-sample values; arrays are aligned by index (the
    i-th entry of every column belongs to the same sample), regardless of how a given adapter stores or retrieves them
    (e.g. an HDF5 table with one column per attribute, or a database query result assembled into these arrays).
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["RecordingData"]
    class_class_curie: ClassVar[str] = "dataset:RecordingData"
    class_name: ClassVar[str] = "RecordingData"
    class_model_uri: ClassVar[URIRef] = DATASET.RecordingData

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
class Recording(YAMLRoot):
    """
    A complete recording: hardware/metadata plus per-sample sensor data.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["Recording"]
    class_class_curie: ClassVar[str] = "dataset:Recording"
    class_name: ClassVar[str] = "Recording"
    class_model_uri: ClassVar[URIRef] = DATASET.Recording

    hardware_metadata: Union[dict, HardwareMetadata] = None
    recording_metadata: Union[dict, RecordingMetadata] = None
    recording_data: Union[dict, RecordingData] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.hardware_metadata):
            self.MissingRequiredField("hardware_metadata")
        if not isinstance(self.hardware_metadata, HardwareMetadata):
            self.hardware_metadata = HardwareMetadata(**as_dict(self.hardware_metadata))

        if self._is_empty(self.recording_metadata):
            self.MissingRequiredField("recording_metadata")
        if not isinstance(self.recording_metadata, RecordingMetadata):
            self.recording_metadata = RecordingMetadata(**as_dict(self.recording_metadata))

        if self._is_empty(self.recording_data):
            self.MissingRequiredField("recording_data")
        if not isinstance(self.recording_data, RecordingData):
            self.recording_data = RecordingData(**as_dict(self.recording_data))

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class DerivedDataset(YAMLRoot):
    """
    One named, computed array derived from a Recording, plus the description of how it was produced.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["DerivedDataset"]
    class_class_curie: ClassVar[str] = "dataset:DerivedDataset"
    class_name: ClassVar[str] = "DerivedDataset"
    class_model_uri: ClassVar[URIRef] = DATASET.DerivedDataset

    key: Union[str, DerivedDatasetKey] = None
    values: Union[float, list[float]] = None
    shape: Union[int, list[int]] = None
    dtype: str = None
    unit: Optional[str] = None
    produced_by: Optional[str] = None
    produced_at: Optional[str] = None
    params: Optional[str] = None
    description: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.key):
            self.MissingRequiredField("key")
        if not isinstance(self.key, DerivedDatasetKey):
            self.key = DerivedDatasetKey(self.key)

        if self._is_empty(self.values):
            self.MissingRequiredField("values")
        if not isinstance(self.values, list):
            self.values = [self.values] if self.values is not None else []
        self.values = [v if isinstance(v, float) else float(v) for v in self.values]

        if self._is_empty(self.shape):
            self.MissingRequiredField("shape")
        if not isinstance(self.shape, list):
            self.shape = [self.shape] if self.shape is not None else []
        self.shape = [v if isinstance(v, int) else int(v) for v in self.shape]

        if self._is_empty(self.dtype):
            self.MissingRequiredField("dtype")
        if not isinstance(self.dtype, str):
            self.dtype = str(self.dtype)

        if self.unit is not None and not isinstance(self.unit, str):
            self.unit = str(self.unit)

        if self.produced_by is not None and not isinstance(self.produced_by, str):
            self.produced_by = str(self.produced_by)

        if self.produced_at is not None and not isinstance(self.produced_at, str):
            self.produced_at = str(self.produced_at)

        if self.params is not None and not isinstance(self.params, str):
            self.params = str(self.params)

        if self.description is not None and not isinstance(self.description, str):
            self.description = str(self.description)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class DatasetBundle(YAMLRoot):
    """
    A Recording together with every DerivedDataset computed from it.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["DatasetBundle"]
    class_class_curie: ClassVar[str] = "dataset:DatasetBundle"
    class_name: ClassVar[str] = "DatasetBundle"
    class_model_uri: ClassVar[URIRef] = DATASET.DatasetBundle

    recording: Union[dict, Recording] = None
    computations: Optional[Union[dict[Union[str, DerivedDatasetKey], Union[dict, DerivedDataset]], list[Union[dict, DerivedDataset]]]] = empty_dict()

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.recording):
            self.MissingRequiredField("recording")
        if not isinstance(self.recording, Recording):
            self.recording = Recording(**as_dict(self.recording))

        self._normalize_inlined_as_dict(slot_name="computations", slot_type=DerivedDataset, key_name="key", keyed=True)

        super().__post_init__(**kwargs)


# Enumerations


# Slots
class slots:
    pass

slots.recordingMetadata__start_time = Slot(uri=DATASET.start_time, name="recordingMetadata__start_time", curie=DATASET.curie('start_time'),
                   model_uri=DATASET.recordingMetadata__start_time, domain=None, range=Optional[str])

slots.hardwareMetadata__revision = Slot(uri=DATASET.revision, name="hardwareMetadata__revision", curie=DATASET.curie('revision'),
                   model_uri=DATASET.hardwareMetadata__revision, domain=None, range=Optional[str])

slots.hardwareMetadata__adc_reference_voltage = Slot(uri=DATASET.adc_reference_voltage, name="hardwareMetadata__adc_reference_voltage", curie=DATASET.curie('adc_reference_voltage'),
                   model_uri=DATASET.hardwareMetadata__adc_reference_voltage, domain=None, range=Optional[str])

slots.hardwareMetadata__channel1_metadata = Slot(uri=DATASET.channel1_metadata, name="hardwareMetadata__channel1_metadata", curie=DATASET.curie('channel1_metadata'),
                   model_uri=DATASET.hardwareMetadata__channel1_metadata, domain=None, range=Union[dict, ChannelMetadata])

slots.hardwareMetadata__channel2_metadata = Slot(uri=DATASET.channel2_metadata, name="hardwareMetadata__channel2_metadata", curie=DATASET.curie('channel2_metadata'),
                   model_uri=DATASET.hardwareMetadata__channel2_metadata, domain=None, range=Optional[Union[dict, ChannelMetadata]])

slots.hardwareMetadata__channel3_metadata = Slot(uri=DATASET.channel3_metadata, name="hardwareMetadata__channel3_metadata", curie=DATASET.curie('channel3_metadata'),
                   model_uri=DATASET.hardwareMetadata__channel3_metadata, domain=None, range=Optional[Union[dict, ChannelMetadata]])

slots.channelMetadata__sensor = Slot(uri=DATASET.sensor, name="channelMetadata__sensor", curie=DATASET.curie('sensor'),
                   model_uri=DATASET.channelMetadata__sensor, domain=None, range=Union[dict, Sensor])

slots.channelMetadata__compensations = Slot(uri=DATASET.compensations, name="channelMetadata__compensations", curie=DATASET.curie('compensations'),
                   model_uri=DATASET.channelMetadata__compensations, domain=None, range=Union[Union[dict, Compensation], list[Union[dict, Compensation]]])

slots.sensor__sensor_id = Slot(uri=DATASET.sensor_id, name="sensor__sensor_id", curie=DATASET.curie('sensor_id'),
                   model_uri=DATASET.sensor__sensor_id, domain=None, range=Optional[str])

slots.sensor__sensor_type = Slot(uri=DATASET.sensor_type, name="sensor__sensor_type", curie=DATASET.curie('sensor_type'),
                   model_uri=DATASET.sensor__sensor_type, domain=None, range=Optional[str])

slots.sensor__name = Slot(uri=DATASET.name, name="sensor__name", curie=DATASET.curie('name'),
                   model_uri=DATASET.sensor__name, domain=None, range=Optional[str])

slots.sensor__unit = Slot(uri=DATASET.unit, name="sensor__unit", curie=DATASET.curie('unit'),
                   model_uri=DATASET.sensor__unit, domain=None, range=Optional[str])

slots.sensor__dimension = Slot(uri=DATASET.dimension, name="sensor__dimension", curie=DATASET.curie('dimension'),
                   model_uri=DATASET.sensor__dimension, domain=None, range=Optional[str])

slots.sensor__phys_min = Slot(uri=DATASET.phys_min, name="sensor__phys_min", curie=DATASET.curie('phys_min'),
                   model_uri=DATASET.sensor__phys_min, domain=None, range=Optional[float])

slots.sensor__phys_max = Slot(uri=DATASET.phys_max, name="sensor__phys_max", curie=DATASET.curie('phys_max'),
                   model_uri=DATASET.sensor__phys_max, domain=None, range=Optional[float])

slots.sensor__volt_min = Slot(uri=DATASET.volt_min, name="sensor__volt_min", curie=DATASET.curie('volt_min'),
                   model_uri=DATASET.sensor__volt_min, domain=None, range=Optional[float])

slots.sensor__volt_max = Slot(uri=DATASET.volt_max, name="sensor__volt_max", curie=DATASET.curie('volt_max'),
                   model_uri=DATASET.sensor__volt_max, domain=None, range=Optional[float])

slots.compensation__order = Slot(uri=DATASET.order, name="compensation__order", curie=DATASET.curie('order'),
                   model_uri=DATASET.compensation__order, domain=None, range=int)

slots.linearConversion__gain = Slot(uri=DATASET.gain, name="linearConversion__gain", curie=DATASET.curie('gain'),
                   model_uri=DATASET.linearConversion__gain, domain=None, range=float)

slots.linearConversion__offset = Slot(uri=DATASET.offset, name="linearConversion__offset", curie=DATASET.curie('offset'),
                   model_uri=DATASET.linearConversion__offset, domain=None, range=float)

slots.polynomialConversion__coefficients = Slot(uri=DATASET.coefficients, name="polynomialConversion__coefficients", curie=DATASET.curie('coefficients'),
                   model_uri=DATASET.polynomialConversion__coefficients, domain=None, range=Union[float, list[float]])

slots.recordingData__timestamp = Slot(uri=DATASET.timestamp, name="recordingData__timestamp", curie=DATASET.curie('timestamp'),
                   model_uri=DATASET.recordingData__timestamp, domain=None, range=Union[int, list[int]])

slots.recordingData__counter = Slot(uri=DATASET.counter, name="recordingData__counter", curie=DATASET.curie('counter'),
                   model_uri=DATASET.recordingData__counter, domain=None, range=Union[int, list[int]])

slots.recordingData__channel1 = Slot(uri=DATASET.channel1, name="recordingData__channel1", curie=DATASET.curie('channel1'),
                   model_uri=DATASET.recordingData__channel1, domain=None, range=Union[float, list[float]])

slots.recordingData__channel2 = Slot(uri=DATASET.channel2, name="recordingData__channel2", curie=DATASET.curie('channel2'),
                   model_uri=DATASET.recordingData__channel2, domain=None, range=Optional[Union[float, list[float]]])

slots.recordingData__channel3 = Slot(uri=DATASET.channel3, name="recordingData__channel3", curie=DATASET.curie('channel3'),
                   model_uri=DATASET.recordingData__channel3, domain=None, range=Optional[Union[float, list[float]]])

slots.recording__hardware_metadata = Slot(uri=DATASET.hardware_metadata, name="recording__hardware_metadata", curie=DATASET.curie('hardware_metadata'),
                   model_uri=DATASET.recording__hardware_metadata, domain=None, range=Union[dict, HardwareMetadata])

slots.recording__recording_metadata = Slot(uri=DATASET.recording_metadata, name="recording__recording_metadata", curie=DATASET.curie('recording_metadata'),
                   model_uri=DATASET.recording__recording_metadata, domain=None, range=Union[dict, RecordingMetadata])

slots.recording__recording_data = Slot(uri=DATASET.recording_data, name="recording__recording_data", curie=DATASET.curie('recording_data'),
                   model_uri=DATASET.recording__recording_data, domain=None, range=Union[dict, RecordingData])

slots.derivedDataset__key = Slot(uri=DATASET.key, name="derivedDataset__key", curie=DATASET.curie('key'),
                   model_uri=DATASET.derivedDataset__key, domain=None, range=URIRef)

slots.derivedDataset__values = Slot(uri=DATASET.values, name="derivedDataset__values", curie=DATASET.curie('values'),
                   model_uri=DATASET.derivedDataset__values, domain=None, range=Union[float, list[float]])

slots.derivedDataset__shape = Slot(uri=DATASET.shape, name="derivedDataset__shape", curie=DATASET.curie('shape'),
                   model_uri=DATASET.derivedDataset__shape, domain=None, range=Union[int, list[int]])

slots.derivedDataset__dtype = Slot(uri=DATASET.dtype, name="derivedDataset__dtype", curie=DATASET.curie('dtype'),
                   model_uri=DATASET.derivedDataset__dtype, domain=None, range=str)

slots.derivedDataset__unit = Slot(uri=DATASET.unit, name="derivedDataset__unit", curie=DATASET.curie('unit'),
                   model_uri=DATASET.derivedDataset__unit, domain=None, range=Optional[str])

slots.derivedDataset__produced_by = Slot(uri=DATASET.produced_by, name="derivedDataset__produced_by", curie=DATASET.curie('produced_by'),
                   model_uri=DATASET.derivedDataset__produced_by, domain=None, range=Optional[str])

slots.derivedDataset__produced_at = Slot(uri=DATASET.produced_at, name="derivedDataset__produced_at", curie=DATASET.curie('produced_at'),
                   model_uri=DATASET.derivedDataset__produced_at, domain=None, range=Optional[str])

slots.derivedDataset__params = Slot(uri=DATASET.params, name="derivedDataset__params", curie=DATASET.curie('params'),
                   model_uri=DATASET.derivedDataset__params, domain=None, range=Optional[str])

slots.derivedDataset__description = Slot(uri=DATASET.description, name="derivedDataset__description", curie=DATASET.curie('description'),
                   model_uri=DATASET.derivedDataset__description, domain=None, range=Optional[str])

slots.datasetBundle__recording = Slot(uri=DATASET.recording, name="datasetBundle__recording", curie=DATASET.curie('recording'),
                   model_uri=DATASET.datasetBundle__recording, domain=None, range=Union[dict, Recording])

slots.datasetBundle__computations = Slot(uri=DATASET.computations, name="datasetBundle__computations", curie=DATASET.curie('computations'),
                   model_uri=DATASET.datasetBundle__computations, domain=None, range=Optional[Union[dict[Union[str, DerivedDatasetKey], Union[dict, DerivedDataset]], list[Union[dict, DerivedDataset]]]])

