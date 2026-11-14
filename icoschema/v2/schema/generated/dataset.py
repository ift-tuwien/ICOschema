# Auto generated from dataset.yaml by pythongen.py version: 0.0.1
# Generation date: 2026-11-14T14:53:42
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
version = "2.0.0"

# Namespaces
DATASET = CurieNamespace('dataset', 'https://example.org/dataset/')
LINKML = CurieNamespace('linkml', 'https://w3id.org/linkml/')
DEFAULT_ = DATASET


# Types

# Class references
class SourceName(extended_str):
    pass


class DerivedDatasetKey(extended_str):
    pass


class ComputationStepNode(extended_str):
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
    pre_metadata: Optional[str] = None
    post_metadata: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self.start_time is not None and not isinstance(self.start_time, str):
            self.start_time = str(self.start_time)

        if self.pre_metadata is not None and not isinstance(self.pre_metadata, str):
            self.pre_metadata = str(self.pre_metadata)

        if self.post_metadata is not None and not isinstance(self.post_metadata, str):
            self.post_metadata = str(self.post_metadata)

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
    adc_prescaler: Optional[int] = None
    adc_acquisition_time: Optional[int] = None
    adc_oversample_rate: Optional[int] = None
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

        if self.adc_prescaler is not None and not isinstance(self.adc_prescaler, int):
            self.adc_prescaler = int(self.adc_prescaler)

        if self.adc_acquisition_time is not None and not isinstance(self.adc_acquisition_time, int):
            self.adc_acquisition_time = int(self.adc_acquisition_time)

        if self.adc_oversample_rate is not None and not isinstance(self.adc_oversample_rate, int):
            self.adc_oversample_rate = int(self.adc_oversample_rate)

        if self.channel2_metadata is not None and not isinstance(self.channel2_metadata, ChannelMetadata):
            self.channel2_metadata = ChannelMetadata(**as_dict(self.channel2_metadata))

        if self.channel3_metadata is not None and not isinstance(self.channel3_metadata, ChannelMetadata):
            self.channel3_metadata = ChannelMetadata(**as_dict(self.channel3_metadata))

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class ChannelMetadata(YAMLRoot):
    """
    Metadata describing a single sensor channel: which physical sensor produced it, and the conversion that was
    applied to its raw values to get its RecordingData values.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["ChannelMetadata"]
    class_class_curie: ClassVar[str] = "dataset:ChannelMetadata"
    class_name: ClassVar[str] = "ChannelMetadata"
    class_model_uri: ClassVar[URIRef] = DATASET.ChannelMetadata

    sensor: Union[dict, "Sensor"] = None
    conversion: Union[dict, "Conversion"] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.sensor):
            self.MissingRequiredField("sensor")
        if not isinstance(self.sensor, Sensor):
            self.sensor = Sensor(**as_dict(self.sensor))

        if self._is_empty(self.conversion):
            self.MissingRequiredField("conversion")
        if not isinstance(self.conversion, Conversion):
            self.conversion = Conversion(**as_dict(self.conversion))

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

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Conversion(YAMLRoot):
    """
    A conversion that was applied to a channel's raw (voltage) values to get the values stored in its RecordingData,
    so that they are in the physical unit of its associated Sensor. Concrete conversions are represented by
    subclasses, each declaring the parameters its kind of conversion needs.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["Conversion"]
    class_class_curie: ClassVar[str] = "dataset:Conversion"
    class_name: ClassVar[str] = "Conversion"
    class_model_uri: ClassVar[URIRef] = DATASET.Conversion

    conversion_type: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        self.conversion_type = str(self.class_name)

        super().__post_init__(**kwargs)
        self.unknown_conversion_type = str(self.class_name)


    def __new__(cls, *args, **kwargs):

        type_designator = "conversion_type"
        if not type_designator in kwargs:
            return super().__new__(cls,*args,**kwargs)
        else:
            type_designator_value = kwargs[type_designator]
            target_cls = cls._class_for("class_name", type_designator_value)


            if target_cls is None:
                raise ValueError(f"Wrong type designator value: class {cls.__name__} "
                                 f"has no subclass with ['class_name']='{kwargs[type_designator]}'")
            return super().__new__(target_cls,*args,**kwargs)



class NoConversion(Conversion):
    """
    No conversion was applied: the channel's values are raw voltage values.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["NoConversion"]
    class_class_curie: ClassVar[str] = "dataset:NoConversion"
    class_name: ClassVar[str] = "NoConversion"
    class_model_uri: ClassVar[URIRef] = DATASET.NoConversion


    def __post_init__(self, *_: str, **kwargs: Any):

        super().__post_init__(**kwargs)
        self.unknown_conversion_type = str(self.class_name)


@dataclass(repr=False)
class LinearConversion(Conversion):
    """
    A linear conversion that was applied: stored = raw * gain + offset, with the stored value in the unit of the
    channel's Sensor. A gain of 1 and an offset of 0 is a conversion that changed nothing (values that were in the
    unit already).
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["LinearConversion"]
    class_class_curie: ClassVar[str] = "dataset:LinearConversion"
    class_name: ClassVar[str] = "LinearConversion"
    class_model_uri: ClassVar[URIRef] = DATASET.LinearConversion

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
        self.unknown_conversion_type = str(self.class_name)


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
    channel1: Union[float, list[float]] = None
    counter: Optional[Union[int, list[int]]] = empty_list()
    channel2: Optional[Union[float, list[float]]] = empty_list()
    channel3: Optional[Union[float, list[float]]] = empty_list()

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.timestamp):
            self.MissingRequiredField("timestamp")
        if not isinstance(self.timestamp, list):
            self.timestamp = [self.timestamp] if self.timestamp is not None else []
        self.timestamp = [v if isinstance(v, int) else int(v) for v in self.timestamp]

        if self._is_empty(self.channel1):
            self.MissingRequiredField("channel1")
        if not isinstance(self.channel1, list):
            self.channel1 = [self.channel1] if self.channel1 is not None else []
        self.channel1 = [v if isinstance(v, float) else float(v) for v in self.channel1]

        if not isinstance(self.counter, list):
            self.counter = [self.counter] if self.counter is not None else []
        self.counter = [v if isinstance(v, int) else int(v) for v in self.counter]

        if not isinstance(self.channel2, list):
            self.channel2 = [self.channel2] if self.channel2 is not None else []
        self.channel2 = [v if isinstance(v, float) else float(v) for v in self.channel2]

        if not isinstance(self.channel3, list):
            self.channel3 = [self.channel3] if self.channel3 is not None else []
        self.channel3 = [v if isinstance(v, float) else float(v) for v in self.channel3]

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Source(YAMLRoot):
    """
    The data of one acquisition source, i.e. one STU/STH combination: its hardware/sensor metadata and its per-sample
    data. Sources are independent -- each has its own clock (RecordingMetadata.start_time), packet counter, ADC
    settings (hence its own sampling frequency) and sensors -- so sources of one Recording may differ in all of these.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["Source"]
    class_class_curie: ClassVar[str] = "dataset:Source"
    class_name: ClassVar[str] = "Source"
    class_model_uri: ClassVar[URIRef] = DATASET.Source

    name: Union[str, SourceName] = None
    hardware_metadata: Union[dict, HardwareMetadata] = None
    recording_metadata: Union[dict, RecordingMetadata] = None
    recording_data: Union[dict, RecordingData] = None
    description: Optional[str] = None
    stu_mac: Optional[str] = None
    sth_mac: Optional[str] = None
    sampling_frequency: Optional[float] = None
    quality: Optional[Union[dict, "QualityChannel"]] = None
    additional_data: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.name):
            self.MissingRequiredField("name")
        if not isinstance(self.name, SourceName):
            self.name = SourceName(self.name)

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

        if self.description is not None and not isinstance(self.description, str):
            self.description = str(self.description)

        if self.stu_mac is not None and not isinstance(self.stu_mac, str):
            self.stu_mac = str(self.stu_mac)

        if self.sth_mac is not None and not isinstance(self.sth_mac, str):
            self.sth_mac = str(self.sth_mac)

        if self.sampling_frequency is not None and not isinstance(self.sampling_frequency, float):
            self.sampling_frequency = float(self.sampling_frequency)

        if self.quality is not None and not isinstance(self.quality, QualityChannel):
            self.quality = QualityChannel(**as_dict(self.quality))

        if self.additional_data is not None and not isinstance(self.additional_data, str):
            self.additional_data = str(self.additional_data)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class QualityChannel(YAMLRoot):
    """
    A signal-quality series of one source: percentages, 100 meaning nothing was lost. Sampled independently of the
    source's channels.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["QualityChannel"]
    class_class_curie: ClassVar[str] = "dataset:QualityChannel"
    class_name: ClassVar[str] = "QualityChannel"
    class_model_uri: ClassVar[URIRef] = DATASET.QualityChannel

    values: Union[float, list[float]] = None
    sampling_frequency: Optional[float] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.values):
            self.MissingRequiredField("values")
        if not isinstance(self.values, list):
            self.values = [self.values] if self.values is not None else []
        self.values = [v if isinstance(v, float) else float(v) for v in self.values]

        if self.sampling_frequency is not None and not isinstance(self.sampling_frequency, float):
            self.sampling_frequency = float(self.sampling_frequency)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Recording(YAMLRoot):
    """
    A complete recording: one or more independent Sources, each with its hardware/metadata plus per-sample sensor data.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["Recording"]
    class_class_curie: ClassVar[str] = "dataset:Recording"
    class_name: ClassVar[str] = "Recording"
    class_model_uri: ClassVar[URIRef] = DATASET.Recording

    sources: Union[dict[Union[str, SourceName], Union[dict, Source]], list[Union[dict, Source]]] = empty_dict()

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.sources):
            self.MissingRequiredField("sources")
        self._normalize_inlined_as_dict(slot_name="sources", slot_type=Source, key_name="name", keyed=True)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class PreprocessedRecording(YAMLRoot):
    """
    The raw RecordingData channels placed on the gap-free sample grid (lost packets filled) with timestamps rebased to
    1 / sampling frequency. Row j is grid position j, where position 0 is the first received raw row. Channel values
    are copied from RecordingData as stored, whatever their conversions say: they share the Recording's
    HardwareMetadata (sensors, conversions) and mean exactly what the raw channels mean. Built from one Source of the
    Recording.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["PreprocessedRecording"]
    class_class_curie: ClassVar[str] = "dataset:PreprocessedRecording"
    class_name: ClassVar[str] = "PreprocessedRecording"
    class_model_uri: ClassVar[URIRef] = DATASET.PreprocessedRecording

    timestamp: Union[int, list[int]] = None
    channel1: Union[float, list[float]] = None
    channel_sampling_frequency: float = None
    sampling_frequency_source: Union[str, "SamplingFrequencySource"] = None
    fill_method: str = None
    producer: str = None
    channel2: Optional[Union[float, list[float]]] = empty_list()
    channel3: Optional[Union[float, list[float]]] = empty_list()
    source: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.timestamp):
            self.MissingRequiredField("timestamp")
        if not isinstance(self.timestamp, list):
            self.timestamp = [self.timestamp] if self.timestamp is not None else []
        self.timestamp = [v if isinstance(v, int) else int(v) for v in self.timestamp]

        if self._is_empty(self.channel1):
            self.MissingRequiredField("channel1")
        if not isinstance(self.channel1, list):
            self.channel1 = [self.channel1] if self.channel1 is not None else []
        self.channel1 = [v if isinstance(v, float) else float(v) for v in self.channel1]

        if self._is_empty(self.channel_sampling_frequency):
            self.MissingRequiredField("channel_sampling_frequency")
        if not isinstance(self.channel_sampling_frequency, float):
            self.channel_sampling_frequency = float(self.channel_sampling_frequency)

        if self._is_empty(self.sampling_frequency_source):
            self.MissingRequiredField("sampling_frequency_source")
        if not isinstance(self.sampling_frequency_source, SamplingFrequencySource):
            self.sampling_frequency_source = SamplingFrequencySource(self.sampling_frequency_source)

        if self._is_empty(self.fill_method):
            self.MissingRequiredField("fill_method")
        if not isinstance(self.fill_method, str):
            self.fill_method = str(self.fill_method)

        if self._is_empty(self.producer):
            self.MissingRequiredField("producer")
        if not isinstance(self.producer, str):
            self.producer = str(self.producer)

        if not isinstance(self.channel2, list):
            self.channel2 = [self.channel2] if self.channel2 is not None else []
        self.channel2 = [v if isinstance(v, float) else float(v) for v in self.channel2]

        if not isinstance(self.channel3, list):
            self.channel3 = [self.channel3] if self.channel3 is not None else []
        self.channel3 = [v if isinstance(v, float) else float(v) for v in self.channel3]

        if self.source is not None and not isinstance(self.source, str):
            self.source = str(self.source)

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
class ComputationStep(YAMLRoot):
    """
    The record of one computation step that produced (or failed to produce) DerivedDatasets in a bundle: what ran,
    with which parameters, in which order, and which computations it wrote. Generic provenance -- how producers name
    steps or derive keys from them is up to them.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["ComputationStep"]
    class_class_curie: ClassVar[str] = "dataset:ComputationStep"
    class_name: ClassVar[str] = "ComputationStep"
    class_model_uri: ClassVar[URIRef] = DATASET.ComputationStep

    node: Union[str, ComputationStepNode] = None
    step_index: int = None
    producer: str = None
    params: Optional[str] = None
    resolved_params: Optional[str] = None
    inputs: Optional[Union[str, list[str]]] = empty_list()
    status: Optional[Union[str, "ComputationStatus"]] = None
    error: Optional[str] = None
    summary: Optional[str] = None
    output_keys: Optional[Union[str, list[str]]] = empty_list()
    started_at: Optional[str] = None
    duration_s: Optional[float] = None
    environment: Optional[str] = None
    source_node: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.node):
            self.MissingRequiredField("node")
        if not isinstance(self.node, ComputationStepNode):
            self.node = ComputationStepNode(self.node)

        if self._is_empty(self.step_index):
            self.MissingRequiredField("step_index")
        if not isinstance(self.step_index, int):
            self.step_index = int(self.step_index)

        if self._is_empty(self.producer):
            self.MissingRequiredField("producer")
        if not isinstance(self.producer, str):
            self.producer = str(self.producer)

        if self.params is not None and not isinstance(self.params, str):
            self.params = str(self.params)

        if self.resolved_params is not None and not isinstance(self.resolved_params, str):
            self.resolved_params = str(self.resolved_params)

        if not isinstance(self.inputs, list):
            self.inputs = [self.inputs] if self.inputs is not None else []
        self.inputs = [v if isinstance(v, str) else str(v) for v in self.inputs]

        if self.status is not None and not isinstance(self.status, ComputationStatus):
            self.status = ComputationStatus(self.status)

        if self.error is not None and not isinstance(self.error, str):
            self.error = str(self.error)

        if self.summary is not None and not isinstance(self.summary, str):
            self.summary = str(self.summary)

        if not isinstance(self.output_keys, list):
            self.output_keys = [self.output_keys] if self.output_keys is not None else []
        self.output_keys = [v if isinstance(v, str) else str(v) for v in self.output_keys]

        if self.started_at is not None and not isinstance(self.started_at, str):
            self.started_at = str(self.started_at)

        if self.duration_s is not None and not isinstance(self.duration_s, float):
            self.duration_s = float(self.duration_s)

        if self.environment is not None and not isinstance(self.environment, str):
            self.environment = str(self.environment)

        if self.source_node is not None and not isinstance(self.source_node, str):
            self.source_node = str(self.source_node)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class Provenance(YAMLRoot):
    """
    Where a DatasetBundle was read from and by what it was written.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["Provenance"]
    class_class_curie: ClassVar[str] = "dataset:Provenance"
    class_name: ClassVar[str] = "Provenance"
    class_model_uri: ClassVar[URIRef] = DATASET.Provenance

    source_format: Optional[str] = None
    source_format_version: Optional[str] = None
    reader: Optional[str] = None
    writer: Optional[str] = None

    def __post_init__(self, *_: str, **kwargs: Any):
        if self.source_format is not None and not isinstance(self.source_format, str):
            self.source_format = str(self.source_format)

        if self.source_format_version is not None and not isinstance(self.source_format_version, str):
            self.source_format_version = str(self.source_format_version)

        if self.reader is not None and not isinstance(self.reader, str):
            self.reader = str(self.reader)

        if self.writer is not None and not isinstance(self.writer, str):
            self.writer = str(self.writer)

        super().__post_init__(**kwargs)


@dataclass(repr=False)
class DatasetBundle(YAMLRoot):
    """
    A Recording together with its optional PreprocessedRecordings (at most one per source), every DerivedDataset
    computed from them, and the ComputationSteps that produced them.
    """
    _inherited_slots: ClassVar[list[str]] = []

    class_class_uri: ClassVar[URIRef] = DATASET["DatasetBundle"]
    class_class_curie: ClassVar[str] = "dataset:DatasetBundle"
    class_name: ClassVar[str] = "DatasetBundle"
    class_model_uri: ClassVar[URIRef] = DATASET.DatasetBundle

    recording: Union[dict, Recording] = None
    provenance: Optional[Union[dict, Provenance]] = None
    preprocessed_tables: Optional[Union[Union[dict, PreprocessedRecording], list[Union[dict, PreprocessedRecording]]]] = empty_list()
    computations: Optional[Union[dict[Union[str, DerivedDatasetKey], Union[dict, DerivedDataset]], list[Union[dict, DerivedDataset]]]] = empty_dict()
    steps: Optional[Union[dict[Union[str, ComputationStepNode], Union[dict, ComputationStep]], list[Union[dict, ComputationStep]]]] = empty_dict()

    def __post_init__(self, *_: str, **kwargs: Any):
        if self._is_empty(self.recording):
            self.MissingRequiredField("recording")
        if not isinstance(self.recording, Recording):
            self.recording = Recording(**as_dict(self.recording))

        if self.provenance is not None and not isinstance(self.provenance, Provenance):
            self.provenance = Provenance(**as_dict(self.provenance))

        self._normalize_inlined_as_list(slot_name="preprocessed_tables", slot_type=PreprocessedRecording, key_name="timestamp", keyed=False)

        self._normalize_inlined_as_dict(slot_name="computations", slot_type=DerivedDataset, key_name="key", keyed=True)

        self._normalize_inlined_as_list(slot_name="steps", slot_type=ComputationStep, key_name="node", keyed=True)

        super().__post_init__(**kwargs)


# Enumerations
class ComputationStatus(EnumDefinitionImpl):
    """
    Whether a ComputationStep succeeded.
    """
    ok = PermissibleValue(
        text="ok",
        description="The step ran and wrote its output_keys.")
    error = PermissibleValue(
        text="error",
        description="The step raised; see ComputationStep.error.")

    _defn = EnumDefinition(
        name="ComputationStatus",
        description="Whether a ComputationStep succeeded.",
    )

class SamplingFrequencySource(EnumDefinitionImpl):
    """
    Where a per-channel sampling frequency came from.
    """
    override = PermissibleValue(
        text="override",
        description="Given explicitly by whoever produced the data.")
    hardware = PermissibleValue(
        text="hardware",
        description="Computed from the ADC settings recorded in HardwareMetadata.")
    default = PermissibleValue(
        text="default",
        description="Computed from the default ADC settings, because the recording doesn't record its own.")

    _defn = EnumDefinition(
        name="SamplingFrequencySource",
        description="Where a per-channel sampling frequency came from.",
    )

# Slots
class slots:
    pass

slots.recordingMetadata__start_time = Slot(uri=DATASET.start_time, name="recordingMetadata__start_time", curie=DATASET.curie('start_time'),
                   model_uri=DATASET.recordingMetadata__start_time, domain=None, range=Optional[str])

slots.recordingMetadata__pre_metadata = Slot(uri=DATASET.pre_metadata, name="recordingMetadata__pre_metadata", curie=DATASET.curie('pre_metadata'),
                   model_uri=DATASET.recordingMetadata__pre_metadata, domain=None, range=Optional[str])

slots.recordingMetadata__post_metadata = Slot(uri=DATASET.post_metadata, name="recordingMetadata__post_metadata", curie=DATASET.curie('post_metadata'),
                   model_uri=DATASET.recordingMetadata__post_metadata, domain=None, range=Optional[str])

slots.hardwareMetadata__revision = Slot(uri=DATASET.revision, name="hardwareMetadata__revision", curie=DATASET.curie('revision'),
                   model_uri=DATASET.hardwareMetadata__revision, domain=None, range=Optional[str])

slots.hardwareMetadata__adc_reference_voltage = Slot(uri=DATASET.adc_reference_voltage, name="hardwareMetadata__adc_reference_voltage", curie=DATASET.curie('adc_reference_voltage'),
                   model_uri=DATASET.hardwareMetadata__adc_reference_voltage, domain=None, range=Optional[str])

slots.hardwareMetadata__adc_prescaler = Slot(uri=DATASET.adc_prescaler, name="hardwareMetadata__adc_prescaler", curie=DATASET.curie('adc_prescaler'),
                   model_uri=DATASET.hardwareMetadata__adc_prescaler, domain=None, range=Optional[int])

slots.hardwareMetadata__adc_acquisition_time = Slot(uri=DATASET.adc_acquisition_time, name="hardwareMetadata__adc_acquisition_time", curie=DATASET.curie('adc_acquisition_time'),
                   model_uri=DATASET.hardwareMetadata__adc_acquisition_time, domain=None, range=Optional[int])

slots.hardwareMetadata__adc_oversample_rate = Slot(uri=DATASET.adc_oversample_rate, name="hardwareMetadata__adc_oversample_rate", curie=DATASET.curie('adc_oversample_rate'),
                   model_uri=DATASET.hardwareMetadata__adc_oversample_rate, domain=None, range=Optional[int])

slots.hardwareMetadata__channel1_metadata = Slot(uri=DATASET.channel1_metadata, name="hardwareMetadata__channel1_metadata", curie=DATASET.curie('channel1_metadata'),
                   model_uri=DATASET.hardwareMetadata__channel1_metadata, domain=None, range=Union[dict, ChannelMetadata])

slots.hardwareMetadata__channel2_metadata = Slot(uri=DATASET.channel2_metadata, name="hardwareMetadata__channel2_metadata", curie=DATASET.curie('channel2_metadata'),
                   model_uri=DATASET.hardwareMetadata__channel2_metadata, domain=None, range=Optional[Union[dict, ChannelMetadata]])

slots.hardwareMetadata__channel3_metadata = Slot(uri=DATASET.channel3_metadata, name="hardwareMetadata__channel3_metadata", curie=DATASET.curie('channel3_metadata'),
                   model_uri=DATASET.hardwareMetadata__channel3_metadata, domain=None, range=Optional[Union[dict, ChannelMetadata]])

slots.channelMetadata__sensor = Slot(uri=DATASET.sensor, name="channelMetadata__sensor", curie=DATASET.curie('sensor'),
                   model_uri=DATASET.channelMetadata__sensor, domain=None, range=Union[dict, Sensor])

slots.channelMetadata__conversion = Slot(uri=DATASET.conversion, name="channelMetadata__conversion", curie=DATASET.curie('conversion'),
                   model_uri=DATASET.channelMetadata__conversion, domain=None, range=Union[dict, Conversion])

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

slots.conversion__conversion_type = Slot(uri=DATASET.conversion_type, name="conversion__conversion_type", curie=DATASET.curie('conversion_type'),
                   model_uri=DATASET.conversion__conversion_type, domain=None, range=Optional[str])

slots.linearConversion__gain = Slot(uri=DATASET.gain, name="linearConversion__gain", curie=DATASET.curie('gain'),
                   model_uri=DATASET.linearConversion__gain, domain=None, range=float)

slots.linearConversion__offset = Slot(uri=DATASET.offset, name="linearConversion__offset", curie=DATASET.curie('offset'),
                   model_uri=DATASET.linearConversion__offset, domain=None, range=float)

slots.recordingData__timestamp = Slot(uri=DATASET.timestamp, name="recordingData__timestamp", curie=DATASET.curie('timestamp'),
                   model_uri=DATASET.recordingData__timestamp, domain=None, range=Union[int, list[int]])

slots.recordingData__counter = Slot(uri=DATASET.counter, name="recordingData__counter", curie=DATASET.curie('counter'),
                   model_uri=DATASET.recordingData__counter, domain=None, range=Optional[Union[int, list[int]]])

slots.recordingData__channel1 = Slot(uri=DATASET.channel1, name="recordingData__channel1", curie=DATASET.curie('channel1'),
                   model_uri=DATASET.recordingData__channel1, domain=None, range=Union[float, list[float]])

slots.recordingData__channel2 = Slot(uri=DATASET.channel2, name="recordingData__channel2", curie=DATASET.curie('channel2'),
                   model_uri=DATASET.recordingData__channel2, domain=None, range=Optional[Union[float, list[float]]])

slots.recordingData__channel3 = Slot(uri=DATASET.channel3, name="recordingData__channel3", curie=DATASET.curie('channel3'),
                   model_uri=DATASET.recordingData__channel3, domain=None, range=Optional[Union[float, list[float]]])

slots.source__name = Slot(uri=DATASET.name, name="source__name", curie=DATASET.curie('name'),
                   model_uri=DATASET.source__name, domain=None, range=URIRef)

slots.source__description = Slot(uri=DATASET.description, name="source__description", curie=DATASET.curie('description'),
                   model_uri=DATASET.source__description, domain=None, range=Optional[str])

slots.source__stu_mac = Slot(uri=DATASET.stu_mac, name="source__stu_mac", curie=DATASET.curie('stu_mac'),
                   model_uri=DATASET.source__stu_mac, domain=None, range=Optional[str])

slots.source__sth_mac = Slot(uri=DATASET.sth_mac, name="source__sth_mac", curie=DATASET.curie('sth_mac'),
                   model_uri=DATASET.source__sth_mac, domain=None, range=Optional[str])

slots.source__sampling_frequency = Slot(uri=DATASET.sampling_frequency, name="source__sampling_frequency", curie=DATASET.curie('sampling_frequency'),
                   model_uri=DATASET.source__sampling_frequency, domain=None, range=Optional[float])

slots.source__quality = Slot(uri=DATASET.quality, name="source__quality", curie=DATASET.curie('quality'),
                   model_uri=DATASET.source__quality, domain=None, range=Optional[Union[dict, QualityChannel]])

slots.source__additional_data = Slot(uri=DATASET.additional_data, name="source__additional_data", curie=DATASET.curie('additional_data'),
                   model_uri=DATASET.source__additional_data, domain=None, range=Optional[str])

slots.source__hardware_metadata = Slot(uri=DATASET.hardware_metadata, name="source__hardware_metadata", curie=DATASET.curie('hardware_metadata'),
                   model_uri=DATASET.source__hardware_metadata, domain=None, range=Union[dict, HardwareMetadata])

slots.source__recording_metadata = Slot(uri=DATASET.recording_metadata, name="source__recording_metadata", curie=DATASET.curie('recording_metadata'),
                   model_uri=DATASET.source__recording_metadata, domain=None, range=Union[dict, RecordingMetadata])

slots.source__recording_data = Slot(uri=DATASET.recording_data, name="source__recording_data", curie=DATASET.curie('recording_data'),
                   model_uri=DATASET.source__recording_data, domain=None, range=Union[dict, RecordingData])

slots.qualityChannel__values = Slot(uri=DATASET.values, name="qualityChannel__values", curie=DATASET.curie('values'),
                   model_uri=DATASET.qualityChannel__values, domain=None, range=Union[float, list[float]])

slots.qualityChannel__sampling_frequency = Slot(uri=DATASET.sampling_frequency, name="qualityChannel__sampling_frequency", curie=DATASET.curie('sampling_frequency'),
                   model_uri=DATASET.qualityChannel__sampling_frequency, domain=None, range=Optional[float])

slots.recording__sources = Slot(uri=DATASET.sources, name="recording__sources", curie=DATASET.curie('sources'),
                   model_uri=DATASET.recording__sources, domain=None, range=Union[dict[Union[str, SourceName], Union[dict, Source]], list[Union[dict, Source]]])

slots.preprocessedRecording__timestamp = Slot(uri=DATASET.timestamp, name="preprocessedRecording__timestamp", curie=DATASET.curie('timestamp'),
                   model_uri=DATASET.preprocessedRecording__timestamp, domain=None, range=Union[int, list[int]])

slots.preprocessedRecording__channel1 = Slot(uri=DATASET.channel1, name="preprocessedRecording__channel1", curie=DATASET.curie('channel1'),
                   model_uri=DATASET.preprocessedRecording__channel1, domain=None, range=Union[float, list[float]])

slots.preprocessedRecording__channel2 = Slot(uri=DATASET.channel2, name="preprocessedRecording__channel2", curie=DATASET.curie('channel2'),
                   model_uri=DATASET.preprocessedRecording__channel2, domain=None, range=Optional[Union[float, list[float]]])

slots.preprocessedRecording__channel3 = Slot(uri=DATASET.channel3, name="preprocessedRecording__channel3", curie=DATASET.curie('channel3'),
                   model_uri=DATASET.preprocessedRecording__channel3, domain=None, range=Optional[Union[float, list[float]]])

slots.preprocessedRecording__channel_sampling_frequency = Slot(uri=DATASET.channel_sampling_frequency, name="preprocessedRecording__channel_sampling_frequency", curie=DATASET.curie('channel_sampling_frequency'),
                   model_uri=DATASET.preprocessedRecording__channel_sampling_frequency, domain=None, range=float)

slots.preprocessedRecording__sampling_frequency_source = Slot(uri=DATASET.sampling_frequency_source, name="preprocessedRecording__sampling_frequency_source", curie=DATASET.curie('sampling_frequency_source'),
                   model_uri=DATASET.preprocessedRecording__sampling_frequency_source, domain=None, range=Union[str, "SamplingFrequencySource"])

slots.preprocessedRecording__fill_method = Slot(uri=DATASET.fill_method, name="preprocessedRecording__fill_method", curie=DATASET.curie('fill_method'),
                   model_uri=DATASET.preprocessedRecording__fill_method, domain=None, range=str)

slots.preprocessedRecording__producer = Slot(uri=DATASET.producer, name="preprocessedRecording__producer", curie=DATASET.curie('producer'),
                   model_uri=DATASET.preprocessedRecording__producer, domain=None, range=str)

slots.preprocessedRecording__source = Slot(uri=DATASET.source, name="preprocessedRecording__source", curie=DATASET.curie('source'),
                   model_uri=DATASET.preprocessedRecording__source, domain=None, range=Optional[str])

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

slots.computationStep__node = Slot(uri=DATASET.node, name="computationStep__node", curie=DATASET.curie('node'),
                   model_uri=DATASET.computationStep__node, domain=None, range=URIRef)

slots.computationStep__step_index = Slot(uri=DATASET.step_index, name="computationStep__step_index", curie=DATASET.curie('step_index'),
                   model_uri=DATASET.computationStep__step_index, domain=None, range=int)

slots.computationStep__producer = Slot(uri=DATASET.producer, name="computationStep__producer", curie=DATASET.curie('producer'),
                   model_uri=DATASET.computationStep__producer, domain=None, range=str)

slots.computationStep__params = Slot(uri=DATASET.params, name="computationStep__params", curie=DATASET.curie('params'),
                   model_uri=DATASET.computationStep__params, domain=None, range=Optional[str])

slots.computationStep__resolved_params = Slot(uri=DATASET.resolved_params, name="computationStep__resolved_params", curie=DATASET.curie('resolved_params'),
                   model_uri=DATASET.computationStep__resolved_params, domain=None, range=Optional[str])

slots.computationStep__inputs = Slot(uri=DATASET.inputs, name="computationStep__inputs", curie=DATASET.curie('inputs'),
                   model_uri=DATASET.computationStep__inputs, domain=None, range=Optional[Union[str, list[str]]])

slots.computationStep__status = Slot(uri=DATASET.status, name="computationStep__status", curie=DATASET.curie('status'),
                   model_uri=DATASET.computationStep__status, domain=None, range=Optional[Union[str, "ComputationStatus"]])

slots.computationStep__error = Slot(uri=DATASET.error, name="computationStep__error", curie=DATASET.curie('error'),
                   model_uri=DATASET.computationStep__error, domain=None, range=Optional[str])

slots.computationStep__summary = Slot(uri=DATASET.summary, name="computationStep__summary", curie=DATASET.curie('summary'),
                   model_uri=DATASET.computationStep__summary, domain=None, range=Optional[str])

slots.computationStep__output_keys = Slot(uri=DATASET.output_keys, name="computationStep__output_keys", curie=DATASET.curie('output_keys'),
                   model_uri=DATASET.computationStep__output_keys, domain=None, range=Optional[Union[str, list[str]]])

slots.computationStep__started_at = Slot(uri=DATASET.started_at, name="computationStep__started_at", curie=DATASET.curie('started_at'),
                   model_uri=DATASET.computationStep__started_at, domain=None, range=Optional[str])

slots.computationStep__duration_s = Slot(uri=DATASET.duration_s, name="computationStep__duration_s", curie=DATASET.curie('duration_s'),
                   model_uri=DATASET.computationStep__duration_s, domain=None, range=Optional[float])

slots.computationStep__environment = Slot(uri=DATASET.environment, name="computationStep__environment", curie=DATASET.curie('environment'),
                   model_uri=DATASET.computationStep__environment, domain=None, range=Optional[str])

slots.computationStep__source_node = Slot(uri=DATASET.source_node, name="computationStep__source_node", curie=DATASET.curie('source_node'),
                   model_uri=DATASET.computationStep__source_node, domain=None, range=Optional[str])

slots.provenance__source_format = Slot(uri=DATASET.source_format, name="provenance__source_format", curie=DATASET.curie('source_format'),
                   model_uri=DATASET.provenance__source_format, domain=None, range=Optional[str])

slots.provenance__source_format_version = Slot(uri=DATASET.source_format_version, name="provenance__source_format_version", curie=DATASET.curie('source_format_version'),
                   model_uri=DATASET.provenance__source_format_version, domain=None, range=Optional[str])

slots.provenance__reader = Slot(uri=DATASET.reader, name="provenance__reader", curie=DATASET.curie('reader'),
                   model_uri=DATASET.provenance__reader, domain=None, range=Optional[str])

slots.provenance__writer = Slot(uri=DATASET.writer, name="provenance__writer", curie=DATASET.curie('writer'),
                   model_uri=DATASET.provenance__writer, domain=None, range=Optional[str])

slots.datasetBundle__recording = Slot(uri=DATASET.recording, name="datasetBundle__recording", curie=DATASET.curie('recording'),
                   model_uri=DATASET.datasetBundle__recording, domain=None, range=Union[dict, Recording])

slots.datasetBundle__provenance = Slot(uri=DATASET.provenance, name="datasetBundle__provenance", curie=DATASET.curie('provenance'),
                   model_uri=DATASET.datasetBundle__provenance, domain=None, range=Optional[Union[dict, Provenance]])

slots.datasetBundle__preprocessed_tables = Slot(uri=DATASET.preprocessed_tables, name="datasetBundle__preprocessed_tables", curie=DATASET.curie('preprocessed_tables'),
                   model_uri=DATASET.datasetBundle__preprocessed_tables, domain=None, range=Optional[Union[Union[dict, PreprocessedRecording], list[Union[dict, PreprocessedRecording]]]])

slots.datasetBundle__computations = Slot(uri=DATASET.computations, name="datasetBundle__computations", curie=DATASET.curie('computations'),
                   model_uri=DATASET.datasetBundle__computations, domain=None, range=Optional[Union[dict[Union[str, DerivedDatasetKey], Union[dict, DerivedDataset]], list[Union[dict, DerivedDataset]]]])

slots.datasetBundle__steps = Slot(uri=DATASET.steps, name="datasetBundle__steps", curie=DATASET.curie('steps'),
                   model_uri=DATASET.datasetBundle__steps, domain=None, range=Optional[Union[dict[Union[str, ComputationStepNode], Union[dict, ComputationStep]], list[Union[dict, ComputationStep]]]])

