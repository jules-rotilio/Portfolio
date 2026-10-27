//! Live mode: microphone in, changed voice out, with latency measurements.
//!
//! The big picture:
//!
//!   microphone ──► input callback ──► ring buffer ──► output callback ──► speakers
//!                  (pitch shift here)  (a queue)
//!
//! The sound card asks for audio in small chunks on its own high-priority
//! threads. cpal calls our "callback" functions on those threads: one gives us
//! freshly recorded samples, the other asks us to fill the next samples to
//! play. The ring buffer passes audio from one thread to the other without
//! locks, so neither side ever has to wait (waiting is what causes clicks).
//!
//! This file also plays finished audio for the `file` command (`play`).
//! The device code both use is in the library's `devices.rs`.

use crate::results::{self, Report};
use clap::Args;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{BufferSize, InputCallbackInfo, OutputCallbackInfo, StreamConfig};
use ringbuf::traits::{Consumer, Observer, Producer, Split};
use ringbuf::{HeapCons, HeapRb};
use serde_json::{Value, json};
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, mpsc};
use std::time::{Duration, Instant};
use voice_changer::AnyResult;
use voice_changer::audio_file::resample;
use voice_changer::devices::{
    describe, device_name, open_input, open_output, output_config, pick_input, pick_output,
};
use voice_changer::effect::{Effect, EffectArgs};

/// The options of the `live` command. `#[derive(Args)]` lets clap fill this
/// struct straight from the command line; the `///` comments become `--help`.
#[derive(Args)]
pub struct LiveOptions {
    #[command(flatten)]
    effect: EffectArgs,
    /// Safety queue between mic and speaker in ms. Raise it if you hear clicks
    #[arg(long, default_value_t = 10.0)]
    buffer_ms: f32,
    /// Ask the sound card for blocks of this many samples (e.g. 128 or 256)
    #[arg(long, value_parser = clap::value_parser!(u32).range(1..=16_384))]
    block: Option<u32>,
    /// Stop after this many seconds instead of waiting for Enter
    #[arg(long)]
    seconds: Option<f32>,
    /// Use the first microphone whose name contains this text
    #[arg(long)]
    input: Option<String>,
    /// Use the first output whose name contains this text
    #[arg(long)]
    output: Option<String>,
    /// Folder for the benchmark result files
    #[arg(long, default_value_os_t = results::default_dir())]
    out_dir: PathBuf,
}

/// The latest numbers from the audio threads, for the main thread to read.
/// "Atomic" numbers can be safely changed by one thread while another reads
/// them, without locks. `Default` lets us create one with every value at 0.
#[derive(Default)]
struct Readings {
    input_latency_us: AtomicU64,
    output_latency_us: AtomicU64,
    ring_fill_frames: AtomicU64,
    underruns: AtomicU64,
    overflows: AtomicU64,
}

/// What the main thread collected while the audio was running.
#[derive(Default)]
struct Measurements {
    /// Time spent on each block, in microseconds...
    process_us: Vec<f64>,
    /// ...and as a share of the block's own duration (0.01 = 1%).
    rtf: Vec<f64>,
    /// Ten times a second, after the first second: the estimated
    /// mouth-to-ear delay and its parts, in milliseconds.
    e2e_ms: Vec<f64>,
    input_ms: Vec<f64>,
    queue_ms: Vec<f64>,
    output_ms: Vec<f64>,
    /// One status entry per second, for the results file.
    samples: Vec<Value>,
    duration_s: f64,
    /// CPU seconds the whole program used meanwhile, if the system tells us.
    cpu_s: Option<f64>,
}

/// Prints every microphone and speaker the program can see.
pub fn list_devices() -> AnyResult<()> {
    let host = cpal::default_host();
    println!("Audio system: {}", host.id().name());
    println!("\nInputs (microphones):");
    for d in host.input_devices()? {
        let cfg = d
            .default_input_config()
            .map(|c| describe(&c))
            .unwrap_or_default();
        println!("  {}  {cfg}", device_name(&d));
    }
    println!("\nOutputs (speakers, virtual cables):");
    for d in host.output_devices()? {
        let cfg = d
            .default_output_config()
            .map(|c| describe(&c))
            .unwrap_or_default();
        println!("  {}  {cfg}", device_name(&d));
    }
    Ok(())
}

pub fn run(opts: &LiveOptions) -> AnyResult<()> {
    let setup_start = Instant::now();
    let host = cpal::default_host();

    // 1. Pick the devices: the first whose name contains what the user typed
    //    after --input / --output, or else the system default.
    let input_device = pick_input(&host, opts.input.as_deref())?;
    let output_device = pick_output(&host, opts.output.as_deref())?;

    // 2. Pick formats. Both sides must run at the same sample rate (samples
    //    per second), otherwise the voice would drift faster or slower.
    let in_supported = input_device.default_input_config()?;
    let sr = in_supported.sample_rate();
    let out_supported = output_config(&output_device, sr)?;
    let mut in_config: StreamConfig = in_supported.config();
    let mut out_config: StreamConfig = out_supported.config();
    if let Some(frames) = opts.block {
        // Smaller blocks = less delay, but more risk of clicks.
        in_config.buffer_size = BufferSize::Fixed(frames);
        out_config.buffer_size = BufferSize::Fixed(frames);
    }
    println!("Audio system: {}", host.id().name());
    println!(
        "Input:  {}  {}",
        device_name(&input_device),
        describe(&in_supported)
    );
    println!(
        "Output: {}  {}",
        device_name(&output_device),
        describe(&out_supported)
    );

    // 3. The ring buffer between the two threads. It holds one second at
    //    most; we pre-fill it with a little silence (`buffer_ms`) so the
    //    output side has something to play if the input side is a bit late.
    let target_fill = (opts.buffer_ms / 1000.0 * sr as f32) as usize;
    let (mut audio_tx, mut audio_rx) = HeapRb::<f32>::new(sr as usize).split();
    for _ in 0..target_fill {
        let _ = audio_tx.try_push(0.0);
    }
    // A second, small ring buffer carries "how long did processing take"
    // measurements from the audio thread to the main thread.
    let (mut timing_tx, mut timing_rx) = HeapRb::<(f32, u32)>::new(4096).split();

    // `Arc` = "shared ownership": several threads can hold the same Readings.
    let readings = Arc::new(Readings::default());
    let mut effect = Effect::new(&opts.effect, sr);
    let algo_ms = effect.algorithmic_latency_ms(sr) as f64;

    // 4. The input callback. `move` means the closure takes ownership of
    //    the variables it uses (effect, audio_tx...), because it will live
    //    on another thread after this function has moved on.
    let in_readings = Arc::clone(&readings);
    let on_input = move |mono: &mut [f32], info: &InputCallbackInfo| {
        let ts = info.timestamp();
        let in_lat = ts.callback - ts.capture; // time since the mic captured this audio
        in_readings
            .input_latency_us
            .store(in_lat.as_micros() as u64, Ordering::Relaxed);

        let start = Instant::now();
        effect.process(mono);
        let took_us = start.elapsed().as_secs_f32() * 1e6;
        let _ = timing_tx.try_push((took_us, mono.len() as u32));

        if audio_tx.push_slice(mono) < mono.len() {
            in_readings.overflows.fetch_add(1, Ordering::Relaxed);
        }
    };

    // 5. The output callback.
    let out_readings = Arc::clone(&readings);
    let on_output = move |mono: &mut [f32], info: &OutputCallbackInfo| {
        let ts = info.timestamp();
        let out_lat = ts.playback - ts.callback; // time until these samples reach the speaker
        out_readings
            .output_latency_us
            .store(out_lat.as_micros() as u64, Ordering::Relaxed);

        // The mic and speaker clocks are never perfectly equal, so the queue
        // can slowly grow. If it gets too long, throw away the extra audio
        // to keep the delay low.
        let fill = audio_rx.occupied_len();
        if fill > target_fill + 2 * mono.len() {
            audio_rx.skip(fill - target_fill);
        }
        out_readings
            .ring_fill_frames
            .store(audio_rx.occupied_len() as u64, Ordering::Relaxed);

        let got = audio_rx.pop_slice(mono);
        if got < mono.len() {
            mono[got..].fill(0.0); // nothing to play: output silence
            out_readings.underruns.fetch_add(1, Ordering::Relaxed);
        }
    };

    // 6. Build the streams. The sound card may want its samples as decimals
    //    (f32) or as whole numbers (i16...). We do all our maths in f32 and
    //    convert at the edges (see `open_input` and `open_output`).
    let input_stream = open_input(&input_device, &in_supported, in_config, on_input)?;
    let output_stream = open_output(&output_device, &out_supported, out_config, on_output)?;
    input_stream.play()?;
    output_stream.play()?;
    let load_ms = setup_start.elapsed().as_secs_f64() * 1000.0;

    // 7. While the audio threads run, the main thread collects measurements.
    println!(
        "\nRunning: {}. Wear headphones to avoid feedback.",
        opts.effect.summary()
    );
    let m = measure(opts.seconds, sr, algo_ms, &readings, &mut timing_rx);
    drop(input_stream);
    drop(output_stream);

    // 8. Summarise and save.
    let mut report = Report::new("live", opts.effect.engine());
    report.load_ms = results::round3(load_ms);
    report.add("e2e_latency_ms", &m.e2e_ms);
    // Same number under the name the other two apps use for "time until you hear sound".
    report.add("first_audio_ms", &m.e2e_ms);
    report.add("input_latency_ms", &m.input_ms);
    report.add("queue_latency_ms", &m.queue_ms);
    report.add("output_latency_ms", &m.output_ms);
    report.add("algorithmic_latency_ms", &[algo_ms]);
    report.add("block_process_us", &m.process_us);
    report.add("rtf", &m.rtf);
    if let Some(cpu_s) = m.cpu_s {
        // Whole program, including the audio threads, per second of voice.
        report.add("cpu_s_per_audio_s", &[cpu_s / m.duration_s]);
    }
    report.samples = m.samples;
    let underruns = readings.underruns.load(Ordering::Relaxed);
    let overflows = readings.overflows.load(Ordering::Relaxed);
    report.counters.insert("underruns".into(), underruns);
    report.counters.insert("overflows".into(), overflows);
    // Start from the effect's own settings, then add the rest.
    report.settings = opts.effect.settings();
    report.settings["buffer_ms"] = json!(opts.buffer_ms);
    report.settings["block"] = json!(opts.block); // `None` becomes `null` = the sound card's default
    report.settings["sample_rate"] = json!(sr);
    report.settings["duration_s"] = json!(results::round3(m.duration_s));
    report.settings["audio_host"] = json!(host.id().name());
    report.settings["input_device"] = json!(device_name(&input_device));
    report.settings["output_device"] = json!(device_name(&output_device));

    println!("\nSummary:");
    report.print();
    let path = report.save(&opts.out_dir)?;
    println!("\nSaved to {}", path.display());
    Ok(())
}

/// The main thread's job while the audio threads work. Every 100 ms it
/// collects their latest numbers, and once a second it prints a status line.
/// Returns after `seconds`, or when Enter is pressed if there is no limit.
fn measure(
    seconds: Option<f32>,
    sr: u32,
    algo_ms: f64,
    readings: &Readings,
    timing_rx: &mut HeapCons<(f32, u32)>,
) -> Measurements {
    let stop_rx = match seconds {
        Some(s) => {
            println!("Stopping automatically after {s} s.\n");
            None
        }
        None => {
            println!("Press Enter to stop.\n");
            Some(wait_for_enter())
        }
    };

    let mut m = Measurements::default();
    let started = Instant::now();
    let cpu_start = results::cpu_time_s();
    let mut last_print = started;
    let mut since_print = 0; // index into `m.process_us` at the last printout

    loop {
        std::thread::sleep(Duration::from_millis(100));
        let elapsed = started.elapsed().as_secs_f32();
        if let Some(rx) = &stop_rx
            && rx.try_recv().is_ok()
        {
            break;
        }
        if seconds.is_some_and(|limit| elapsed >= limit) {
            break;
        }

        // Collect processing times sent by the input thread.
        while let Some((us, frames)) = timing_rx.try_pop() {
            let block_us = frames as f64 / sr as f64 * 1e6;
            m.process_us.push(us as f64);
            m.rtf.push(us as f64 / block_us);
        }

        // Estimated mouth-to-ear delay = time in the input driver
        // + time waiting in our queue + time in the output driver + the effect itself.
        let i = readings.input_latency_us.load(Ordering::Relaxed) as f64 / 1000.0;
        let o = readings.output_latency_us.load(Ordering::Relaxed) as f64 / 1000.0;
        let q = readings.ring_fill_frames.load(Ordering::Relaxed) as f64 / sr as f64 * 1000.0;
        let total = i + q + o + algo_ms;
        // Skip the first second: devices are still settling.
        if elapsed > 1.0 {
            m.e2e_ms.push(total);
            m.input_ms.push(i);
            m.output_ms.push(o);
            m.queue_ms.push(q);
        }

        // Once per second: print a status line and keep it as a sample.
        if last_print.elapsed() >= Duration::from_secs(1) {
            last_print = Instant::now();
            let recent = &m.process_us[since_print..];
            since_print = m.process_us.len();
            let underruns = readings.underruns.load(Ordering::Relaxed);
            println!(
                "latency ≈ {total:5.1} ms (input {i:.1} + queue {q:.1} + output {o:.1} + effect {algo_ms:.1}) | \
                 processing {:.1} us/block | underruns {underruns}",
                results::mean(recent),
            );
            m.samples.push(json!({
                "t_s": results::round3(elapsed as f64),
                "e2e_latency_ms": results::round3(total),
                "input_latency_ms": results::round3(i),
                "queue_latency_ms": results::round3(q),
                "output_latency_ms": results::round3(o),
                "block_process_us_mean": results::round3(results::mean(recent)),
                "underruns_total": underruns,
            }));
        }
    }

    m.duration_s = started.elapsed().as_secs_f64();
    if let (Some(a), Some(b)) = (cpu_start, results::cpu_time_s()) {
        m.cpu_s = Some(b - a);
    }
    m
}

/// Plays finished audio on the default output (this is what the `file`
/// command does when you give it no output file). Returns once everything
/// has been heard, or when Enter is pressed.
pub fn play(samples: Vec<f32>, sample_rate: u32) -> AnyResult<()> {
    let host = cpal::default_host();
    let device = pick_output(&host, None)?;
    // Play at the audio's own rate if the device can. If it can't, convert
    // the audio to the device's rate, or it would play too fast or too slow.
    let (supported, samples) = match output_config(&device, sample_rate) {
        Ok(supported) => (supported, samples),
        Err(_) => {
            let supported = device.default_output_config()?;
            let converted = resample(&samples, sample_rate, supported.sample_rate());
            (supported, converted)
        }
    };
    let sr = supported.sample_rate();
    println!("Output: {}  {}", device_name(&device), describe(&supported));
    let seconds = samples.len() as f64 / sr as f64;

    // The output callback hands over the next samples, and silence once they
    // run out. Along with the last ones, it tells the main thread how long
    // until they come out of the speaker.
    let (done_tx, done_rx) = mpsc::channel();
    let mut done_tx = Some(done_tx);
    let mut pos = 0;
    let on_output = move |mono: &mut [f32], info: &OutputCallbackInfo| {
        let n = mono.len().min(samples.len() - pos);
        mono[..n].copy_from_slice(&samples[pos..pos + n]);
        mono[n..].fill(0.0);
        pos += n;
        // `take()` empties the `Option`, so the message is only sent once.
        if pos == samples.len()
            && let Some(tx) = done_tx.take()
        {
            let ts = info.timestamp();
            let this_block = Duration::from_secs_f64(n as f64 / sr as f64);
            let _ = tx.send(ts.playback - ts.callback + this_block);
        }
    };
    let stream = open_output(&device, &supported, supported.config(), on_output)?;
    stream.play()?;
    println!("\nPlaying {seconds:.1} s of audio. Press Enter to stop.");

    let stop_rx = wait_for_enter();
    loop {
        if let Ok(left) = done_rx.recv_timeout(Duration::from_millis(50)) {
            // The delay the system reports is an estimate: leave a little extra.
            std::thread::sleep(left + Duration::from_millis(100));
            break;
        }
        if stop_rx.try_recv().is_ok() {
            break;
        }
    }
    Ok(())
}

/// Starts a helper thread that waits for Enter and then sends a message.
fn wait_for_enter() -> mpsc::Receiver<()> {
    let (tx, rx) = mpsc::channel();
    std::thread::spawn(move || {
        let mut line = String::new();
        let _ = std::io::stdin().read_line(&mut line);
        let _ = tx.send(());
    });
    rx
}
