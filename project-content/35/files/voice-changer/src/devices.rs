//! Finding sound devices and opening streams on them.
//!
//! The sound card may want its samples as decimals (f32) or as whole numbers
//! (i16...). Everything else in this crate works in f32, mono; the functions
//! here convert at the edges: `open_input` averages the channels into mono,
//! `open_output` copies each mono sample to every channel.

use crate::AnyResult;
use cpal::traits::{DeviceTrait, HostTrait};
use cpal::{
    Device, FromSample, InputCallbackInfo, OutputCallbackInfo, Sample, SampleFormat, SizedSample,
    Stream, StreamConfig, SupportedStreamConfig,
};

/// Builds the microphone stream in whatever sample type the device gives.
pub fn open_input(
    device: &Device,
    supported: &SupportedStreamConfig,
    config: StreamConfig,
    on_mono: impl FnMut(&mut [f32], &InputCallbackInfo) + Send + 'static,
) -> AnyResult<Stream> {
    match supported.sample_format() {
        SampleFormat::F32 => build_input::<f32>(device, config, on_mono),
        SampleFormat::I16 => build_input::<i16>(device, config, on_mono),
        SampleFormat::I32 => build_input::<i32>(device, config, on_mono),
        SampleFormat::U16 => build_input::<u16>(device, config, on_mono),
        other => Err(format!("unsupported microphone sample format {other}").into()),
    }
}

/// Builds the microphone stream for sample type `T`.
///
/// `<T>` makes this a "generic" function: one recipe, compiled once per
/// sample type we use it with. The `where` lines are requirements on `T`:
/// it must be an audio sample type, and convertible to f32.
/// `impl FnMut(...)` means "any function or closure with this shape".
fn build_input<T>(
    device: &Device,
    config: StreamConfig,
    mut on_mono: impl FnMut(&mut [f32], &InputCallbackInfo) + Send + 'static,
) -> AnyResult<Stream>
where
    T: SizedSample,
    f32: FromSample<T>,
{
    let channels = config.channels as usize;
    // Reserve memory up front so the audio thread rarely has to allocate.
    let mut mono: Vec<f32> = Vec::with_capacity(16_384);
    let stream = device.build_input_stream::<T, _, _>(
        config,
        move |data: &[T], info: &InputCallbackInfo| {
            // Audio arrives "interleaved": L R L R... We average each frame
            // (one sample per channel) into a single mono sample.
            mono.clear();
            mono.extend(data.chunks(channels).map(|frame| {
                frame.iter().map(|&s| f32::from_sample(s)).sum::<f32>() / channels as f32
            }));
            on_mono(&mut mono, info);
        },
        |err| eprintln!("microphone error: {err}"),
        None,
    )?;
    Ok(stream)
}

/// Builds the speaker stream in whatever sample type the device wants.
pub fn open_output(
    device: &Device,
    supported: &SupportedStreamConfig,
    config: StreamConfig,
    fill_mono: impl FnMut(&mut [f32], &OutputCallbackInfo) + Send + 'static,
) -> AnyResult<Stream> {
    match supported.sample_format() {
        SampleFormat::F32 => build_output::<f32>(device, config, fill_mono),
        SampleFormat::I16 => build_output::<i16>(device, config, fill_mono),
        SampleFormat::I32 => build_output::<i32>(device, config, fill_mono),
        SampleFormat::U16 => build_output::<u16>(device, config, fill_mono),
        other => Err(format!("unsupported output sample format {other}").into()),
    }
}

/// Builds the speaker stream for sample type `T`: asks for mono samples and
/// copies each one to every output channel.
fn build_output<T>(
    device: &Device,
    config: StreamConfig,
    mut fill_mono: impl FnMut(&mut [f32], &OutputCallbackInfo) + Send + 'static,
) -> AnyResult<Stream>
where
    T: SizedSample + FromSample<f32>,
{
    let channels = config.channels as usize;
    let mut mono: Vec<f32> = Vec::with_capacity(16_384);
    let stream = device.build_output_stream::<T, _, _>(
        config,
        move |data: &mut [T], info: &OutputCallbackInfo| {
            mono.resize(data.len() / channels, 0.0);
            fill_mono(&mut mono, info);
            for (frame, &s) in data.chunks_mut(channels).zip(mono.iter()) {
                frame.fill(T::from_sample(s));
            }
        },
        |err| eprintln!("output error: {err}"),
        None,
    )?;
    Ok(stream)
}

/// Finds an output format at sample rate `sr`, preferring the device default.
pub fn output_config(device: &Device, sr: u32) -> AnyResult<SupportedStreamConfig> {
    let default = device.default_output_config()?;
    if default.sample_rate() == sr {
        return Ok(default);
    }
    // Otherwise, the format closest to the default that can run at `sr`. A
    // device can list odd ones first (PulseAudio starts with 1-channel u8),
    // so keep the sample types we can write, and put the default's type and
    // channel count first (`false` sorts before `true`).
    let mut ranges: Vec<_> = device
        .supported_output_configs()?
        .filter(|r| {
            matches!(
                r.sample_format(),
                SampleFormat::F32 | SampleFormat::I16 | SampleFormat::I32 | SampleFormat::U16
            )
        })
        .collect();
    ranges.sort_by_key(|r| {
        (
            r.sample_format() != default.sample_format(),
            r.channels() != default.channels(),
        )
    });
    if let Some(cfg) = ranges.into_iter().find_map(|r| r.try_with_sample_rate(sr)) {
        return Ok(cfg);
    }
    Err(format!(
        "the output device can't run at {sr} Hz like the microphone; set both to the same rate in your sound settings"
    )
    .into())
}

/// The microphone whose name contains `wanted`, or the default one.
pub fn pick_input(host: &cpal::Host, wanted: Option<&str>) -> AnyResult<Device> {
    match wanted {
        Some(name) => find_device(host.input_devices()?, name),
        None => default_device(
            host,
            host.input_devices().ok(),
            host.default_input_device(),
            |d| d.default_input_config().is_ok(),
        )
        .ok_or_else(|| "no microphone found".into()),
    }
}

/// The output whose name contains `wanted`, or the default one.
pub fn pick_output(host: &cpal::Host, wanted: Option<&str>) -> AnyResult<Device> {
    match wanted {
        Some(name) => find_device(host.output_devices()?, name),
        None => default_device(
            host,
            host.output_devices().ok(),
            host.default_output_device(),
            |d| d.default_output_config().is_ok(),
        )
        .ok_or_else(|| "no output device found".into()),
    }
}

/// The device to use when the user didn't pick one.
///
/// On Linux, the plain ALSA "default" often can't be opened because PipeWire
/// or PulseAudio already owns the sound card. The "pulse" device talks to that
/// sound server instead and follows the desktop's default mic and speakers, so
/// we prefer it when it works and fall back to the ALSA default otherwise.
fn default_device(
    host: &cpal::Host,
    devices: Option<impl Iterator<Item = Device>>,
    fallback: Option<Device>,
    works: impl Fn(&Device) -> bool,
) -> Option<Device> {
    if host.id().name() == "ALSA" {
        let pulse = devices.and_then(|d| find_device(d, "pulseaudio").ok());
        if let Some(pulse) = pulse.filter(|d| works(d)) {
            return Some(pulse);
        }
    }
    fallback
}

/// The first device whose name contains `wanted`, ignoring upper and lower case.
pub fn find_device(devices: impl Iterator<Item = Device>, wanted: &str) -> AnyResult<Device> {
    let wanted = wanted.to_lowercase();
    devices
        .into_iter()
        .find(|d| device_name(d).to_lowercase().contains(&wanted))
        .ok_or_else(|| {
            format!("no device name contains \"{wanted}\"; run `voice-changer devices`").into()
        })
}

/// The device's name as people see it, e.g. "PulseAudio Sound Server".
pub fn device_name(d: &Device) -> String {
    d.description()
        .map(|desc| desc.name().to_string())
        .unwrap_or_else(|_| "(unknown device)".into())
}

/// A format in a few words, e.g. "[48000 Hz, 2 ch, f32]".
pub fn describe(c: &SupportedStreamConfig) -> String {
    format!(
        "[{} Hz, {} ch, {}]",
        c.sample_rate(),
        c.channels(),
        c.sample_format()
    )
}
