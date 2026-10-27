//! The audio engine: one microphone stream, and one output stream per device.
//!
//! ```text
//!  mic ─► offset removed, gate ─► effect ─► one queue per device ──────┐
//!  sound clip (decoded once, at each device's rate) ───────────────────┼─► mix ─► output device
//!  captured program (programs.rs) ─► one queue per device others hear ─┘
//! ```
//!
//! Each output device has *roles*: it can be the voice's virtual output, the
//! soundboard's virtual output, the headset (monitor), the voice test device,
//! or several at once (then everything is mixed into that one stream).
//!
//! The audio threads never wait and never allocate: they get commands
//! through lock-free queues, and volumes and switches are atomic numbers.

use crate::config::Sound;
use crate::gate::{DcBlock, Gate};
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use cpal::{Device, Host, InputCallbackInfo, OutputCallbackInfo, Stream};
use ringbuf::traits::{Consumer, Observer, Producer, Split};
use ringbuf::{HeapCons, HeapProd, HeapRb};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use voice_changer::audio_file::{read_audio, resample};
use voice_changer::devices::{device_name, find_device, open_input, open_output, output_config};
use voice_changer::effect::{Effect, EffectArgs};

/// An `f32` that several threads can read and write (stored as its bits).
#[derive(Default)]
pub struct AtomicF32(AtomicU32);

impl AtomicF32 {
    pub fn new(v: f32) -> Self {
        AtomicF32(AtomicU32::new(v.to_bits()))
    }
    pub fn get(&self) -> f32 {
        f32::from_bits(self.0.load(Ordering::Relaxed))
    }
    pub fn set(&self, v: f32) {
        self.0.store(v.to_bits(), Ordering::Relaxed)
    }
    /// Raises the value to `v` if `v` is bigger (for peak meters; `v` >= 0).
    fn raise(&self, v: f32) {
        // Positive floats compare like their bits, so an integer max works.
        self.0.fetch_max(v.to_bits(), Ordering::Relaxed);
    }
    /// Reads the value and resets it to 0.
    fn take(&self) -> f32 {
        f32::from_bits(self.0.swap(0, Ordering::Relaxed))
    }
}

/// Switches and numbers shared with the audio threads. It outlives the
/// streams, so restarting the engine keeps them.
pub struct Shared {
    /// Your changed voice goes to the virtual output.
    pub voice_on: AtomicBool,
    /// Your changed voice goes to the headset (or the test device).
    pub test_on: AtomicBool,
    pub sound_volume: AtomicF32,
    pub headset_volume: AtomicF32,
    /// The noise gate silences the mic between words.
    pub gate_on: AtomicBool,
    /// It opens this many dB above the noise floor.
    pub gate_margin: AtomicF32,
    /// The mic's noise floor in dB, NaN while it is being measured.
    noise_floor: AtomicF32,
    /// The captured program's volume, in what others hear.
    pub program_volume: AtomicF32,
    pub program: ProgramTap,
    mic_peak: AtomicF32,
    virtual_peak: AtomicF32,
    pub underruns: AtomicU64,
}

impl Shared {
    pub fn new() -> Arc<Shared> {
        Arc::new(Shared {
            voice_on: AtomicBool::new(false),
            test_on: AtomicBool::new(false),
            sound_volume: AtomicF32::new(0.6),
            headset_volume: AtomicF32::new(0.8),
            gate_on: AtomicBool::new(true),
            gate_margin: AtomicF32::new(9.0),
            noise_floor: AtomicF32::new(f32::NAN),
            program_volume: AtomicF32::new(0.5),
            program: ProgramTap::default(),
            mic_peak: AtomicF32::default(),
            virtual_peak: AtomicF32::default(),
            underruns: AtomicU64::new(0),
        })
    }

    /// The loudest sample since the last call: (mic, virtual output).
    pub fn take_peaks(&self) -> (f32, f32) {
        (self.mic_peak.take(), self.virtual_peak.take())
    }

    /// The mic's noise floor in dB, once it has been measured.
    pub fn noise_floor(&self) -> Option<f32> {
        Some(self.noise_floor.get()).filter(|f| !f.is_nan())
    }
}

/// Where a captured program's sound enters the engine (`programs.rs` pushes
/// into it): one queue per output that others hear, swapped when the
/// engine restarts.
#[derive(Default)]
pub struct ProgramTap {
    queues: Mutex<Vec<HeapProd<f32>>>,
    /// The sample rate the queues expect, 0 before the engine first starts.
    rate: AtomicU32,
}

impl ProgramTap {
    pub fn rate(&self) -> u32 {
        self.rate.load(Ordering::Relaxed)
    }

    /// Called from the capture's audio thread. It never waits: while the
    /// engine is swapping the queues, the block is dropped.
    pub fn push(&self, mono: &[f32]) {
        if let Ok(mut queues) = self.queues.try_lock() {
            for queue in queues.iter_mut() {
                queue.push_slice(mono);
            }
        }
    }
}

/// What one output device is used for.
#[derive(Clone, Copy, Default, PartialEq, Eq, Debug)]
pub struct Roles {
    /// The voice's virtual output.
    pub voice: bool,
    /// The soundboard's virtual output.
    pub sound: bool,
    /// The headset: you hear the sounds here.
    pub monitor: bool,
    /// You hear your changed voice here while testing.
    pub test: bool,
}

impl Roles {
    fn wants_voice(self) -> bool {
        self.voice || self.test
    }
    fn wants_sounds(self) -> bool {
        self.sound || self.monitor
    }
}

/// The devices to use, by name. `None`: the system default (mic, headset)
/// or nothing (virtual outputs).
#[derive(Clone, PartialEq, Debug, Default)]
pub struct Routing {
    pub mic: Option<String>,
    pub voice_out: Option<String>,
    pub sound_out: Option<String>,
    pub headset: Option<String>,
    pub test_out: Option<String>,
    /// Size of the blocks the sound system exchanges with Intercom, in ms.
    pub block_ms: u32,
}

/// Asks for `block_ms` blocks if the device allows that size. Left to
/// itself, PulseAudio picks a 2-second playback buffer: every sound would
/// start and stop 2 s late. A fixed size also asks it for low latency.
pub(crate) fn buffer_size(
    supported: &cpal::SupportedStreamConfig,
    rate: u32,
    block_ms: u32,
) -> (cpal::BufferSize, usize) {
    let frames = (rate * block_ms.max(1) / 1000).max(32);
    match supported.buffer_size() {
        cpal::SupportedBufferSize::Range { min, max } if !(*min..=*max).contains(&frames) => {
            (cpal::BufferSize::Default, rate as usize / 100)
        }
        _ => (cpal::BufferSize::Fixed(frames), frames as usize),
    }
}

enum OutCmd {
    Play {
        samples: Arc<[f32]>,
        gain: f32,
    },
    Stop,
    /// A short signal for you alone (the auto-click chimes), on top of the sound.
    Cue {
        samples: Arc<[f32]>,
        gain: f32,
    },
}

/// The engine's side of one output stream.
struct OutputLink {
    rate: u32,
    roles: Roles,
    commands: HeapProd<OutCmd>,
}

/// Decoded sound files, kept so a key plays instantly the second time.
#[derive(Default)]
struct ClipCache {
    decoded: HashMap<PathBuf, Arc<(Vec<f32>, u32)>>,
    at_rate: HashMap<(PathBuf, u32), Arc<[f32]>>,
}

impl ClipCache {
    fn decoded(&mut self, path: &Path) -> Result<Arc<(Vec<f32>, u32)>, String> {
        if let Some(clip) = self.decoded.get(path) {
            return Ok(Arc::clone(clip));
        }
        let (samples, rate) = read_audio(path).map_err(|e| e.to_string())?;
        let clip = Arc::new((samples, rate));
        self.decoded.insert(path.to_path_buf(), Arc::clone(&clip));
        Ok(clip)
    }

    fn at_rate(&mut self, path: &Path, rate: u32) -> Result<Arc<[f32]>, String> {
        if let Some(clip) = self.at_rate.get(&(path.to_path_buf(), rate)) {
            return Ok(Arc::clone(clip));
        }
        let decoded = self.decoded(path)?;
        let (samples, from) = (&decoded.0, decoded.1);
        let clip: Arc<[f32]> = if from == rate {
            samples.as_slice().into()
        } else {
            resample(samples, from, rate).into()
        };
        self.at_rate
            .insert((path.to_path_buf(), rate), Arc::clone(&clip));
        Ok(clip)
    }
}

pub struct NowPlaying {
    pub title: String,
    started: Instant,
    length: Duration,
}

/// Plays sound clips. Shared by the window and the hotkey thread.
pub struct Player {
    pub shared: Arc<Shared>,
    outputs: Mutex<Vec<OutputLink>>,
    clips: Mutex<ClipCache>,
    now: Mutex<Option<NowPlaying>>,
    random: AtomicU64,
}

impl Player {
    fn new(shared: Arc<Shared>) -> Player {
        let seed = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos() as u64)
            .unwrap_or(1);
        Player {
            shared,
            outputs: Mutex::new(Vec::new()),
            clips: Mutex::new(ClipCache::default()),
            now: Mutex::new(None),
            random: AtomicU64::new(seed | 1),
        }
    }

    /// A pseudo-random number below `n` (xorshift: plenty for picking a sound).
    fn pick(&self, n: usize) -> usize {
        let mut x = self.random.load(Ordering::Relaxed);
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.random.store(x, Ordering::Relaxed);
        (x % n as u64) as usize
    }

    /// Plays `sound` on the soundboard's virtual output and the headset, or,
    /// with `preview`, on the headset only.
    pub fn play(&self, sound: &Sound, preview: bool) -> Result<(), String> {
        if sound.files.is_empty() {
            return Ok(());
        }
        let path = &sound.files[self.pick(sound.files.len())];
        let mut outputs = self.outputs.lock().unwrap();
        if outputs.is_empty() {
            return Err("no output device is open".into());
        }
        let mut clips = self.clips.lock().unwrap();
        let decoded = clips.decoded(path)?;
        let length = Duration::from_secs_f64(decoded.0.len() as f64 / decoded.1 as f64);
        for out in outputs.iter_mut() {
            let wanted = if preview {
                out.roles.monitor
            } else {
                out.roles.wants_sounds()
            };
            if wanted {
                let samples = clips.at_rate(path, out.rate)?;
                let _ = out.commands.try_push(OutCmd::Play {
                    samples,
                    gain: sound.volume,
                });
            } else if out.roles.wants_sounds() {
                let _ = out.commands.try_push(OutCmd::Stop);
            }
        }
        *self.now.lock().unwrap() = Some(NowPlaying {
            title: Sound {
                files: vec![path.clone()],
                volume: 1.0,
            }
            .title(),
            started: Instant::now(),
            length,
        });
        Ok(())
    }

    /// Plays a short signal in the headset only, never to the others.
    /// `make` builds it at a given sample rate.
    pub fn cue(&self, make: impl Fn(u32) -> Vec<f32>, gain: f32) {
        for out in self.outputs.lock().unwrap().iter_mut() {
            if out.roles.monitor && !out.roles.sound && !out.roles.voice {
                let samples = make(out.rate).into();
                let _ = out.commands.try_push(OutCmd::Cue { samples, gain });
            }
        }
    }

    pub fn stop(&self) {
        for out in self.outputs.lock().unwrap().iter_mut() {
            let _ = out.commands.try_push(OutCmd::Stop);
        }
        *self.now.lock().unwrap() = None;
    }

    /// (title, seconds played, length in seconds) of the sound playing now.
    pub fn now_playing(&self) -> Option<(String, f32, f32)> {
        let mut now = self.now.lock().unwrap();
        let playing = now.as_ref()?;
        let elapsed = playing.started.elapsed();
        if elapsed > playing.length {
            *now = None;
            return None;
        }
        Some((
            playing.title.clone(),
            elapsed.as_secs_f32(),
            playing.length.as_secs_f32(),
        ))
    }
}

/// What the engine ended up using, and what went wrong.
#[derive(Default, Clone)]
pub struct EngineStatus {
    pub mic: Option<String>,
    pub voice_out: Option<String>,
    pub sound_out: Option<String>,
    pub headset: Option<String>,
    pub problems: Vec<String>,
}

pub struct Engine {
    pub player: Arc<Player>,
    streams: Vec<Stream>,
    mic_rate: Option<u32>,
    effect_tx: Option<HeapProd<Effect>>,
    trash_rx: Option<HeapCons<Effect>>,
    pub status: EngineStatus,
}

/// The sound system to use: PulseAudio on Linux (so a device can be picked by
/// name, including Intercom's own virtual one), the default elsewhere.
pub fn host() -> Host {
    #[cfg(target_os = "linux")]
    if let Ok(host) = cpal::host_from_id(cpal::HostId::PulseAudio) {
        return host;
    }
    cpal::default_host()
}

/// Whether `device` only repeats sound from this computer: Intercom's own
/// virtual mic, the "monitor" of a speaker, VB-Cable... Taken as the mic, it
/// would send what others hear back to them, in a loop.
pub fn is_virtual_input(device: &Device) -> bool {
    #[cfg(target_os = "linux")]
    if let Ok(id) = device.id()
        && id.host() == cpal::HostId::PulseAudio
    {
        let id = id.id();
        return id.ends_with(".monitor") || id == crate::virtual_mic::SOURCE_NAME;
    }
    let name = device_name(device);
    name.contains("CABLE Output") || name.contains("VB-Audio")
}

/// The real microphones.
fn physical_inputs(host: &Host) -> Vec<Device> {
    host.input_devices()
        .map(|d| d.filter(|d| !is_virtual_input(d)).collect())
        .unwrap_or_default()
}

/// The system's default mic, unless it is a virtual one (Intercom's own mic
/// can be the default): then the first real one.
fn default_physical_input(host: &Host) -> Option<Device> {
    host.default_input_device()
        .filter(|d| !is_virtual_input(d))
        .or_else(|| physical_inputs(host).into_iter().next())
}

/// The name of the mic used when none is picked.
pub fn default_mic_name(host: &Host) -> Option<String> {
    default_physical_input(host).map(|d| device_name(&d))
}

/// Names of the (real microphones, outputs) the host offers.
pub fn device_names(host: &Host) -> (Vec<String>, Vec<String>) {
    let names = |devices: Option<Vec<Device>>| {
        let mut names: Vec<String> = devices
            .unwrap_or_default()
            .iter()
            .map(device_name)
            .collect();
        names.dedup();
        names
    };
    (
        names(Some(physical_inputs(host))),
        names(host.output_devices().ok().map(|d| d.collect())),
    )
}

/// The device named `name` (exactly, else the first whose name contains it).
fn find(devices: Option<impl Iterator<Item = Device>>, name: &str) -> Option<Device> {
    let devices: Vec<Device> = devices?.collect();
    if let Some(d) = devices.iter().find(|d| device_name(d) == name) {
        return Some(d.clone());
    }
    find_device(devices.into_iter(), name).ok()
}

impl Engine {
    pub fn new(shared: Arc<Shared>) -> Engine {
        Engine {
            player: Arc::new(Player::new(shared)),
            streams: Vec::new(),
            mic_rate: None,
            effect_tx: None,
            trash_rx: None,
            status: EngineStatus::default(),
        }
    }

    pub fn is_running(&self) -> bool {
        !self.streams.is_empty()
    }

    /// Closes every stream (the sound in progress stops).
    pub fn stop(&mut self) {
        self.streams.clear();
        self.player.outputs.lock().unwrap().clear();
        self.player.shared.program.queues.lock().unwrap().clear();
        *self.player.now.lock().unwrap() = None;
        self.effect_tx = None;
        self.trash_rx = None;
        self.mic_rate = None;
    }

    /// (Re)opens the streams for `routing`, with the voice `effect`.
    pub fn start(&mut self, host: &Host, routing: &Routing, effect: &EffectArgs) {
        self.stop();
        let mut status = EngineStatus::default();
        let shared = Arc::clone(&self.player.shared);

        // 1. The microphone sets the sample rate for the voice. Only real
        // mics: "Monitor of My Headset" contains "My Headset" too.
        let mic = match &routing.mic {
            Some(name) => find(Some(physical_inputs(host).into_iter()), name),
            None => default_physical_input(host),
        };
        let mic = mic.and_then(|d| match d.default_input_config() {
            Ok(cfg) => Some((d, cfg)),
            Err(e) => {
                status
                    .problems
                    .push(format!("Can't use the microphone: {e}"));
                None
            }
        });
        if mic.is_none() && status.problems.is_empty() {
            status.problems.push(match &routing.mic {
                Some(name) => format!("Microphone \"{name}\" not found"),
                None => "No microphone found".into(),
            });
        }
        let mic_rate = mic.as_ref().map(|(_, cfg)| cfg.sample_rate());
        status.mic = mic.as_ref().map(|(d, _)| device_name(d));

        // 2. The output devices, each with its roles.
        let mut wanted: Vec<(String, Device, Roles)> = Vec::new();
        let mut add = |name: &Option<String>, default_ok: bool, set: fn(&mut Roles), what: &str| {
            let device = match name {
                Some(n) => find(host.output_devices().ok(), n),
                None if default_ok => host.default_output_device(),
                None => return None,
            };
            let Some(device) = device else {
                status.problems.push(format!(
                    "{what}: \"{}\" not found",
                    name.as_deref().unwrap_or("default")
                ));
                return None;
            };
            let actual = device_name(&device);
            match wanted.iter_mut().find(|(n, _, _)| *n == actual) {
                Some((_, _, roles)) => set(roles),
                None => {
                    let mut roles = Roles::default();
                    set(&mut roles);
                    wanted.push((actual.clone(), device, roles));
                }
            }
            Some(actual)
        };
        status.voice_out = add(
            &routing.voice_out,
            false,
            |r| r.voice = true,
            "Voice output",
        );
        status.sound_out = add(
            &routing.sound_out,
            false,
            |r| r.sound = true,
            "Sound output",
        );
        status.headset = add(&routing.headset, true, |r| r.monitor = true, "Headset");
        add(
            &routing.test_out,
            true,
            |r| r.test = true,
            "Voice test device",
        );

        // 3. Open the outputs. Those that carry the voice get a queue from the
        // mic, those others hear get one from the captured program.
        let mut voice_queues: Vec<(HeapProd<f32>, Roles)> = Vec::new();
        let mut program_queues: Vec<HeapProd<f32>> = Vec::new();
        let program_rate = mic_rate.unwrap_or(48_000);
        let mut links = Vec::new();
        let peak_on = |roles: Roles| roles.voice || (roles.sound && !wanted_has_voice(&wanted));
        let peaks: Vec<bool> = wanted.iter().map(|(_, _, r)| peak_on(*r)).collect();
        for ((name, device, mut roles), peak) in wanted.into_iter().zip(peaks) {
            let rate_wanted = mic_rate.unwrap_or(48_000);
            let supported = match output_config(&device, rate_wanted).or_else(|_| {
                device
                    .default_output_config()
                    .map_err(|e| Box::new(e) as Box<dyn std::error::Error>)
            }) {
                Ok(s) => s,
                Err(e) => {
                    status.problems.push(format!("Can't open \"{name}\": {e}"));
                    continue;
                }
            };
            let rate = supported.sample_rate();
            let (buffer, block) = buffer_size(&supported, rate, routing.block_ms);
            if roles.wants_voice() && Some(rate) != mic_rate {
                status.problems.push(format!(
                    "\"{name}\" can't run at the microphone's rate; no voice is sent there"
                ));
                roles.voice = false;
                roles.test = false;
            }
            let (cmd_tx, cmd_rx) = HeapRb::<OutCmd>::new(16).split();
            let voice = if roles.wants_voice() {
                let (tx, rx) = HeapRb::<f32>::new(rate as usize).split();
                voice_queues.push((tx, roles));
                Some(Cushioned::new(rx, block, 0))
            } else {
                None
            };
            // The capture runs on its own clock, in blocks of its own size:
            // a larger cushion, and more slack before throwing samples away.
            let program = if roles.sound && rate == program_rate {
                let (tx, rx) = HeapRb::<f32>::new(rate as usize).split();
                program_queues.push(tx);
                let ms40 = rate as usize / 25;
                Some(Cushioned::new(rx, block.max(ms40), ms40))
            } else {
                None
            };
            let mut out = OutputState {
                roles,
                shared: Arc::clone(&shared),
                commands: cmd_rx,
                clip: None,
                cue: None,
                voice,
                program,
                peak,
            };
            let mut config = supported.config();
            config.buffer_size = buffer;
            let stream = open_output(
                &device,
                &supported,
                config,
                move |mono: &mut [f32], _: &OutputCallbackInfo| out.fill(mono),
            );
            match stream.and_then(|s| s.play().map(|_| s).map_err(Into::into)) {
                Ok(stream) => {
                    self.streams.push(stream);
                    links.push(OutputLink {
                        rate,
                        roles,
                        commands: cmd_tx,
                    });
                }
                Err(e) => status.problems.push(format!("Can't open \"{name}\": {e}")),
            }
        }
        *self.player.outputs.lock().unwrap() = links;
        *shared.program.queues.lock().unwrap() = program_queues;
        shared.program.rate.store(program_rate, Ordering::Relaxed);

        // 4. The microphone stream: effect, then a copy to each voice queue.
        if let (Some((device, supported)), Some(rate)) = (mic, mic_rate)
            && !voice_queues.is_empty()
        {
            let (effect_tx, mut effect_rx) = HeapRb::<Effect>::new(4).split();
            let (mut trash_tx, trash_rx) = HeapRb::<Effect>::new(4).split();
            let mut effect = Effect::new(effect, rate);
            let mut dc = DcBlock::new(rate);
            let mut gate = Gate::new(rate);
            let shared = Arc::clone(&shared);
            let on_input = move |mono: &mut [f32], _: &InputCallbackInfo| {
                dc.process(mono);
                let peak = mono.iter().fold(0.0f32, |m, s| m.max(s.abs()));
                shared.mic_peak.raise(peak);
                // Measured even while nothing is sent, so the floor is known
                // when the voice changer comes on.
                let gate_on = shared.gate_on.load(Ordering::Relaxed);
                gate.process(mono, gate_on, shared.gate_margin.get());
                shared.noise_floor.set(gate.floor_db().unwrap_or(f32::NAN));
                // A new effect from the window: swap it in, send the old one back.
                while let Some(new) = effect_rx.try_pop() {
                    let old = std::mem::replace(&mut effect, new);
                    let _ = trash_tx.try_push(old);
                }
                let voice = shared.voice_on.load(Ordering::Relaxed);
                let test = shared.test_on.load(Ordering::Relaxed);
                if !voice && !test {
                    return;
                }
                effect.process(mono);
                for (queue, roles) in voice_queues.iter_mut() {
                    if (roles.voice && voice) || (roles.test && test) {
                        queue.push_slice(mono);
                    }
                }
            };
            let mut config = supported.config();
            config.buffer_size = buffer_size(&supported, rate, routing.block_ms).0;
            match open_input(&device, &supported, config, on_input)
                .and_then(|s| s.play().map(|_| s).map_err(Into::into))
            {
                Ok(stream) => {
                    self.streams.push(stream);
                    self.effect_tx = Some(effect_tx);
                    self.trash_rx = Some(trash_rx);
                    self.mic_rate = Some(rate);
                }
                Err(e) => status
                    .problems
                    .push(format!("Can't open the microphone: {e}")),
            }
        }
        self.status = status;
    }

    /// Switches the voice effect without stopping anything.
    pub fn set_effect(&mut self, args: &EffectArgs) {
        if let (Some(tx), Some(rate)) = (&mut self.effect_tx, self.mic_rate) {
            let _ = tx.try_push(Effect::new(args, rate));
        }
    }

    /// The effect's own delay, in ms.
    pub fn effect_delay_ms(&self, args: &EffectArgs) -> Option<f32> {
        let rate = self.mic_rate?;
        Some(Effect::new(args, rate).algorithmic_latency_ms(rate))
    }

    /// Frees the effects the audio thread is done with (call once per frame).
    pub fn collect_garbage(&mut self) {
        if let Some(rx) = &mut self.trash_rx {
            while rx.try_pop().is_some() {}
        }
    }
}

/// Adds the next block of `slot`'s clip to `mono`, at its own volume times
/// `gain`, and empties the slot once the clip has ended.
fn mix(slot: &mut Option<(Arc<[f32]>, usize, f32)>, mono: &mut [f32], gain: f32) {
    let Some((samples, pos, own)) = slot else {
        return;
    };
    let take = (samples.len() - *pos).min(mono.len());
    for (out, s) in mono.iter_mut().zip(&samples[*pos..*pos + take]) {
        *out += s * *own * gain;
    }
    *pos += take;
    if *pos >= samples.len() {
        *slot = None;
    }
}

fn wanted_has_voice(wanted: &[(String, Device, Roles)]) -> bool {
    wanted.iter().any(|(_, _, r)| r.voice)
}

/// A queue filled on another clock (the mic, a captured program). It
/// waits for a small cushion before playing, so a late block doesn't cause
/// a click, and throws away any surplus to keep the delay low.
struct Cushioned {
    queue: HeapCons<f32>,
    /// The queue has filled up to `cushion` and is being played.
    primed: bool,
    cushion: usize,
    /// How far beyond the cushion it may fill (at least two blocks).
    slack: usize,
}

impl Cushioned {
    fn new(queue: HeapCons<f32>, cushion: usize, slack: usize) -> Cushioned {
        Cushioned {
            queue,
            primed: false,
            cushion,
            slack,
        }
    }

    /// Empties the queue: nothing is to be played from it now.
    fn flush(&mut self) {
        self.queue.skip(self.queue.occupied_len());
        self.primed = false;
    }

    /// Adds the next block, times `gain`, to `mono`. False if it ran dry.
    fn mix_into(&mut self, mono: &mut [f32], gain: f32) -> bool {
        let n = mono.len();
        let fill = self.queue.occupied_len();
        let target = self.cushion + n;
        if !self.primed && fill >= target {
            self.primed = true;
        }
        if !self.primed {
            return true;
        }
        if fill > target + self.slack.max(2 * n) {
            self.queue.skip(fill - target);
        }
        let mut got = 0;
        for (out, s) in mono.iter_mut().zip(self.queue.pop_iter()) {
            *out += s * gain;
            got += 1;
        }
        if got < n {
            self.primed = false;
            return false;
        }
        true
    }
}

/// The audio thread's side of one output stream.
struct OutputState {
    roles: Roles,
    shared: Arc<Shared>,
    commands: HeapCons<OutCmd>,
    /// The clip playing: samples, position, the key's own volume.
    clip: Option<(Arc<[f32]>, usize, f32)>,
    /// The cue playing, the same way.
    cue: Option<(Arc<[f32]>, usize, f32)>,
    voice: Option<Cushioned>,
    /// The captured program, on outputs others hear.
    program: Option<Cushioned>,
    /// This output's level is the "virtual mic" meter.
    peak: bool,
}

impl OutputState {
    fn fill(&mut self, mono: &mut [f32]) {
        mono.fill(0.0);
        while let Some(cmd) = self.commands.try_pop() {
            match cmd {
                OutCmd::Play { samples, gain } => self.clip = Some((samples, 0, gain)),
                OutCmd::Stop => self.clip = None,
                OutCmd::Cue { samples, gain } => self.cue = Some((samples, 0, gain)),
            }
        }
        let headset = self.shared.headset_volume.get();

        // The sound clip. The volumes are read every block, so ↑/↓ act at once.
        let mut g = self.shared.sound_volume.get();
        if self.roles.monitor && !self.roles.sound {
            g *= headset;
        }
        mix(&mut self.clip, mono, g);
        mix(&mut self.cue, mono, headset);

        if let Some(queue) = &mut self.voice {
            let voice = self.shared.voice_on.load(Ordering::Relaxed);
            let test = self.shared.test_on.load(Ordering::Relaxed);
            if !((self.roles.voice && voice) || (self.roles.test && test)) {
                queue.flush();
            } else {
                let g = if self.roles.voice { 1.0 } else { headset };
                if !queue.mix_into(mono, g) {
                    self.shared.underruns.fetch_add(1, Ordering::Relaxed);
                }
            }
        }

        // The captured program. Its queue stays empty while nothing is captured.
        if let Some(queue) = &mut self.program {
            queue.mix_into(mono, self.shared.program_volume.get());
        }

        if self.peak {
            let peak = mono.iter().fold(0.0f32, |m, s| m.max(s.abs()));
            self.shared.virtual_peak.raise(peak);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn output(
        roles: Roles,
        shared: &Arc<Shared>,
    ) -> (OutputState, HeapProd<OutCmd>, HeapProd<f32>) {
        let (cmd_tx, cmd_rx) = HeapRb::<OutCmd>::new(4).split();
        let (voice_tx, voice_rx) = HeapRb::<f32>::new(4096).split();
        let state = OutputState {
            roles,
            shared: Arc::clone(shared),
            commands: cmd_rx,
            clip: None,
            cue: None,
            voice: Some(Cushioned::new(voice_rx, 10, 0)),
            program: None,
            peak: true,
        };
        (state, cmd_tx, voice_tx)
    }

    #[test]
    fn clip_follows_the_volumes_and_ends() {
        let shared = Shared::new();
        shared.sound_volume.set(0.5);
        shared.headset_volume.set(0.5);
        let roles = Roles {
            monitor: true,
            ..Roles::default()
        };
        let (mut out, mut cmds, _) = output(roles, &shared);
        let _ = cmds.try_push(OutCmd::Play {
            samples: vec![1.0; 6].into(),
            gain: 1.0,
        });
        let mut block = [0.0f32; 4];
        out.fill(&mut block);
        assert_eq!(block, [0.25; 4]); // sound volume × headset volume
        shared.sound_volume.set(1.0); // ↑ while playing
        out.fill(&mut block);
        assert_eq!(block, [0.5, 0.5, 0.0, 0.0]);
        assert!(out.clip.is_none());
    }

    #[test]
    fn voice_only_flows_when_switched_on() {
        let shared = Shared::new();
        let roles = Roles {
            voice: true,
            ..Roles::default()
        };
        let (mut out, _, mut voice) = output(roles, &shared);
        let mut block = [0.0f32; 8];
        voice.push_slice(&[0.5; 64]);
        out.fill(&mut block);
        assert_eq!(
            block, [0.0; 8],
            "voice off: nothing, and the queue is emptied"
        );
        assert_eq!(voice.occupied_len(), 0);

        shared.voice_on.store(true, Ordering::Relaxed);
        voice.push_slice(&[0.5; 12]); // below cushion + block: wait
        out.fill(&mut block);
        assert_eq!(block, [0.0; 8]);
        voice.push_slice(&[0.5; 12]);
        out.fill(&mut block);
        assert_eq!(block, [0.5; 8]);
    }

    #[test]
    fn a_captured_program_plays_at_its_own_volume_with_the_voice_off() {
        let shared = Shared::new();
        shared.program_volume.set(0.5);
        let roles = Roles {
            sound: true,
            ..Roles::default()
        };
        let (mut out, _, _) = output(roles, &shared);
        let (mut program, rx) = HeapRb::<f32>::new(4096).split();
        out.program = Some(Cushioned::new(rx, 10, 40));
        let mut block = [0.0f32; 8];
        program.push_slice(&[0.8; 12]); // below cushion + block: wait
        out.fill(&mut block);
        assert_eq!(block, [0.0; 8]);
        program.push_slice(&[0.8; 40]);
        out.fill(&mut block);
        assert_eq!(block, [0.4; 8]);
        // A surplus within the slack is kept (the capture's blocks are big)...
        assert_eq!(program.occupied_len(), 52 - 8);
        // ...beyond it, the queue goes back to the cushion.
        program.push_slice(&[0.8; 60]);
        out.fill(&mut block);
        assert_eq!(program.occupied_len(), 10);
    }

    #[test]
    fn test_voice_uses_the_headset_volume() {
        let shared = Shared::new();
        shared.headset_volume.set(0.5);
        shared.test_on.store(true, Ordering::Relaxed);
        let roles = Roles {
            monitor: true,
            test: true,
            ..Roles::default()
        };
        let (mut out, _, mut voice) = output(roles, &shared);
        voice.push_slice(&[1.0; 64]);
        let mut block = [0.0f32; 8];
        out.fill(&mut block);
        assert_eq!(block, [0.5; 8]);
        assert!((shared.take_peaks().1 - 0.5).abs() < 1e-6);
    }
}
