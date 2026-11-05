use icoschema::DatasetBundle;
use std::time::Instant;

fn main() -> icoschema::Result<()> {
    let path = std::env::args().nth(1).unwrap();
    let t = Instant::now();
    let b = DatasetBundle::from_hdf5(&path)?;
    println!("loaded in {:?}", t.elapsed());
    let r = &b.recording;
    println!("rows {} loss% {:.9} rows/packet {}", r.timestamps().len(), r.signal_loss_percentage(), r.rows_per_packet()?);
    let idx = r.sample_index()?;
    let mask = r.filled_mask()?;
    println!("sample_index last {} mask len {} filled {}", idx.last().unwrap(), mask.len(), mask.iter().filter(|m| **m).count());
    println!("fs {:?} ch {}", r.channel_sampling_frequency()?, r.channel_count());
    let s = r.summary();
    println!("start {:?} n {}", s.start_time, s.sample_count);
    for (n, c) in &s.channels {
        println!("{n}: {:?} {:?} {:?} n={} min={:.6} max={:.6} mean={:.9} std={:.9}", c.sensor_id, c.sensor_type, c.unit, c.sample_count, c.min, c.max, c.mean, c.std);
    }
    println!("hw adc {:?} {:?} {:?} ref {:?}", r.hardware_metadata.adc_prescaler, r.hardware_metadata.adc_acquisition_time, r.hardware_metadata.adc_oversample_rate, r.hardware_metadata.adc_reference_voltage);
    let mut keys: Vec<_> = b.computations.keys().collect();
    keys.sort();
    for k in keys { let d = &b.computations[k]; println!("comp {k}: shape {:?} dtype {} n={}", d.shape, d.dtype, d.values.len()); }
    println!("steps {}", b.steps.len());
    for s in &b.steps { println!("step {} idx {} producer {} status {:?} inputs {:?} out {:?}", s.node, s.step_index, s.producer, s.status, s.inputs, s.output_keys); }
    println!("preprocessed {}", b.preprocessed.is_some());
    Ok(())
}
