#![allow(non_camel_case_types)]

use crate::*;
use crate::poly_containers::*;


pub trait RecordingMetadata   {

    fn start_time<'a>(&'a self) -> Option<&'a str>;
    // fn start_time_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_start_time(&mut self, value: Option<&'a str>);

    fn pre_metadata<'a>(&'a self) -> Option<&'a str>;
    // fn pre_metadata_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_pre_metadata(&mut self, value: Option<&'a str>);

    fn post_metadata<'a>(&'a self) -> Option<&'a str>;
    // fn post_metadata_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_post_metadata(&mut self, value: Option<&'a str>);


}

impl RecordingMetadata for crate::RecordingMetadata {
        fn start_time<'a>(&'a self) -> Option<&'a str> {
        return self.start_time.as_deref();
    }
        fn pre_metadata<'a>(&'a self) -> Option<&'a str> {
        return self.pre_metadata.as_deref();
    }
        fn post_metadata<'a>(&'a self) -> Option<&'a str> {
        return self.post_metadata.as_deref();
    }
}


pub trait HardwareMetadata   {

    fn revision<'a>(&'a self) -> Option<&'a str>;
    // fn revision_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_revision(&mut self, value: Option<&'a str>);

    fn adc_reference_voltage<'a>(&'a self) -> Option<&'a str>;
    // fn adc_reference_voltage_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_adc_reference_voltage(&mut self, value: Option<&'a str>);

    fn adc_prescaler(&self) -> Option<isize>;
    // fn adc_prescaler_mut(&mut self) -> &mut Option<isize>;
    // fn set_adc_prescaler(&mut self, value: Option<isize>);

    fn adc_acquisition_time(&self) -> Option<isize>;
    // fn adc_acquisition_time_mut(&mut self) -> &mut Option<isize>;
    // fn set_adc_acquisition_time(&mut self, value: Option<isize>);

    fn adc_oversample_rate(&self) -> Option<isize>;
    // fn adc_oversample_rate_mut(&mut self) -> &mut Option<isize>;
    // fn set_adc_oversample_rate(&mut self, value: Option<isize>);

    fn channel1_metadata<'a>(&'a self) -> &'a crate::ChannelMetadata;
    // fn channel1_metadata_mut(&mut self) -> &mut &'a crate::ChannelMetadata;
    // fn set_channel1_metadata<E>(&mut self, value: E) where E: Into<ChannelMetadata>;

    fn channel2_metadata<'a>(&'a self) -> Option<&'a crate::ChannelMetadata>;
    // fn channel2_metadata_mut(&mut self) -> &mut Option<&'a crate::ChannelMetadata>;
    // fn set_channel2_metadata<E>(&mut self, value: Option<E>) where E: Into<ChannelMetadata>;

    fn channel3_metadata<'a>(&'a self) -> Option<&'a crate::ChannelMetadata>;
    // fn channel3_metadata_mut(&mut self) -> &mut Option<&'a crate::ChannelMetadata>;
    // fn set_channel3_metadata<E>(&mut self, value: Option<E>) where E: Into<ChannelMetadata>;


}

impl HardwareMetadata for crate::HardwareMetadata {
        fn revision<'a>(&'a self) -> Option<&'a str> {
        return self.revision.as_deref();
    }
        fn adc_reference_voltage<'a>(&'a self) -> Option<&'a str> {
        return self.adc_reference_voltage.as_deref();
    }
        fn adc_prescaler(&self) -> Option<isize> {
        return self.adc_prescaler;
    }
        fn adc_acquisition_time(&self) -> Option<isize> {
        return self.adc_acquisition_time;
    }
        fn adc_oversample_rate(&self) -> Option<isize> {
        return self.adc_oversample_rate;
    }
        fn channel1_metadata<'a>(&'a self) -> &'a crate::ChannelMetadata {
        return &self.channel1_metadata;
    }
        fn channel2_metadata<'a>(&'a self) -> Option<&'a crate::ChannelMetadata> {
        return self.channel2_metadata.as_ref();
    }
        fn channel3_metadata<'a>(&'a self) -> Option<&'a crate::ChannelMetadata> {
        return self.channel3_metadata.as_ref();
    }
}


pub trait ChannelMetadata   {

    fn sensor<'a>(&'a self) -> &'a crate::Sensor;
    // fn sensor_mut(&mut self) -> &mut &'a crate::Sensor;
    // fn set_sensor<E>(&mut self, value: E) where E: Into<Sensor>;

    fn conversion<'a>(&'a self) -> &'a ConversionOrSubtype;
    // fn conversion_mut(&mut self) -> &mut &'a ConversionOrSubtype;
    // fn set_conversion<E>(&mut self, value: E) where E: Into<Conversion>;


}

impl ChannelMetadata for crate::ChannelMetadata {
        fn sensor<'a>(&'a self) -> &'a crate::Sensor {
        return &self.sensor;
    }
        fn conversion<'a>(&'a self) -> &'a ConversionOrSubtype {
        return &self.conversion;
    }
}


pub trait Sensor   {

    fn sensor_id<'a>(&'a self) -> Option<&'a str>;
    // fn sensor_id_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_sensor_id(&mut self, value: Option<&'a str>);

    fn sensor_type<'a>(&'a self) -> Option<&'a str>;
    // fn sensor_type_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_sensor_type(&mut self, value: Option<&'a str>);

    fn name<'a>(&'a self) -> Option<&'a str>;
    // fn name_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_name(&mut self, value: Option<&'a str>);

    fn unit<'a>(&'a self) -> Option<&'a str>;
    // fn unit_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_unit(&mut self, value: Option<&'a str>);

    fn dimension<'a>(&'a self) -> Option<&'a str>;
    // fn dimension_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_dimension(&mut self, value: Option<&'a str>);


}

impl Sensor for crate::Sensor {
        fn sensor_id<'a>(&'a self) -> Option<&'a str> {
        return self.sensor_id.as_deref();
    }
        fn sensor_type<'a>(&'a self) -> Option<&'a str> {
        return self.sensor_type.as_deref();
    }
        fn name<'a>(&'a self) -> Option<&'a str> {
        return self.name.as_deref();
    }
        fn unit<'a>(&'a self) -> Option<&'a str> {
        return self.unit.as_deref();
    }
        fn dimension<'a>(&'a self) -> Option<&'a str> {
        return self.dimension.as_deref();
    }
}


pub trait Conversion   {

    fn conversion_type<'a>(&'a self) -> Option<&'a str>;
    // fn conversion_type_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_conversion_type(&mut self, value: Option<&'a str>);


}

impl Conversion for crate::Conversion {
        fn conversion_type<'a>(&'a self) -> Option<&'a str> {
        return self.conversion_type.as_deref();
    }
}
impl Conversion for crate::NoConversion {
        fn conversion_type<'a>(&'a self) -> Option<&'a str> {
        return self.conversion_type.as_deref();
    }
}
impl Conversion for crate::LinearConversion {
        fn conversion_type<'a>(&'a self) -> Option<&'a str> {
        return self.conversion_type.as_deref();
    }
}

impl Conversion for crate::ConversionOrSubtype {
        fn conversion_type<'a>(&'a self) -> Option<&'a str> {
        match self {
                ConversionOrSubtype::NoConversion(val) => val.conversion_type(),
                ConversionOrSubtype::LinearConversion(val) => val.conversion_type(),

        }
    }
}

pub trait NoConversion : Conversion   {


}

impl NoConversion for crate::NoConversion {
}


pub trait LinearConversion : Conversion   {

    fn gain(&self) -> f64;
    // fn gain_mut(&mut self) -> &mut f64;
    // fn set_gain(&mut self, value: f64);

    fn offset(&self) -> f64;
    // fn offset_mut(&mut self) -> &mut f64;
    // fn set_offset(&mut self, value: f64);


}

impl LinearConversion for crate::LinearConversion {
        fn gain(&self) -> f64 {
        return self.gain;
    }
        fn offset(&self) -> f64 {
        return self.offset;
    }
}


pub trait RecordingData   {

    fn timestamp<'a>(&'a self) -> impl poly_containers::SeqRef<'a, isize>;
    // fn timestamp_mut(&mut self) -> &mut impl poly_containers::SeqRef<'a, isize>;
    // fn set_timestamp(&mut self, value: &Vec<isize>);

    fn counter<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, isize>>;
    // fn counter_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, isize>>;
    // fn set_counter(&mut self, value: Option<&Vec<isize>>);

    fn channel1<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64>;
    // fn channel1_mut(&mut self) -> &mut impl poly_containers::SeqRef<'a, f64>;
    // fn set_channel1(&mut self, value: &Vec<f64>);

    fn channel2<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn channel2_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn set_channel2(&mut self, value: Option<&Vec<f64>>);

    fn channel3<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn channel3_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn set_channel3(&mut self, value: Option<&Vec<f64>>);


}

impl RecordingData for crate::RecordingData {
        fn timestamp<'a>(&'a self) -> impl poly_containers::SeqRef<'a, isize> {
        return &self.timestamp;
    }
        fn counter<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, isize>> {
        return self.counter.as_ref();
    }
        fn channel1<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64> {
        return &self.channel1;
    }
        fn channel2<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>> {
        return self.channel2.as_ref();
    }
        fn channel3<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>> {
        return self.channel3.as_ref();
    }
}


pub trait Source   {

    fn name<'a>(&'a self) -> &'a str;
    // fn name_mut(&mut self) -> &mut &'a str;
    // fn set_name(&mut self, value: String);

    fn description<'a>(&'a self) -> Option<&'a str>;
    // fn description_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_description(&mut self, value: Option<&'a str>);

    fn stu_mac<'a>(&'a self) -> Option<&'a str>;
    // fn stu_mac_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_stu_mac(&mut self, value: Option<&'a str>);

    fn sth_mac<'a>(&'a self) -> Option<&'a str>;
    // fn sth_mac_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_sth_mac(&mut self, value: Option<&'a str>);

    fn sampling_frequency(&self) -> Option<f64>;
    // fn sampling_frequency_mut(&mut self) -> &mut Option<f64>;
    // fn set_sampling_frequency(&mut self, value: Option<f64>);

    fn quality<'a>(&'a self) -> Option<&'a crate::QualityChannel>;
    // fn quality_mut(&mut self) -> &mut Option<&'a crate::QualityChannel>;
    // fn set_quality<E>(&mut self, value: Option<E>) where E: Into<QualityChannel>;

    fn additional_data<'a>(&'a self) -> Option<&'a str>;
    // fn additional_data_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_additional_data(&mut self, value: Option<&'a str>);

    fn hardware_metadata<'a>(&'a self) -> &'a crate::HardwareMetadata;
    // fn hardware_metadata_mut(&mut self) -> &mut &'a crate::HardwareMetadata;
    // fn set_hardware_metadata<E>(&mut self, value: E) where E: Into<HardwareMetadata>;

    fn recording_metadata<'a>(&'a self) -> &'a crate::RecordingMetadata;
    // fn recording_metadata_mut(&mut self) -> &mut &'a crate::RecordingMetadata;
    // fn set_recording_metadata<E>(&mut self, value: E) where E: Into<RecordingMetadata>;

    fn recording_data<'a>(&'a self) -> &'a crate::RecordingData;
    // fn recording_data_mut(&mut self) -> &mut &'a crate::RecordingData;
    // fn set_recording_data<E>(&mut self, value: E) where E: Into<RecordingData>;


}

impl Source for crate::Source {
        fn name<'a>(&'a self) -> &'a str {
        return &self.name[..];
    }
        fn description<'a>(&'a self) -> Option<&'a str> {
        return self.description.as_deref();
    }
        fn stu_mac<'a>(&'a self) -> Option<&'a str> {
        return self.stu_mac.as_deref();
    }
        fn sth_mac<'a>(&'a self) -> Option<&'a str> {
        return self.sth_mac.as_deref();
    }
        fn sampling_frequency(&self) -> Option<f64> {
        return self.sampling_frequency;
    }
        fn quality<'a>(&'a self) -> Option<&'a crate::QualityChannel> {
        return self.quality.as_ref();
    }
        fn additional_data<'a>(&'a self) -> Option<&'a str> {
        return self.additional_data.as_deref();
    }
        fn hardware_metadata<'a>(&'a self) -> &'a crate::HardwareMetadata {
        return &self.hardware_metadata;
    }
        fn recording_metadata<'a>(&'a self) -> &'a crate::RecordingMetadata {
        return &self.recording_metadata;
    }
        fn recording_data<'a>(&'a self) -> &'a crate::RecordingData {
        return &self.recording_data;
    }
}


pub trait QualityChannel   {

    fn values<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64>;
    // fn values_mut(&mut self) -> &mut impl poly_containers::SeqRef<'a, f64>;
    // fn set_values(&mut self, value: &Vec<f64>);

    fn sampling_frequency(&self) -> Option<f64>;
    // fn sampling_frequency_mut(&mut self) -> &mut Option<f64>;
    // fn set_sampling_frequency(&mut self, value: Option<f64>);


}

impl QualityChannel for crate::QualityChannel {
        fn values<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64> {
        return &self.values;
    }
        fn sampling_frequency(&self) -> Option<f64> {
        return self.sampling_frequency;
    }
}


pub trait Recording   {

    fn sources<'a>(&'a self) -> impl poly_containers::MapRef<'a, String,crate::Source>;
    // fn sources_mut(&mut self) -> &mut impl poly_containers::MapRef<'a, String,crate::Source>;
    // fn set_sources<E>(&mut self, value: &HashMap<String, E>) where E: Into<Source>;


}

impl Recording for crate::Recording {
        fn sources<'a>(&'a self) -> impl poly_containers::MapRef<'a, String,crate::Source> {
        return &self.sources;
    }
}


pub trait PreprocessedRecording   {

    fn timestamp<'a>(&'a self) -> impl poly_containers::SeqRef<'a, isize>;
    // fn timestamp_mut(&mut self) -> &mut impl poly_containers::SeqRef<'a, isize>;
    // fn set_timestamp(&mut self, value: &Vec<isize>);

    fn channel1<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64>;
    // fn channel1_mut(&mut self) -> &mut impl poly_containers::SeqRef<'a, f64>;
    // fn set_channel1(&mut self, value: &Vec<f64>);

    fn channel2<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn channel2_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn set_channel2(&mut self, value: Option<&Vec<f64>>);

    fn channel3<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn channel3_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, f64>>;
    // fn set_channel3(&mut self, value: Option<&Vec<f64>>);

    fn channel_sampling_frequency(&self) -> f64;
    // fn channel_sampling_frequency_mut(&mut self) -> &mut f64;
    // fn set_channel_sampling_frequency(&mut self, value: f64);

    fn sampling_frequency_source<'a>(&'a self) -> &'a crate::SamplingFrequencySource;
    // fn sampling_frequency_source_mut(&mut self) -> &mut &'a crate::SamplingFrequencySource;
    // fn set_sampling_frequency_source(&mut self, value: SamplingFrequencySource);

    fn fill_method<'a>(&'a self) -> &'a str;
    // fn fill_method_mut(&mut self) -> &mut &'a str;
    // fn set_fill_method(&mut self, value: String);

    fn producer<'a>(&'a self) -> &'a str;
    // fn producer_mut(&mut self) -> &mut &'a str;
    // fn set_producer(&mut self, value: String);

    fn source<'a>(&'a self) -> Option<&'a str>;
    // fn source_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_source(&mut self, value: Option<&'a str>);


}

impl PreprocessedRecording for crate::PreprocessedRecording {
        fn timestamp<'a>(&'a self) -> impl poly_containers::SeqRef<'a, isize> {
        return &self.timestamp;
    }
        fn channel1<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64> {
        return &self.channel1;
    }
        fn channel2<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>> {
        return self.channel2.as_ref();
    }
        fn channel3<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, f64>> {
        return self.channel3.as_ref();
    }
        fn channel_sampling_frequency(&self) -> f64 {
        return self.channel_sampling_frequency;
    }
        fn sampling_frequency_source<'a>(&'a self) -> &'a crate::SamplingFrequencySource {
        return &self.sampling_frequency_source;
    }
        fn fill_method<'a>(&'a self) -> &'a str {
        return &self.fill_method[..];
    }
        fn producer<'a>(&'a self) -> &'a str {
        return &self.producer[..];
    }
        fn source<'a>(&'a self) -> Option<&'a str> {
        return self.source.as_deref();
    }
}


pub trait DerivedDataset   {

    fn key<'a>(&'a self) -> &'a str;
    // fn key_mut(&mut self) -> &mut &'a str;
    // fn set_key(&mut self, value: String);

    fn values<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64>;
    // fn values_mut(&mut self) -> &mut impl poly_containers::SeqRef<'a, f64>;
    // fn set_values(&mut self, value: &Vec<f64>);

    fn shape<'a>(&'a self) -> impl poly_containers::SeqRef<'a, isize>;
    // fn shape_mut(&mut self) -> &mut impl poly_containers::SeqRef<'a, isize>;
    // fn set_shape(&mut self, value: &Vec<isize>);

    fn dtype<'a>(&'a self) -> &'a str;
    // fn dtype_mut(&mut self) -> &mut &'a str;
    // fn set_dtype(&mut self, value: String);

    fn unit<'a>(&'a self) -> Option<&'a str>;
    // fn unit_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_unit(&mut self, value: Option<&'a str>);

    fn produced_by<'a>(&'a self) -> Option<&'a str>;
    // fn produced_by_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_produced_by(&mut self, value: Option<&'a str>);

    fn produced_at<'a>(&'a self) -> Option<&'a str>;
    // fn produced_at_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_produced_at(&mut self, value: Option<&'a str>);

    fn params<'a>(&'a self) -> Option<&'a str>;
    // fn params_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_params(&mut self, value: Option<&'a str>);

    fn description<'a>(&'a self) -> Option<&'a str>;
    // fn description_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_description(&mut self, value: Option<&'a str>);


}

impl DerivedDataset for crate::DerivedDataset {
        fn key<'a>(&'a self) -> &'a str {
        return &self.key[..];
    }
        fn values<'a>(&'a self) -> impl poly_containers::SeqRef<'a, f64> {
        return &self.values;
    }
        fn shape<'a>(&'a self) -> impl poly_containers::SeqRef<'a, isize> {
        return &self.shape;
    }
        fn dtype<'a>(&'a self) -> &'a str {
        return &self.dtype[..];
    }
        fn unit<'a>(&'a self) -> Option<&'a str> {
        return self.unit.as_deref();
    }
        fn produced_by<'a>(&'a self) -> Option<&'a str> {
        return self.produced_by.as_deref();
    }
        fn produced_at<'a>(&'a self) -> Option<&'a str> {
        return self.produced_at.as_deref();
    }
        fn params<'a>(&'a self) -> Option<&'a str> {
        return self.params.as_deref();
    }
        fn description<'a>(&'a self) -> Option<&'a str> {
        return self.description.as_deref();
    }
}


pub trait ComputationStep   {

    fn node<'a>(&'a self) -> &'a str;
    // fn node_mut(&mut self) -> &mut &'a str;
    // fn set_node(&mut self, value: String);

    fn step_index(&self) -> isize;
    // fn step_index_mut(&mut self) -> &mut isize;
    // fn set_step_index(&mut self, value: isize);

    fn producer<'a>(&'a self) -> &'a str;
    // fn producer_mut(&mut self) -> &mut &'a str;
    // fn set_producer(&mut self, value: String);

    fn params<'a>(&'a self) -> Option<&'a str>;
    // fn params_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_params(&mut self, value: Option<&'a str>);

    fn resolved_params<'a>(&'a self) -> Option<&'a str>;
    // fn resolved_params_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_resolved_params(&mut self, value: Option<&'a str>);

    fn inputs<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, String>>;
    // fn inputs_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, String>>;
    // fn set_inputs(&mut self, value: Option<&Vec<String>>);

    fn status<'a>(&'a self) -> Option<&'a crate::ComputationStatus>;
    // fn status_mut(&mut self) -> &mut Option<&'a crate::ComputationStatus>;
    // fn set_status(&mut self, value: Option<&'a ComputationStatus>);

    fn error<'a>(&'a self) -> Option<&'a str>;
    // fn error_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_error(&mut self, value: Option<&'a str>);

    fn summary<'a>(&'a self) -> Option<&'a str>;
    // fn summary_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_summary(&mut self, value: Option<&'a str>);

    fn output_keys<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, String>>;
    // fn output_keys_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, String>>;
    // fn set_output_keys(&mut self, value: Option<&Vec<String>>);

    fn started_at<'a>(&'a self) -> Option<&'a str>;
    // fn started_at_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_started_at(&mut self, value: Option<&'a str>);

    fn duration_s(&self) -> Option<f64>;
    // fn duration_s_mut(&mut self) -> &mut Option<f64>;
    // fn set_duration_s(&mut self, value: Option<f64>);

    fn environment<'a>(&'a self) -> Option<&'a str>;
    // fn environment_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_environment(&mut self, value: Option<&'a str>);

    fn source_node<'a>(&'a self) -> Option<&'a str>;
    // fn source_node_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_source_node(&mut self, value: Option<&'a str>);


}

impl ComputationStep for crate::ComputationStep {
        fn node<'a>(&'a self) -> &'a str {
        return &self.node[..];
    }
        fn step_index(&self) -> isize {
        return self.step_index;
    }
        fn producer<'a>(&'a self) -> &'a str {
        return &self.producer[..];
    }
        fn params<'a>(&'a self) -> Option<&'a str> {
        return self.params.as_deref();
    }
        fn resolved_params<'a>(&'a self) -> Option<&'a str> {
        return self.resolved_params.as_deref();
    }
        fn inputs<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, String>> {
        return self.inputs.as_ref();
    }
        fn status<'a>(&'a self) -> Option<&'a crate::ComputationStatus> {
        return self.status.as_ref();
    }
        fn error<'a>(&'a self) -> Option<&'a str> {
        return self.error.as_deref();
    }
        fn summary<'a>(&'a self) -> Option<&'a str> {
        return self.summary.as_deref();
    }
        fn output_keys<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, String>> {
        return self.output_keys.as_ref();
    }
        fn started_at<'a>(&'a self) -> Option<&'a str> {
        return self.started_at.as_deref();
    }
        fn duration_s(&self) -> Option<f64> {
        return self.duration_s;
    }
        fn environment<'a>(&'a self) -> Option<&'a str> {
        return self.environment.as_deref();
    }
        fn source_node<'a>(&'a self) -> Option<&'a str> {
        return self.source_node.as_deref();
    }
}


pub trait Provenance   {

    fn source_format<'a>(&'a self) -> Option<&'a str>;
    // fn source_format_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_source_format(&mut self, value: Option<&'a str>);

    fn source_format_version<'a>(&'a self) -> Option<&'a str>;
    // fn source_format_version_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_source_format_version(&mut self, value: Option<&'a str>);

    fn reader<'a>(&'a self) -> Option<&'a str>;
    // fn reader_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_reader(&mut self, value: Option<&'a str>);

    fn writer<'a>(&'a self) -> Option<&'a str>;
    // fn writer_mut(&mut self) -> &mut Option<&'a str>;
    // fn set_writer(&mut self, value: Option<&'a str>);


}

impl Provenance for crate::Provenance {
        fn source_format<'a>(&'a self) -> Option<&'a str> {
        return self.source_format.as_deref();
    }
        fn source_format_version<'a>(&'a self) -> Option<&'a str> {
        return self.source_format_version.as_deref();
    }
        fn reader<'a>(&'a self) -> Option<&'a str> {
        return self.reader.as_deref();
    }
        fn writer<'a>(&'a self) -> Option<&'a str> {
        return self.writer.as_deref();
    }
}


pub trait DatasetBundle   {

    fn recording<'a>(&'a self) -> &'a crate::Recording;
    // fn recording_mut(&mut self) -> &mut &'a crate::Recording;
    // fn set_recording<E>(&mut self, value: E) where E: Into<Recording>;

    fn provenance<'a>(&'a self) -> Option<&'a crate::Provenance>;
    // fn provenance_mut(&mut self) -> &mut Option<&'a crate::Provenance>;
    // fn set_provenance<E>(&mut self, value: Option<E>) where E: Into<Provenance>;

    fn preprocessed_tables<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, crate::PreprocessedRecording>>;
    // fn preprocessed_tables_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, crate::PreprocessedRecording>>;
    // fn set_preprocessed_tables<E>(&mut self, value: Option<&Vec<E>>) where E: Into<PreprocessedRecording>;

    fn computations<'a>(&'a self) -> Option<impl poly_containers::MapRef<'a, String,crate::DerivedDataset>>;
    // fn computations_mut(&mut self) -> &mut Option<impl poly_containers::MapRef<'a, String,crate::DerivedDataset>>;
    // fn set_computations<E>(&mut self, value: Option<&HashMap<String, E>>) where E: Into<DerivedDataset>;

    fn steps<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, crate::ComputationStep>>;
    // fn steps_mut(&mut self) -> &mut Option<impl poly_containers::SeqRef<'a, crate::ComputationStep>>;
    // fn set_steps<E>(&mut self, value: Option<&Vec<E>>) where E: Into<ComputationStep>;


}

impl DatasetBundle for crate::DatasetBundle {
        fn recording<'a>(&'a self) -> &'a crate::Recording {
        return &self.recording;
    }
        fn provenance<'a>(&'a self) -> Option<&'a crate::Provenance> {
        return self.provenance.as_ref();
    }
        fn preprocessed_tables<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, crate::PreprocessedRecording>> {
        return self.preprocessed_tables.as_ref();
    }
        fn computations<'a>(&'a self) -> Option<impl poly_containers::MapRef<'a, String,crate::DerivedDataset>> {
        return self.computations.as_ref();
    }
        fn steps<'a>(&'a self) -> Option<impl poly_containers::SeqRef<'a, crate::ComputationStep>> {
        return self.steps.as_ref();
    }
}
