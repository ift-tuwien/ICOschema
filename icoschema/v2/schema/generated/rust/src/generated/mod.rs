#![allow(non_camel_case_types)]

#[cfg(feature = "serde")]
mod serde_utils;
pub mod poly;
pub mod poly_containers;
#[cfg(feature = "stubgen")]
pub mod stub_utils;

#[cfg(feature = "serde")]
use serde_yml as _ ;
#[cfg(feature = "pyo3")]
use pyo3::{FromPyObject,prelude::*};
#[cfg(feature = "stubgen")]
use pyo3_stub_gen::{define_stub_info_gatherer,derive::gen_stub_pyclass,derive::gen_stub_pymethods};
#[cfg(feature = "serde")]
use serde::{Deserialize,Serialize,de::IntoDeserializer};
use serde_value::Value;
#[cfg(feature = "serde")]
use serde_path_to_error;
use std::collections::HashMap;
use std::collections::BTreeMap;

// Types

pub type string = String;
pub type integer = String;
pub type boolean = String;
pub type float = f64;
pub type double = f64;
pub type decimal = String;
pub type time = String;
pub type date = String;
pub type datetime = String;
pub type date_or_datetime = String;
pub type uriorcurie = String;
pub type curie = String;
pub type uri = String;
pub type ncname = String;
pub type objectidentifier = String;
pub type nodeidentifier = String;
pub type jsonpointer = String;
pub type jsonpath = String;
pub type sparqlpath = String;

// Slots

pub type start_time = String;
pub type pre_metadata = String;
pub type post_metadata = String;
pub type revision = String;
pub type adc_reference_voltage = String;
pub type adc_prescaler = isize;
pub type adc_acquisition_time = isize;
pub type adc_oversample_rate = isize;
pub type channel1_metadata = ChannelMetadata;
pub type channel2_metadata = ChannelMetadata;
pub type channel3_metadata = ChannelMetadata;
pub type sensor = Sensor;
pub type conversion = Conversion;
pub type sensor_id = String;
pub type sensor_type = String;
pub type name = String;
pub type unit = String;
pub type dimension = String;
pub type conversion_type = String;
pub type gain = f64;
pub type offset = f64;
pub type timestamp = String;
pub type counter = Vec<isize>;
pub type channel1 = String;
pub type channel2 = String;
pub type channel3 = String;
pub type description = String;
pub type stu_mac = String;
pub type sth_mac = String;
pub type sampling_frequency = String;
pub type quality = QualityChannel;
pub type additional_data = String;
pub type hardware_metadata = HardwareMetadata;
pub type recording_metadata = RecordingMetadata;
pub type recording_data = RecordingData;
pub type values = String;
pub type sources = Vec<Source>;
pub type channel_sampling_frequency = f64;
pub type sampling_frequency_source = SamplingFrequencySource;
pub type fill_method = String;
pub type producer = String;
pub type source = String;
pub type key = String;
pub type shape = Vec<isize>;
pub type dtype = String;
pub type produced_by = String;
pub type produced_at = String;
pub type params = String;
pub type node = String;
pub type step_index = isize;
pub type resolved_params = String;
pub type inputs = Vec<String>;
pub type status = ComputationStatus;
pub type error = String;
pub type summary = String;
pub type output_keys = Vec<String>;
pub type started_at = String;
pub type duration_s = f64;
pub type environment = String;
pub type source_node = String;
pub type source_format = String;
pub type source_format_version = String;
pub type reader = String;
pub type writer = String;
pub type recording = Recording;
pub type provenance = Provenance;
pub type preprocessed_tables = Vec<PreprocessedRecording>;
pub type computations = Vec<DerivedDataset>;
pub type steps = Vec<ComputationStep>;

// Enums

#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub enum ComputationStatus {
#[cfg_attr(feature = "serde", serde(rename = "ok"))]
    Ok,
#[cfg_attr(feature = "serde", serde(rename = "error"))]
    Error,
}

impl core::fmt::Display for ComputationStatus {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            ComputationStatus::Ok => f.write_str("ok"),
            ComputationStatus::Error => f.write_str("error"),
        }
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for ComputationStatus {
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        let s: &str = match self {
            ComputationStatus::Ok => "ok",
            ComputationStatus::Error => "error",
        };
        Ok(pyo3::types::PyString::new(py, s).into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for ComputationStatus {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(s) = ob.extract::<&str>() {
            match s {
                "ok" | "Ok" => Ok(ComputationStatus::Ok),
                "error" | "Error" => Ok(ComputationStatus::Error),
                _ => Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("invalid value for ComputationStatus: {}", s),
                )),
            }
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
                concat!("expected str for ", stringify!(ComputationStatus)),
            ))
        }
    }
}

#[cfg(feature = "stubgen")]
impl ::pyo3_stub_gen::PyStubType for ComputationStatus {
    fn type_output() -> ::pyo3_stub_gen::TypeInfo {
        ::pyo3_stub_gen::TypeInfo::with_module(
            "typing.Literal['ok', 'error']",
            "typing".into(),
        )
    }
}
#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
pub enum SamplingFrequencySource {
#[cfg_attr(feature = "serde", serde(rename = "override"))]
    Override,
#[cfg_attr(feature = "serde", serde(rename = "hardware"))]
    Hardware,
#[cfg_attr(feature = "serde", serde(rename = "default"))]
    Default,
}

impl core::fmt::Display for SamplingFrequencySource {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        match self {
            SamplingFrequencySource::Override => f.write_str("override"),
            SamplingFrequencySource::Hardware => f.write_str("hardware"),
            SamplingFrequencySource::Default => f.write_str("default"),
        }
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for SamplingFrequencySource {
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        let s: &str = match self {
            SamplingFrequencySource::Override => "override",
            SamplingFrequencySource::Hardware => "hardware",
            SamplingFrequencySource::Default => "default",
        };
        Ok(pyo3::types::PyString::new(py, s).into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for SamplingFrequencySource {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(s) = ob.extract::<&str>() {
            match s {
                "override" | "Override" => Ok(SamplingFrequencySource::Override),
                "hardware" | "Hardware" => Ok(SamplingFrequencySource::Hardware),
                "default" | "Default" => Ok(SamplingFrequencySource::Default),
                _ => Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                    format!("invalid value for SamplingFrequencySource: {}", s),
                )),
            }
        } else {
            Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
                concat!("expected str for ", stringify!(SamplingFrequencySource)),
            ))
        }
    }
}

#[cfg(feature = "stubgen")]
impl ::pyo3_stub_gen::PyStubType for SamplingFrequencySource {
    fn type_output() -> ::pyo3_stub_gen::TypeInfo {
        ::pyo3_stub_gen::TypeInfo::with_module(
            "typing.Literal['override', 'hardware', 'default']",
            "typing".into(),
        )
    }
}

// Classes

#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct RecordingMetadata {
    #[cfg_attr(feature = "serde", serde(default))]
    pub start_time: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub pre_metadata: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub post_metadata: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl RecordingMetadata {
    #[new]
    #[pyo3(signature = (start_time=None, pre_metadata=None, post_metadata=None))]
    pub fn new(start_time: Option<String>, pre_metadata: Option<String>, post_metadata: Option<String>) -> Self {
        RecordingMetadata{start_time, pre_metadata, post_metadata}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<RecordingMetadata>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<RecordingMetadata> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<RecordingMetadata>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid RecordingMetadata",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct HardwareMetadata {
    #[cfg_attr(feature = "serde", serde(default))]
    pub revision: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub adc_reference_voltage: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub adc_prescaler: Option<isize>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub adc_acquisition_time: Option<isize>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub adc_oversample_rate: Option<isize>,
    pub channel1_metadata: ChannelMetadata,
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel2_metadata: Option<ChannelMetadata>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel3_metadata: Option<ChannelMetadata>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl HardwareMetadata {
    #[new]
    #[pyo3(signature = (channel1_metadata, revision=None, adc_reference_voltage=None, adc_prescaler=None, adc_acquisition_time=None, adc_oversample_rate=None, channel2_metadata=None, channel3_metadata=None))]
    pub fn new(channel1_metadata: serde_utils::PyValue<ChannelMetadata>, revision: Option<String>, adc_reference_voltage: Option<String>, adc_prescaler: Option<isize>, adc_acquisition_time: Option<isize>, adc_oversample_rate: Option<isize>, channel2_metadata: Option<serde_utils::PyValue<ChannelMetadata>>, channel3_metadata: Option<serde_utils::PyValue<ChannelMetadata>>) -> Self {
        let channel1_metadata = channel1_metadata.into_inner();
        let channel2_metadata = channel2_metadata.map(|v| v.into_inner());
        let channel3_metadata = channel3_metadata.map(|v| v.into_inner());
        HardwareMetadata{channel1_metadata, revision, adc_reference_voltage, adc_prescaler, adc_acquisition_time, adc_oversample_rate, channel2_metadata, channel3_metadata}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<HardwareMetadata>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<HardwareMetadata> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<HardwareMetadata>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid HardwareMetadata",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct ChannelMetadata {
    pub sensor: Sensor,
    pub conversion: ConversionOrSubtype
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl ChannelMetadata {
    #[new]
    #[pyo3(signature = (sensor, conversion))]
    pub fn new(sensor: serde_utils::PyValue<Sensor>, conversion: serde_utils::PyValue<ConversionOrSubtype>) -> Self {
        let sensor = sensor.into_inner();
        let conversion = conversion.into_inner();
        ChannelMetadata{sensor, conversion}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<ChannelMetadata>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<ChannelMetadata> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<ChannelMetadata>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid ChannelMetadata",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct Sensor {
    #[cfg_attr(feature = "serde", serde(default))]
    pub sensor_id: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub sensor_type: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub name: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub unit: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub dimension: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl Sensor {
    #[new]
    #[pyo3(signature = (sensor_id=None, sensor_type=None, name=None, unit=None, dimension=None))]
    pub fn new(sensor_id: Option<String>, sensor_type: Option<String>, name: Option<String>, unit: Option<String>, dimension: Option<String>) -> Self {
        Sensor{sensor_id, sensor_type, name, unit, dimension}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<Sensor>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<Sensor> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<Sensor>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid Sensor",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct Conversion {
    #[cfg_attr(feature = "serde", serde(default))]
    pub conversion_type: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl Conversion {
    #[new]
    #[pyo3(signature = (conversion_type=None))]
    pub fn new(conversion_type: Option<String>) -> Self {
        Conversion{conversion_type}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<Conversion>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<Conversion> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<Conversion>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid Conversion",
        ))
    }
}


#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature="serde", serde(untagged))]
pub enum ConversionOrSubtype {    NoConversion(NoConversion),     LinearConversion(LinearConversion)}

impl From<NoConversion>   for ConversionOrSubtype { fn from(x: NoConversion)   -> Self { Self::NoConversion(x) } }
impl From<LinearConversion>   for ConversionOrSubtype { fn from(x: LinearConversion)   -> Self { Self::LinearConversion(x) } }

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for ConversionOrSubtype {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<NoConversion>() {
            return Ok(ConversionOrSubtype::NoConversion(val));
        }        if let Ok(val) = ob.extract::<LinearConversion>() {
            return Ok(ConversionOrSubtype::LinearConversion(val));
        }Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid ConversionOrSubtype",
        ))
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for ConversionOrSubtype {
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;

    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        match self {
            ConversionOrSubtype::NoConversion(val) => val.into_pyobject(py).map(move |b| b.into_any()),
            ConversionOrSubtype::LinearConversion(val) => val.into_pyobject(py).map(move |b| b.into_any()),
        }
    }
}


#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<ConversionOrSubtype>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<ConversionOrSubtype> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<ConversionOrSubtype>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid ConversionOrSubtype",
        ))
    }
}


#[cfg(feature = "stubgen")]
::pyo3_stub_gen::impl_stub_type!(ConversionOrSubtype = NoConversion | LinearConversion);

#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct NoConversion {
    #[cfg_attr(feature = "serde", serde(default))]
    pub conversion_type: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl NoConversion {
    #[new]
    #[pyo3(signature = (conversion_type=None))]
    pub fn new(conversion_type: Option<String>) -> Self {
        NoConversion{conversion_type}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<NoConversion>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<NoConversion> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<NoConversion>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid NoConversion",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct LinearConversion {
    pub gain: f64,
    pub offset: f64,
    #[cfg_attr(feature = "serde", serde(default))]
    pub conversion_type: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl LinearConversion {
    #[new]
    #[pyo3(signature = (gain, offset, conversion_type=None))]
    pub fn new(gain: f64, offset: f64, conversion_type: Option<String>) -> Self {
        LinearConversion{gain, offset, conversion_type}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<LinearConversion>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<LinearConversion> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<LinearConversion>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid LinearConversion",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct RecordingData {
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub timestamp: Vec<isize>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value_optional",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub counter: Option<Vec<isize>>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel1: Vec<f64>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value_optional",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel2: Option<Vec<f64>>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value_optional",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel3: Option<Vec<f64>>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl RecordingData {
    #[new]
    #[pyo3(signature = (timestamp, channel1, counter=None, channel2=None, channel3=None))]
    pub fn new(timestamp: Vec<isize>, channel1: Vec<f64>, counter: Option<Vec<isize>>, channel2: Option<Vec<f64>>, channel3: Option<Vec<f64>>) -> Self {
        RecordingData{timestamp, channel1, counter, channel2, channel3}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<RecordingData>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<RecordingData> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<RecordingData>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid RecordingData",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct Source {
    pub name: String,
    #[cfg_attr(feature = "serde", serde(default))]
    pub description: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub stu_mac: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub sth_mac: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub sampling_frequency: Option<f64>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub quality: Option<QualityChannel>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub additional_data: Option<String>,
    pub hardware_metadata: HardwareMetadata,
    pub recording_metadata: RecordingMetadata,
    pub recording_data: RecordingData
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl Source {
    #[new]
    #[pyo3(signature = (name, hardware_metadata, recording_metadata, recording_data, description=None, stu_mac=None, sth_mac=None, sampling_frequency=None, quality=None, additional_data=None))]
    pub fn new(name: String, hardware_metadata: serde_utils::PyValue<HardwareMetadata>, recording_metadata: serde_utils::PyValue<RecordingMetadata>, recording_data: serde_utils::PyValue<RecordingData>, description: Option<String>, stu_mac: Option<String>, sth_mac: Option<String>, sampling_frequency: Option<f64>, quality: Option<serde_utils::PyValue<QualityChannel>>, additional_data: Option<String>) -> Self {
        let hardware_metadata = hardware_metadata.into_inner();
        let recording_metadata = recording_metadata.into_inner();
        let recording_data = recording_data.into_inner();
        let quality = quality.map(|v| v.into_inner());
        Source{name, hardware_metadata, recording_metadata, recording_data, description, stu_mac, sth_mac, sampling_frequency, quality, additional_data}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<Source>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<Source> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<Source>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid Source",
        ))
    }
}


#[cfg(feature = "serde")]
impl serde_utils::InlinedPair for Source {
    type Key   = String;
    type Value = Value;
    type Error = String;

    fn extract_key(&self) -> &Self::Key {
        return &self.name;
    }

    fn from_pair_mapping(k: Self::Key, v: Value) -> Result<Self,Self::Error> {
        let mut map = match v {
            Value::Map(m) => m,
            _ => return Err("ClassDefinition must be a mapping".into()),
        };
        let key_value = serde_value::to_value(k.clone())
            .map_err(|e| format!("unable to serialize key: {}", e))?;
        map.insert(Value::String("name".into()), key_value);
        let de          = Value::Map(map).into_deserializer();
        match serde_path_to_error::deserialize(de) {
            Ok(ok)  => Ok(ok),
            Err(e)  => Err(format!("at `{}`: {}", e.path(), e.inner())),
        }
    }


    fn from_pair_simple(_k: Self::Key, _v: Value) -> Result<Self,Self::Error> {
        Err("Cannot create a Source from a primitive value!".into())
    }


    fn compact_value(&self) -> Option<Value> {
        let value = match serde_value::to_value(self) {
            Ok(v) => v,
            Err(_) => return None,
        };
        match value {
            Value::Map(mut map) => {
                map.remove(&Value::String("name".into()));
                Some(Value::Map(map))
            }
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct QualityChannel {
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub values: Vec<f64>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub sampling_frequency: Option<f64>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl QualityChannel {
    #[new]
    #[pyo3(signature = (values, sampling_frequency=None))]
    pub fn new(values: Vec<f64>, sampling_frequency: Option<f64>) -> Self {
        QualityChannel{values, sampling_frequency}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<QualityChannel>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<QualityChannel> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<QualityChannel>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid QualityChannel",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct Recording {
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_inlined_dict_map",
        serialize_with = "serde_utils::serialize_inlined_dict_map"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub sources: HashMap<String, Source>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl Recording {
    #[new]
    #[pyo3(signature = (sources))]
    pub fn new(sources: serde_utils::PyValue<HashMap<String, Source>>) -> Self {
        let sources = sources.into_inner();
        Recording{sources}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<Recording>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<Recording> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<Recording>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid Recording",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct PreprocessedRecording {
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub timestamp: Vec<isize>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel1: Vec<f64>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value_optional",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel2: Option<Vec<f64>>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value_optional",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub channel3: Option<Vec<f64>>,
    pub channel_sampling_frequency: f64,
    pub sampling_frequency_source: SamplingFrequencySource,
    pub fill_method: String,
    pub producer: String,
    #[cfg_attr(feature = "serde", serde(default))]
    pub source: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl PreprocessedRecording {
    #[new]
    #[pyo3(signature = (timestamp, channel1, channel_sampling_frequency, sampling_frequency_source, fill_method, producer, channel2=None, channel3=None, source=None))]
    pub fn new(timestamp: Vec<isize>, channel1: Vec<f64>, channel_sampling_frequency: f64, sampling_frequency_source: SamplingFrequencySource, fill_method: String, producer: String, channel2: Option<Vec<f64>>, channel3: Option<Vec<f64>>, source: Option<String>) -> Self {
        PreprocessedRecording{timestamp, channel1, channel_sampling_frequency, sampling_frequency_source, fill_method, producer, channel2, channel3, source}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<PreprocessedRecording>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<PreprocessedRecording> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<PreprocessedRecording>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid PreprocessedRecording",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct DerivedDataset {
    pub key: String,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub values: Vec<f64>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub shape: Vec<isize>,
    pub dtype: String,
    #[cfg_attr(feature = "serde", serde(default))]
    pub unit: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub produced_by: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub produced_at: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub params: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub description: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl DerivedDataset {
    #[new]
    #[pyo3(signature = (key, values, shape, dtype, unit=None, produced_by=None, produced_at=None, params=None, description=None))]
    pub fn new(key: String, values: Vec<f64>, shape: Vec<isize>, dtype: String, unit: Option<String>, produced_by: Option<String>, produced_at: Option<String>, params: Option<String>, description: Option<String>) -> Self {
        DerivedDataset{key, values, shape, dtype, unit, produced_by, produced_at, params, description}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<DerivedDataset>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<DerivedDataset> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<DerivedDataset>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid DerivedDataset",
        ))
    }
}


#[cfg(feature = "serde")]
impl serde_utils::InlinedPair for DerivedDataset {
    type Key   = String;
    type Value = Value;
    type Error = String;

    fn extract_key(&self) -> &Self::Key {
        return &self.key;
    }

    fn from_pair_mapping(k: Self::Key, v: Value) -> Result<Self,Self::Error> {
        let mut map = match v {
            Value::Map(m) => m,
            _ => return Err("ClassDefinition must be a mapping".into()),
        };
        let key_value = serde_value::to_value(k.clone())
            .map_err(|e| format!("unable to serialize key: {}", e))?;
        map.insert(Value::String("key".into()), key_value);
        let de          = Value::Map(map).into_deserializer();
        match serde_path_to_error::deserialize(de) {
            Ok(ok)  => Ok(ok),
            Err(e)  => Err(format!("at `{}`: {}", e.path(), e.inner())),
        }
    }


    fn from_pair_simple(_k: Self::Key, _v: Value) -> Result<Self,Self::Error> {
        Err("Cannot create a DerivedDataset from a primitive value!".into())
    }


    fn compact_value(&self) -> Option<Value> {
        let value = match serde_value::to_value(self) {
            Ok(v) => v,
            Err(_) => return None,
        };
        match value {
            Value::Map(mut map) => {
                map.remove(&Value::String("key".into()));
                Some(Value::Map(map))
            }
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct ComputationStep {
    pub node: String,
    pub step_index: isize,
    pub producer: String,
    #[cfg_attr(feature = "serde", serde(default))]
    pub params: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub resolved_params: Option<String>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value_optional",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub inputs: Option<Vec<String>>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub status: Option<ComputationStatus>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub error: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub summary: Option<String>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_primitive_list_or_single_value_optional",
        serialize_with = "serde_utils::serialize_primitive_list_or_single_value_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub output_keys: Option<Vec<String>>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub started_at: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub duration_s: Option<f64>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub environment: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub source_node: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl ComputationStep {
    #[new]
    #[pyo3(signature = (node, step_index, producer, params=None, resolved_params=None, inputs=None, status=None, error=None, summary=None, output_keys=None, started_at=None, duration_s=None, environment=None, source_node=None))]
    pub fn new(node: String, step_index: isize, producer: String, params: Option<String>, resolved_params: Option<String>, inputs: Option<Vec<String>>, status: Option<ComputationStatus>, error: Option<String>, summary: Option<String>, output_keys: Option<Vec<String>>, started_at: Option<String>, duration_s: Option<f64>, environment: Option<String>, source_node: Option<String>) -> Self {
        ComputationStep{node, step_index, producer, params, resolved_params, inputs, status, error, summary, output_keys, started_at, duration_s, environment, source_node}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<ComputationStep>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<ComputationStep> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<ComputationStep>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid ComputationStep",
        ))
    }
}


#[cfg(feature = "serde")]
impl serde_utils::InlinedPair for ComputationStep {
    type Key   = String;
    type Value = Value;
    type Error = String;

    fn extract_key(&self) -> &Self::Key {
        return &self.node;
    }

    fn from_pair_mapping(k: Self::Key, v: Value) -> Result<Self,Self::Error> {
        let mut map = match v {
            Value::Map(m) => m,
            _ => return Err("ClassDefinition must be a mapping".into()),
        };
        let key_value = serde_value::to_value(k.clone())
            .map_err(|e| format!("unable to serialize key: {}", e))?;
        map.insert(Value::String("node".into()), key_value);
        let de          = Value::Map(map).into_deserializer();
        match serde_path_to_error::deserialize(de) {
            Ok(ok)  => Ok(ok),
            Err(e)  => Err(format!("at `{}`: {}", e.path(), e.inner())),
        }
    }


    fn from_pair_simple(_k: Self::Key, _v: Value) -> Result<Self,Self::Error> {
        Err("Cannot create a ComputationStep from a primitive value!".into())
    }


    fn compact_value(&self) -> Option<Value> {
        let value = match serde_value::to_value(self) {
            Ok(v) => v,
            Err(_) => return None,
        };
        match value {
            Value::Map(mut map) => {
                map.remove(&Value::String("node".into()));
                Some(Value::Map(map))
            }
            _ => None,
        }
    }
}

#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct Provenance {
    #[cfg_attr(feature = "serde", serde(default))]
    pub source_format: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub source_format_version: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub reader: Option<String>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub writer: Option<String>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl Provenance {
    #[new]
    #[pyo3(signature = (source_format=None, source_format_version=None, reader=None, writer=None))]
    pub fn new(source_format: Option<String>, source_format_version: Option<String>, reader: Option<String>, writer: Option<String>) -> Self {
        Provenance{source_format, source_format_version, reader, writer}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<Provenance>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<Provenance> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<Provenance>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid Provenance",
        ))
    }
}



#[derive(Debug, Clone, PartialEq)]
#[cfg_attr(feature = "serde", derive(Serialize, Deserialize))]
#[cfg_attr(feature = "stubgen", gen_stub_pyclass)]
#[cfg_attr(feature = "pyo3", pyclass(subclass, get_all, set_all))]
pub struct DatasetBundle {
    pub recording: Recording,
    #[cfg_attr(feature = "serde", serde(default))]
    pub provenance: Option<Provenance>,
    #[cfg_attr(feature = "serde", serde(default))]
    pub preprocessed_tables: Option<Vec<PreprocessedRecording>>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_inlined_dict_map_optional",
        serialize_with = "serde_utils::serialize_inlined_dict_map_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub computations: Option<HashMap<String, DerivedDataset>>,
    #[cfg_attr(feature = "serde", serde(
        deserialize_with = "serde_utils::deserialize_inlined_dict_list_optional",
        serialize_with = "serde_utils::serialize_inlined_dict_list_optional"
    ))]
    #[cfg_attr(feature = "serde", serde(default))]
    pub steps: Option<Vec<ComputationStep>>
}
#[cfg(feature = "pyo3")]
#[cfg_attr(feature = "stubgen", gen_stub_pymethods)]
#[pymethods]
impl DatasetBundle {
    #[new]
    #[pyo3(signature = (recording, provenance=None, preprocessed_tables=None, computations=None, steps=None))]
    pub fn new(recording: serde_utils::PyValue<Recording>, provenance: Option<serde_utils::PyValue<Provenance>>, preprocessed_tables: Option<serde_utils::PyValue<Vec<PreprocessedRecording>>>, computations: Option<serde_utils::PyValue<HashMap<String, DerivedDataset>>>, steps: Option<serde_utils::PyValue<Vec<ComputationStep>>>) -> Self {
        let recording = recording.into_inner();
        let provenance = provenance.map(|v| v.into_inner());
        let preprocessed_tables = preprocessed_tables.map(|v| v.into_inner());
        let computations = computations.map(|v| v.into_inner());
        let steps = steps.map(|v| v.into_inner());
        DatasetBundle{recording, provenance, preprocessed_tables, computations, steps}
    }
}

#[cfg(feature = "pyo3")]
impl<'py> IntoPyObject<'py> for Box<DatasetBundle>
{
    type Target = PyAny;
    type Output = Bound<'py, Self::Target>;
    type Error = PyErr;
    fn into_pyobject(self, py: Python<'py>) -> Result<Self::Output, Self::Error> {
        (*self).into_pyobject(py).map(move |x| x.into_any())
    }
}

#[cfg(feature = "pyo3")]
impl<'py> FromPyObject<'py> for Box<DatasetBundle> {
    fn extract_bound(ob: &pyo3::Bound<'py, pyo3::types::PyAny>) -> pyo3::PyResult<Self> {
        if let Ok(val) = ob.extract::<DatasetBundle>() {
            return Ok(Box::new(val));
        }
        Err(PyErr::new::<pyo3::exceptions::PyTypeError, _>(
            "invalid DatasetBundle",
        ))
    }
}






#[cfg(feature = "stubgen")]
define_stub_info_gatherer!(stub_info);
