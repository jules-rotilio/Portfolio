//! Things that run without a microphone: the speed benchmark and audio file processing.

use crate::live;
use crate::results::{self, Report};
use clap::Args;
use serde_json::json;
use std::f32::consts::PI;
use std::path::PathBuf;
use std::time::Instant;
use voice_changer::audio_file::read_audio;
use voice_changer::effect::{Effect, EffectArgs};

/// The options of the `bench` command. `#[derive(Args)]` lets clap fill this
/// struct straight from the command line; the `///` comments become `--help`.
#[derive(Args)]
pub struct BenchOptions {
    #[command(flatten)]
    effect: EffectArgs,
    /// Block size in samples (256 at 48 kHz = 5.3 ms)
    #[arg(long, default_value_t = 256, value_parser = clap::value_parser!(u32).range(1..=16_384))]
    block: u32,
    /// Seconds of audio to process
    #[arg(long, default_value_t = 60.0)]
    seconds: f32,
    /// Folder for the benchmark result files
    #[arg(long, default_value_os_t = results::default_dir())]
    out_dir: PathBuf,
}

/// The options of the `file` command.
#[derive(Args)]
pub struct FileOptions {
    /// The audio file to change
    input: PathBuf,
    /// Where to save the result, as a mono WAV file. Leave it out to listen instead
    output: Option<PathBuf>,
    #[command(flatten)]
    effect: EffectArgs,
}

/// Measures how fast the chosen effect is, using a made-up voice-like signal.
/// This gives repeatable numbers that don't depend on your sound card.
pub fn bench(opts: &BenchOptions) -> std::io::Result<()> {
    let effect_args = &opts.effect;
    let seconds = opts.seconds;
    let block = opts.block as usize;
    let sr: u32 = 48_000;
    let signal = fake_voice(sr, seconds);
    let load = Instant::now();
    let mut effect = Effect::new(effect_args, sr);
    let load_ms = load.elapsed().as_secs_f64() * 1000.0;
    let block_dur_us = block as f64 / sr as f64 * 1e6;

    // Time every block separately so we can report the slowest ones too:
    // in real time, one slow block is enough to cause a click.
    let mut block_us: Vec<f64> = Vec::with_capacity(signal.len() / block + 1);
    let mut rtf: Vec<f64> = Vec::with_capacity(block_us.capacity());
    let mut buf = vec![0.0f32; block];
    let cpu_start = results::cpu_time_s();
    for chunk in signal.chunks(block) {
        let buf = &mut buf[..chunk.len()];
        buf.copy_from_slice(chunk);
        let start = Instant::now();
        effect.process(buf);
        let us = start.elapsed().as_secs_f64() * 1e6;
        block_us.push(us);
        rtf.push(us / block_dur_us);
        // `black_box` stops the compiler from noticing we never use the
        // result and deleting the work we are trying to measure.
        std::hint::black_box(&buf);
    }
    let cpu_end = results::cpu_time_s();

    let mut report = Report::new("bench", effect_args.engine());
    report.load_ms = results::round3(load_ms);
    report.add("block_process_us", &block_us);
    report.add("rtf", &rtf);
    report.add(
        "algorithmic_latency_ms",
        &[effect.algorithmic_latency_ms(sr) as f64],
    );
    // `if let (Some(a), Some(b)) = ...` runs only when both values exist.
    if let (Some(a), Some(b)) = (cpu_start, cpu_end) {
        report.add("cpu_s_per_audio_s", &[(b - a) / seconds as f64]);
    }

    // One sample per second of audio: average and slowest block in that second.
    let blocks_per_s = (sr as usize / block).max(1);
    for (i, second) in block_us.chunks(blocks_per_s).enumerate() {
        let max = second.iter().cloned().fold(0.0, f64::max);
        report.samples.push(json!({
            "t_s": i,
            "block_process_us_mean": results::round3(results::mean(second)),
            "block_process_us_max": results::round3(max),
            "rtf_mean": results::round3(results::mean(second) / block_dur_us),
        }));
    }
    report.settings = effect_args.settings();
    report.settings["block"] = json!(block);
    report.settings["sample_rate"] = json!(sr);
    report.settings["audio_s"] = json!(seconds);

    println!(
        "Offline benchmark ({}): {seconds} s of audio, 48 kHz, blocks of {block} samples ({:.2} ms)\n",
        effect_args.summary(),
        block_dur_us / 1000.0
    );
    report.print();
    let path = report.save(&opts.out_dir)?;
    println!("\nSaved to {}", path.display());
    Ok(())
}

/// Applies the effect to an audio file so you can hear it without a live
/// setup. With an output path the result is saved as a WAV file; without
/// one it is played on the speakers instead.
/// `Box<dyn std::error::Error>` means "any kind of error"; handy when a
/// function can fail in several different ways (file not found, bad MP3...).
pub fn process_file(opts: &FileOptions) -> Result<(), Box<dyn std::error::Error>> {
    // Check this before the slow part, rather than fail at the very end.
    if let Some(path) = &opts.output
        && !path
            .extension()
            .is_some_and(|ext| ext.eq_ignore_ascii_case("wav"))
    {
        return Err("can only save WAV files; name the output like `out.wav`".into());
    }

    let (mut mono, sample_rate) = read_audio(&opts.input)?;
    let start = Instant::now();
    Effect::new(&opts.effect, sample_rate).process(&mut mono);
    let took = start.elapsed();
    let audio_s = mono.len() as f64 / sample_rate as f64;
    println!(
        "{}: {audio_s:.1} s of audio processed in {:.1} ms, {:.0}x faster than real time",
        opts.effect.summary(),
        took.as_secs_f64() * 1000.0,
        audio_s / took.as_secs_f64()
    );

    let Some(output) = &opts.output else {
        return live::play(mono, sample_rate);
    };
    let out_spec = hound::WavSpec {
        channels: 1,
        sample_rate,
        bits_per_sample: 32,
        sample_format: hound::SampleFormat::Float,
    };
    let mut writer = hound::WavWriter::create(output, out_spec)?;
    for s in mono.iter() {
        writer.write_sample(*s)?;
    }
    writer.finalize()?;
    println!("Wrote {}", output.display());
    Ok(())
}

/// A buzzy tone at about 150 Hz with a slight wobble, plus a bit of noise:
/// close enough to a voice for timing purposes.
fn fake_voice(sr: u32, seconds: f32) -> Vec<f32> {
    let n = (sr as f32 * seconds) as usize;
    let mut phase = 0.0f32;
    let mut noise_state: u32 = 12345;
    (0..n)
        .map(|i| {
            let t = i as f32 / sr as f32;
            let f0 = 150.0 + 10.0 * (2.0 * PI * 5.0 * t).sin();
            phase = (phase + f0 / sr as f32).fract();
            let mut s = 0.0;
            for h in 1..=8 {
                s += (2.0 * PI * phase * h as f32).sin() / h as f32;
            }
            // Tiny pseudo-random number generator, so we need no extra library.
            noise_state = noise_state
                .wrapping_mul(1_664_525)
                .wrapping_add(1_013_904_223);
            let noise = (noise_state >> 8) as f32 / (1u32 << 24) as f32 - 0.5;
            0.3 * s + 0.02 * noise
        })
        .collect()
}
