//! Another program's sound (Spotify, a browser, a video player...) sent to
//! the virtual mic, so others hear it too. You keep hearing the program as
//! usual: Intercom takes a copy, it doesn't move the program's sound, so
//! nothing is heard twice.
//!
//! - Linux (PipeWire): Intercom creates a speaker that plays nowhere,
//!   "Intercom Apps", and links the program's sound to it too (`pw-link`),
//!   next to its usual speaker. Intercom records that speaker's monitor. A
//!   browser opens a new stream for each video, so the links are checked
//!   again whenever a stream appears (`pactl subscribe`), and every second.
//! - Windows (10 version 2004 or later): the system records one program's
//!   sound by itself ("process loopback"), with its child processes, which
//!   is where browsers and Spotify play their sound.
//!
//! A thread lists the programs playing sound every second and keeps the
//! capture going; the window reads its list and tells it what to capture.
//! The captured sound goes into the engine's `ProgramTap`.

use crate::audio::Shared;
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender, channel};
use std::sync::{Arc, Mutex};
use std::time::Duration;

/// A program playing sound.
#[derive(Clone, Debug, PartialEq)]
pub struct Program {
    /// What identifies it: its executable's name.
    pub key: String,
    /// The name shown, e.g. "Firefox".
    pub name: String,
}

enum Msg {
    Capture(Option<String>),
    /// Something changed: look again now.
    Nudge,
    Quit,
}

/// What the thread tells the window.
#[derive(Default, PartialEq)]
struct Report {
    programs: Vec<Program>,
    /// Why the capture doesn't work, if it doesn't.
    problem: Option<String>,
}

pub struct Programs {
    report: Arc<Mutex<Report>>,
    tx: Sender<Msg>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl Programs {
    /// Starts the thread. `repaint` is called when the list or a problem changes.
    pub fn start(shared: Arc<Shared>, repaint: impl Fn() + Send + 'static) -> Programs {
        let report = Arc::new(Mutex::new(Report::default()));
        let (tx, rx) = channel();
        let thread = {
            let report = Arc::clone(&report);
            let nudge = tx.clone();
            std::thread::Builder::new()
                .name("programs".into())
                .spawn(move || run(&shared, &report, &rx, nudge, repaint))
                .ok()
        };
        Programs { report, tx, thread }
    }

    /// The programs playing sound now, by name.
    pub fn list(&self) -> Vec<Program> {
        self.report.lock().unwrap().programs.clone()
    }

    pub fn problem(&self) -> Option<String> {
        self.report.lock().unwrap().problem.clone()
    }

    /// Captures the program with this key (`Program::key`), or nothing.
    pub fn capture(&self, key: Option<String>) {
        let _ = self.tx.send(Msg::Capture(key));
    }

    /// Asks the thread to look again now (the engine restarted, maybe at a new rate).
    pub fn nudge(&self) {
        let _ = self.tx.send(Msg::Nudge);
    }

    /// Stops capturing and removes what Intercom created, and waits for it.
    pub fn close(&mut self) {
        let _ = self.tx.send(Msg::Quit);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

impl Drop for Programs {
    fn drop(&mut self) {
        self.close();
    }
}

fn run(
    shared: &Arc<Shared>,
    report: &Mutex<Report>,
    rx: &Receiver<Msg>,
    nudge: Sender<Msg>,
    repaint: impl Fn(),
) {
    let mut source = Source::new(move || {
        let _ = nudge.send(Msg::Nudge);
    });
    let mut target: Option<String> = None;
    loop {
        let mut programs = source.scan();
        programs.sort_by_key(|p| p.name.to_lowercase());
        let problem = source.keep(target.as_deref(), shared).err();
        let now = Report { programs, problem };
        let changed = {
            let mut last = report.lock().unwrap();
            let changed = *last != now;
            *last = now;
            changed
        };
        if changed {
            repaint();
        }
        let mut next = rx.recv_timeout(Duration::from_secs(1));
        // Several messages at once: the last target counts, nudges add nothing.
        loop {
            match next {
                Ok(Msg::Capture(key)) => target = key,
                Ok(Msg::Nudge) | Err(RecvTimeoutError::Timeout) => {}
                Ok(Msg::Quit) | Err(RecvTimeoutError::Disconnected) => {
                    source.stop();
                    return;
                }
            }
            match rx.try_recv() {
                Ok(msg) => next = Ok(msg),
                Err(_) => break,
            }
        }
    }
}

/// Voice chats are never offered: your friends would hear themselves.
const VOICE_CHATS: [&str; 5] = ["discord", "vesktop", "webcord", "legcord", "armcord"];

/// Whether a program can be captured: not Intercom itself, not a voice chat.
fn offered(key: &str, name: &str, pid: Option<u32>) -> bool {
    if pid == Some(std::process::id()) || key.is_empty() {
        return false;
    }
    let (key, name) = (key.to_lowercase(), name.to_lowercase());
    !VOICE_CHATS
        .iter()
        .any(|chat| key.contains(chat) || name.contains(chat))
}

/// Whether Discord (or a Discord app like Vesktop) has been used on this
/// computer: its settings folder exists, however it was installed.
pub fn discord_installed() -> bool {
    let Some(dirs) = directories::BaseDirs::new() else {
        return false;
    };
    let mut places = vec![
        dirs.config_dir().join("discord"),
        dirs.config_dir().join("vesktop"),
        dirs.data_local_dir().join("Discord"),
    ];
    if cfg!(target_os = "linux") {
        let flatpaks = dirs.home_dir().join(".var").join("app");
        places.push(flatpaks.join("com.discordapp.Discord"));
        places.push(flatpaks.join("dev.vencord.Vesktop"));
    }
    places.iter().any(|p| p.is_dir())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn intercom_and_voice_chats_are_never_offered() {
        assert!(offered("spotify", "Spotify", Some(1)));
        assert!(!offered("Discord", "Discord", Some(1)));
        assert!(!offered("electron", "Vesktop", Some(1)));
        assert!(!offered("intercom", "intercom", Some(std::process::id())));
        assert!(!offered("", "", Some(1)));
    }

    #[cfg(target_os = "linux")]
    #[test]
    #[ignore = "needs PipeWire; plays into silent speakers it creates"]
    fn captures_a_playing_program_into_the_engine() {
        use crate::audio::{Engine, Routing, host};
        use crate::virtual_mic::pactl;
        use std::io::Write;
        let sink = |name: &str, desc: &str| -> u32 {
            pactl(&[
                "load-module",
                "module-null-sink",
                &format!("sink_name={name}"),
                &format!("sink_properties='device.description=\"{desc}\"'"),
            ])
            .unwrap()
            .parse()
            .unwrap()
        };
        let play = sink("intercom_test_play", "Intercom Test Play");
        let out = sink("intercom_test_out", "Intercom Test Out");
        let mut pacat = std::process::Command::new("pacat")
            .args([
                "--playback",
                "--device=intercom_test_play",
                "--rate=48000",
                "--channels=2",
                "--format=s16le",
            ])
            .stdin(std::process::Stdio::piped())
            .spawn()
            .unwrap();
        let mut stdin = pacat.stdin.take().unwrap();
        std::thread::spawn(move || {
            let mut t = 0u64;
            loop {
                let mut buf = Vec::with_capacity(4800 * 4);
                for _ in 0..4800 {
                    let s = ((t as f32 * 440.0 * std::f32::consts::TAU / 48000.0).sin() * 16000.0)
                        as i16;
                    buf.extend_from_slice(&s.to_le_bytes());
                    buf.extend_from_slice(&s.to_le_bytes());
                    t += 1;
                }
                if stdin.write_all(&buf).is_err() {
                    return;
                }
            }
        });

        let host = host();
        let shared = Shared::new();
        let mut engine = Engine::new(Arc::clone(&shared));
        let routing = Routing {
            mic: None,
            voice_out: Some("Intercom Test Out".into()),
            sound_out: Some("Intercom Test Out".into()),
            headset: Some("Intercom Test Out".into()),
            test_out: None,
            block_ms: 10,
        };
        engine.start(
            &host,
            &routing,
            &crate::config::VoiceConfig::default().effect_args(),
        );
        let mut programs = Programs::start(Arc::clone(&shared), || {});
        let mut found = false;
        for _ in 0..50 {
            if programs.list().iter().any(|p| p.key == "pacat") {
                found = true;
                break;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let mut peak = 0.0;
        if found {
            programs.capture(Some("pacat".into()));
            std::thread::sleep(Duration::from_millis(2500));
            shared.take_peaks();
            std::thread::sleep(Duration::from_millis(300));
            peak = shared.take_peaks().1;
        }
        let problem = programs.problem();
        programs.close();
        let apps_gone = !pactl(&["list", "short", "sinks"])
            .unwrap()
            .contains("intercom_apps");
        engine.stop();
        let _ = pacat.kill();
        let _ = pacat.wait();
        let _ = pactl(&["unload-module", &out.to_string()]);
        let _ = pactl(&["unload-module", &play.to_string()]);
        assert!(found, "pacat not listed");
        assert_eq!(problem, None);
        // A 0.49 sine at the default 50 % program volume.
        assert!((peak - 0.245).abs() < 0.03, "peak {peak}");
        assert!(apps_gone, "the capture speaker was left behind");
    }
}

#[cfg(target_os = "linux")]
use linux::Source;
#[cfg(windows)]
use windows::Source;

/// Elsewhere: no program can be captured.
#[cfg(not(any(target_os = "linux", windows)))]
struct Source;
#[cfg(not(any(target_os = "linux", windows)))]
impl Source {
    fn new(_nudge: impl Fn() + Send + 'static) -> Source {
        Source
    }
    fn scan(&mut self) -> Vec<Program> {
        Vec::new()
    }
    fn keep(&mut self, target: Option<&str>, _shared: &Arc<Shared>) -> Result<(), String> {
        match target {
            Some(_) => Err("Not supported on this system".into()),
            None => Ok(()),
        }
    }
    fn stop(&mut self) {}
}

#[cfg(target_os = "linux")]
mod linux {
    use super::{Program, offered};
    use crate::audio::Shared;
    use crate::virtual_mic::pactl;
    use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
    use serde_json::Value;
    use std::collections::{HashMap, HashSet};
    use std::io::{BufRead, BufReader};
    use std::process::{Child, Command, Stdio};
    use std::sync::Arc;

    const SINK_NAME: &str = "intercom_apps";
    const SINK_DESCRIPTION: &str = "Intercom Apps";

    /// One stream a program plays.
    struct Playing {
        /// The sink-input's index, which is also its PipeWire node's serial.
        index: u64,
        key: String,
    }

    /// The speaker Intercom links the program to, and the recording of it.
    struct Capture {
        module: u32,
        rate: u32,
        _stream: cpal::Stream,
    }

    pub struct Source {
        /// `pactl subscribe`, which nudges the thread when a stream appears.
        subscribe: Option<Child>,
        playing: Vec<Playing>,
        capture: Option<Capture>,
        /// Why the capture couldn't start, at this rate: not retried every second.
        failed: Option<(u32, String)>,
    }

    impl Source {
        pub fn new(nudge: impl Fn() + Send + 'static) -> Source {
            remove_leftovers();
            Source {
                subscribe: subscribe(nudge),
                playing: Vec::new(),
                capture: None,
                failed: None,
            }
        }

        pub fn scan(&mut self) -> Vec<Program> {
            let Ok(text) = pactl(&["-f", "json", "list", "sink-inputs"]) else {
                self.playing.clear();
                return Vec::new();
            };
            let inputs: Vec<Value> = serde_json::from_str(&text).unwrap_or_default();
            let mut programs: Vec<Program> = Vec::new();
            self.playing.clear();
            for input in &inputs {
                let props = &input["properties"];
                let prop = |name: &str| props[name].as_str().unwrap_or("").to_string();
                let mut key = prop("application.process.binary");
                let mut name = prop("application.name");
                if key.is_empty() {
                    key = name.clone();
                }
                if name.is_empty() {
                    name = key.clone();
                }
                let pid = prop("application.process.id").parse().ok();
                let Some(index) = input["index"].as_u64() else {
                    continue;
                };
                if !offered(&key, &name, pid) {
                    continue;
                }
                if !programs.iter().any(|p| p.key == key) {
                    programs.push(Program {
                        key: key.clone(),
                        name,
                    });
                }
                self.playing.push(Playing { index, key });
            }
            programs
        }

        pub fn keep(&mut self, target: Option<&str>, shared: &Arc<Shared>) -> Result<(), String> {
            let rate = shared.program.rate();
            let Some(target) = target.filter(|_| rate > 0) else {
                self.stop();
                self.failed = None;
                return Ok(());
            };
            if self.capture.as_ref().is_some_and(|c| c.rate != rate) {
                self.stop();
            }
            if self.capture.is_none() {
                if let Some((r, why)) = &self.failed
                    && *r == rate
                {
                    return Err(why.clone());
                }
                match start(rate, shared) {
                    Ok(capture) => self.capture = Some(capture),
                    Err(why) => {
                        self.failed = Some((rate, why.clone()));
                        return Err(why);
                    }
                }
            }
            let streams: HashSet<u64> = self
                .playing
                .iter()
                .filter(|p| p.key == target)
                .map(|p| p.index)
                .collect();
            if streams.is_empty() {
                return Ok(());
            }
            link(&streams)
        }

        pub fn stop(&mut self) {
            if let Some(capture) = self.capture.take() {
                // The recording first, then the speaker under it.
                let module = capture.module;
                drop(capture);
                let _ = pactl(&["unload-module", &module.to_string()]);
            }
        }
    }

    impl Drop for Source {
        fn drop(&mut self) {
            self.stop();
            if let Some(mut child) = self.subscribe.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }

    /// Runs `pactl subscribe`, and nudges whenever a stream comes or changes.
    fn subscribe(nudge: impl Fn() + Send + 'static) -> Option<Child> {
        let mut child = Command::new("pactl")
            .arg("subscribe")
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .ok()?;
        let out = child.stdout.take()?;
        let _ = std::thread::Builder::new()
            .name("pactl subscribe".into())
            .spawn(move || {
                for line in BufReader::new(out).lines().map_while(Result::ok) {
                    if line.contains("sink-input") && !line.contains("'remove'") {
                        nudge();
                    }
                }
            });
        Some(child)
    }

    /// The speakers of an earlier run that crashed.
    fn remove_leftovers() {
        let Ok(modules) = pactl(&["list", "short", "modules"]) else {
            return;
        };
        for line in modules.lines() {
            let mut parts = line.split('\t');
            let id = parts.next().unwrap_or("").trim();
            let _module = parts.next();
            if parts
                .next()
                .is_some_and(|args| args.contains(&format!("sink_name={SINK_NAME}")))
            {
                let _ = pactl(&["unload-module", id]);
            }
        }
    }

    /// Creates the speaker and records its monitor into the engine.
    fn start(rate: u32, shared: &Arc<Shared>) -> Result<Capture, String> {
        let module: u32 = pactl(&[
            "load-module",
            "module-null-sink",
            &format!("sink_name={SINK_NAME}"),
            &format!("rate={rate}"),
            &format!("sink_properties='device.description=\"{SINK_DESCRIPTION}\"'"),
        ])?
        .parse()
        .map_err(|_| "pactl returned no module number".to_string())?;
        match record(rate, shared) {
            Ok(stream) => Ok(Capture {
                module,
                rate,
                _stream: stream,
            }),
            Err(e) => {
                let _ = pactl(&["unload-module", &module.to_string()]);
                Err(e)
            }
        }
    }

    fn record(rate: u32, shared: &Arc<Shared>) -> Result<cpal::Stream, String> {
        let host = crate::audio::host();
        let monitor = format!("{SINK_NAME}.monitor");
        let device = host
            .input_devices()
            .map_err(|e| e.to_string())?
            .find(|d| d.id().is_ok_and(|id| id.id() == monitor))
            .ok_or("Intercom's capture speaker didn't appear")?;
        let supported = device.default_input_config().map_err(|e| e.to_string())?;
        if supported.sample_rate() != rate {
            return Err(format!(
                "the capture runs at {} Hz, not {rate} Hz",
                supported.sample_rate()
            ));
        }
        let mut config = supported.config();
        config.buffer_size = crate::audio::buffer_size(&supported, rate, 10).0;
        let shared = Arc::clone(shared);
        let stream = voice_changer::devices::open_input(
            &device,
            &supported,
            config,
            move |mono: &mut [f32], _: &cpal::InputCallbackInfo| shared.program.push(mono),
        )
        .map_err(|e| e.to_string())?;
        stream.play().map_err(|e| e.to_string())?;
        Ok(stream)
    }

    /// Links each of `streams` (PipeWire node serials) to Intercom's speaker
    /// as well, where it isn't yet: left to left, right to right, mono to both.
    fn link(streams: &HashSet<u64>) -> Result<(), String> {
        let out = Command::new("pw-dump").output().map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                "pw-dump is missing: capturing a program needs PipeWire (Debian/Ubuntu: sudo apt install pipewire-bin)".to_string()
            } else {
                format!("pw-dump: {e}")
            }
        })?;
        let objects: Vec<Value> = serde_json::from_slice(&out.stdout)
            .map_err(|_| "pw-dump printed something unexpected".to_string())?;
        let props = |o: &Value| o["info"]["props"].clone();
        let of_type = |t: &'static str| {
            objects
                .iter()
                .filter(move |o| o["type"].as_str() == Some(t))
        };

        let mut sink = None;
        let mut sources: HashSet<u64> = HashSet::new();
        for node in of_type("PipeWire:Interface:Node") {
            let p = props(node);
            let id = node["id"].as_u64();
            if p["node.name"].as_str() == Some(SINK_NAME) {
                sink = id;
            } else if p["object.serial"]
                .as_u64()
                .is_some_and(|s| streams.contains(&s))
            {
                sources.extend(id);
            }
        }
        let sink = sink.ok_or("Intercom's capture speaker is gone")?;

        // The speaker's inputs by channel, and the programs' outputs.
        let mut inputs: HashMap<String, u64> = HashMap::new();
        let mut outputs: Vec<(u64, String)> = Vec::new();
        for port in of_type("PipeWire:Interface:Port") {
            let p = props(port);
            let (Some(id), Some(node)) = (port["id"].as_u64(), p["node.id"].as_u64()) else {
                continue;
            };
            let channel = p["audio.channel"].as_str().unwrap_or("MONO").to_string();
            let direction = port["info"]["direction"].as_str();
            if node == sink && direction == Some("input") {
                inputs.insert(channel, id);
            } else if sources.contains(&node) && direction == Some("output") {
                outputs.push((id, channel));
            }
        }
        let linked: HashSet<(u64, u64)> = of_type("PipeWire:Interface:Link")
            .filter_map(|l| {
                let i = &l["info"];
                Some((i["output-port-id"].as_u64()?, i["input-port-id"].as_u64()?))
            })
            .collect();

        for (out_port, channel) in outputs {
            let targets: Vec<u64> = match inputs.get(&channel) {
                Some(&port) => vec![port],
                // Mono, or a channel the speaker doesn't have (centre, rear...):
                // to both sides. The bass channel adds nothing to a voice chat.
                None if channel == "LFE" => Vec::new(),
                None => inputs.values().copied().collect(),
            };
            for in_port in targets {
                if !linked.contains(&(out_port, in_port)) {
                    pw_link(out_port, in_port)?;
                }
            }
        }
        Ok(())
    }

    fn pw_link(out_port: u64, in_port: u64) -> Result<(), String> {
        let out = Command::new("pw-link")
            .args([out_port.to_string(), in_port.to_string()])
            .output()
            .map_err(|e| {
                if e.kind() == std::io::ErrorKind::NotFound {
                    "pw-link is missing: capturing a program needs PipeWire (Debian/Ubuntu: sudo apt install pipewire-bin)".to_string()
                } else {
                    format!("pw-link: {e}")
                }
            })?;
        let error = String::from_utf8_lossy(&out.stderr);
        // A stream that just ended, or a link made meanwhile: not a problem.
        if out.status.success() || error.contains("exists") || error.contains("No such") {
            Ok(())
        } else {
            Err(format!("pw-link: {}", error.trim()))
        }
    }
}

#[cfg(windows)]
mod windows {
    use super::{Program, offered};
    use crate::audio::Shared;
    use std::collections::HashMap;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::sync::mpsc;
    use std::sync::{Arc, Mutex};
    use std::thread::JoinHandle;
    use std::time::Duration;
    use windows::Win32::Foundation::{CloseHandle, WAIT_OBJECT_0};
    use windows::Win32::Media::Audio::{
        AUDCLNT_BUFFERFLAGS_SILENT, AUDCLNT_SHAREMODE_SHARED, AUDCLNT_STREAMFLAGS_EVENTCALLBACK,
        AUDCLNT_STREAMFLAGS_LOOPBACK, AUDIOCLIENT_ACTIVATION_PARAMS,
        AUDIOCLIENT_ACTIVATION_PARAMS_0, AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
        AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS, ActivateAudioInterfaceAsync, AudioSessionStateExpired,
        DEVICE_STATE_ACTIVE, IActivateAudioInterfaceAsyncOperation,
        IActivateAudioInterfaceCompletionHandler, IActivateAudioInterfaceCompletionHandler_Impl,
        IAudioCaptureClient, IAudioClient, IAudioSessionControl2, IAudioSessionManager2,
        IMMDeviceEnumerator, MMDeviceEnumerator, PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE,
        VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK, WAVEFORMATEX, eRender,
    };
    use windows::Win32::System::Com::StructuredStorage::{
        PROPVARIANT, PROPVARIANT_0, PROPVARIANT_0_0, PROPVARIANT_0_0_0,
    };
    use windows::Win32::System::Com::{
        BLOB, CLSCTX_ALL, COINIT_MULTITHREADED, CoCreateInstance, CoInitializeEx,
    };
    use windows::Win32::System::Diagnostics::ToolHelp::{
        CreateToolhelp32Snapshot, PROCESSENTRY32W, Process32FirstW, Process32NextW,
        TH32CS_SNAPPROCESS,
    };
    use windows::Win32::System::Threading::{CreateEventW, WaitForSingleObject};
    use windows::Win32::System::Variant::VT_BLOB;
    use windows::core::{HRESULT, IUnknown, Interface, Ref, implement};

    const WAVE_FORMAT_PCM: u16 = 1;
    const WAVE_FORMAT_IEEE_FLOAT: u16 = 3;

    /// The recording thread of one program.
    struct Capture {
        key: String,
        pid: u32,
        rate: u32,
        stop: Arc<AtomicBool>,
        thread: JoinHandle<()>,
        /// Why it stopped, when it stopped by itself.
        failed: Arc<Mutex<Option<String>>>,
    }

    pub struct Source {
        /// Each program playing sound, with the process to record.
        playing: Vec<(Program, u32)>,
        capture: Option<Capture>,
        /// The last capture that failed: (pid, rate, why), not retried every second.
        failed: Option<(u32, u32, String)>,
    }

    impl Source {
        pub fn new(_nudge: impl Fn() + Send + 'static) -> Source {
            unsafe {
                let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
            }
            Source {
                playing: Vec::new(),
                capture: None,
                failed: None,
            }
        }

        pub fn scan(&mut self) -> Vec<Program> {
            let processes = processes();
            self.playing.clear();
            for pid in session_pids() {
                let Some((_, exe)) = processes.get(&pid) else {
                    continue;
                };
                let key = exe.to_lowercase();
                let name = display_name(exe);
                if !offered(&key, &name, Some(pid))
                    || self.playing.iter().any(|(p, _)| p.key == key)
                {
                    continue;
                }
                self.playing
                    .push((Program { key, name }, root(pid, &processes)));
            }
            self.playing.iter().map(|(p, _)| p.clone()).collect()
        }

        pub fn keep(&mut self, target: Option<&str>, shared: &Arc<Shared>) -> Result<(), String> {
            let rate = shared.program.rate();
            let Some(key) = target.filter(|_| rate > 0) else {
                self.stop();
                return Ok(());
            };
            if self.capture.as_ref().is_some_and(|c| c.key != key) {
                self.stop();
            }
            let pid = self
                .playing
                .iter()
                .find(|(p, _)| p.key == key)
                .map(|(_, pid)| *pid);
            // Not playing now: a running capture goes on, the program may
            // only be between two songs.
            let Some(pid) = pid else {
                return self.capture_problem();
            };
            if let Some(c) = &self.capture
                && (c.pid != pid || c.rate != rate || c.thread.is_finished())
            {
                if c.thread.is_finished() {
                    let why = c.failed.lock().unwrap().clone();
                    self.failed = why.map(|why| (c.pid, c.rate, why));
                }
                self.stop();
            }
            if let Some((p, r, why)) = &self.failed {
                if *p == pid && *r == rate {
                    return Err(why.clone());
                }
                self.failed = None;
            }
            if self.capture.is_none() {
                self.capture = Some(start(key, pid, rate, shared));
            }
            self.capture_problem()
        }

        fn capture_problem(&self) -> Result<(), String> {
            match self
                .capture
                .as_ref()
                .and_then(|c| c.failed.lock().unwrap().clone())
            {
                Some(why) => Err(why),
                None => Ok(()),
            }
        }

        pub fn stop(&mut self) {
            if let Some(capture) = self.capture.take() {
                capture.stop.store(true, Ordering::Relaxed);
                let _ = capture.thread.join();
            }
        }
    }

    impl Drop for Source {
        fn drop(&mut self) {
            self.stop();
        }
    }

    /// "spotify.exe" → "Spotify".
    fn display_name(exe: &str) -> String {
        let stem = exe
            .rsplit_once('.')
            .map_or(exe, |(stem, _)| stem)
            .to_string();
        let mut chars = stem.chars();
        match chars.next() {
            Some(first) => first.to_uppercase().chain(chars).collect(),
            None => stem,
        }
    }

    /// Every process: its parent and its executable's name.
    fn processes() -> HashMap<u32, (u32, String)> {
        let mut all = HashMap::new();
        unsafe {
            let Ok(snapshot) = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0) else {
                return all;
            };
            let mut entry = PROCESSENTRY32W {
                dwSize: std::mem::size_of::<PROCESSENTRY32W>() as u32,
                ..Default::default()
            };
            let mut more = Process32FirstW(snapshot, &mut entry).is_ok();
            while more {
                let len = entry
                    .szExeFile
                    .iter()
                    .position(|&c| c == 0)
                    .unwrap_or(entry.szExeFile.len());
                let exe = String::from_utf16_lossy(&entry.szExeFile[..len]);
                all.insert(entry.th32ProcessID, (entry.th32ParentProcessID, exe));
                more = Process32NextW(snapshot, &mut entry).is_ok();
            }
            let _ = CloseHandle(snapshot);
        }
        all
    }

    /// The topmost process of the same program: Firefox and Spotify play
    /// from a child process, and recording the top one includes them all.
    fn root(pid: u32, processes: &HashMap<u32, (u32, String)>) -> u32 {
        let mut pid = pid;
        for _ in 0..32 {
            let Some((parent, exe)) = processes.get(&pid) else {
                break;
            };
            match processes.get(parent) {
                Some((_, parent_exe)) if parent_exe.eq_ignore_ascii_case(exe) && *parent != pid => {
                    pid = *parent
                }
                _ => break,
            }
        }
        pid
    }

    /// The processes with a sound session on any speaker, like the volume mixer shows.
    fn session_pids() -> Vec<u32> {
        let mut pids = Vec::new();
        unsafe {
            let Ok(devices) =
                CoCreateInstance::<_, IMMDeviceEnumerator>(&MMDeviceEnumerator, None, CLSCTX_ALL)
                    .and_then(|e| e.EnumAudioEndpoints(eRender, DEVICE_STATE_ACTIVE))
            else {
                return pids;
            };
            for i in 0..devices.GetCount().unwrap_or(0) {
                let Ok(manager) = devices
                    .Item(i)
                    .and_then(|d| d.Activate::<IAudioSessionManager2>(CLSCTX_ALL, None))
                else {
                    continue;
                };
                let Ok(sessions) = manager.GetSessionEnumerator() else {
                    continue;
                };
                for j in 0..sessions.GetCount().unwrap_or(0) {
                    let Ok(session) = sessions
                        .GetSession(j)
                        .and_then(|s| s.cast::<IAudioSessionControl2>())
                    else {
                        continue;
                    };
                    // S_OK (0) means "this is the system sounds", S_FALSE (1) it isn't.
                    let system = session.IsSystemSoundsSession() == HRESULT(0);
                    let expired = session
                        .GetState()
                        .is_ok_and(|s| s == AudioSessionStateExpired);
                    if let Ok(pid) = session.GetProcessId()
                        && pid != 0
                        && !system
                        && !expired
                        && !pids.contains(&pid)
                    {
                        pids.push(pid);
                    }
                }
            }
        }
        pids
    }

    fn start(key: &str, pid: u32, rate: u32, shared: &Arc<Shared>) -> Capture {
        let stop = Arc::new(AtomicBool::new(false));
        let failed = Arc::new(Mutex::new(None));
        let thread = {
            let (stop, failed, shared) =
                (Arc::clone(&stop), Arc::clone(&failed), Arc::clone(shared));
            std::thread::Builder::new()
                .name("program capture".into())
                .spawn(move || {
                    if let Err(e) = record(pid, rate, &shared, &stop) {
                        *failed.lock().unwrap() = Some(e);
                    }
                })
                .expect("can't start a thread")
        };
        Capture {
            key: key.to_string(),
            pid,
            rate,
            stop,
            thread,
            failed,
        }
    }

    /// Tells the waiting thread that the system finished opening the recording.
    #[implement(IActivateAudioInterfaceCompletionHandler)]
    struct Opened(mpsc::Sender<()>);

    impl IActivateAudioInterfaceCompletionHandler_Impl for Opened_Impl {
        fn ActivateCompleted(
            &self,
            _operation: Ref<IActivateAudioInterfaceAsyncOperation>,
        ) -> windows::core::Result<()> {
            let _ = self.0.send(());
            Ok(())
        }
    }

    fn failed(what: &str) -> impl Fn(windows::core::Error) -> String + '_ {
        move |e| format!("Can't capture the program ({what}): {}", e.message())
    }

    /// Records `pid` and its children until `stop`, into the engine.
    fn record(pid: u32, rate: u32, shared: &Shared, stop: &AtomicBool) -> Result<(), String> {
        unsafe {
            let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
            // Float if the system takes it, else 16-bit like Microsoft's
            // example. A failed Initialize leaves the client unusable, so the
            // second try opens a new one.
            let client = open(pid)?;
            if initialize(&client, &format(WAVE_FORMAT_IEEE_FLOAT, 32, rate)).is_ok() {
                return record_started(client, true, shared, stop);
            }
            let client = open(pid)?;
            initialize(&client, &format(WAVE_FORMAT_PCM, 16, rate)).map_err(failed("format"))?;
            record_started(client, false, shared, stop)
        }
    }

    /// Shared mode, woken by an event, with 20 ms of buffer (in 100 ns steps).
    unsafe fn initialize(
        client: &IAudioClient,
        format: &WAVEFORMATEX,
    ) -> windows::core::Result<()> {
        let flags = AUDCLNT_STREAMFLAGS_LOOPBACK | AUDCLNT_STREAMFLAGS_EVENTCALLBACK;
        unsafe { client.Initialize(AUDCLNT_SHAREMODE_SHARED, flags, 200_000, 0, format, None) }
    }

    unsafe fn record_started(
        client: IAudioClient,
        is_float: bool,
        shared: &Shared,
        stop: &AtomicBool,
    ) -> Result<(), String> {
        unsafe {
            let event = CreateEventW(None, false, false, None).map_err(failed("event"))?;
            let result = (|| {
                client.SetEventHandle(event).map_err(failed("event"))?;
                let capture: IAudioCaptureClient =
                    client.GetService().map_err(failed("service"))?;
                client.Start().map_err(failed("start"))?;
                let mut mono: Vec<f32> = Vec::with_capacity(4096);
                while !stop.load(Ordering::Relaxed) {
                    if WaitForSingleObject(event, 200) != WAIT_OBJECT_0 {
                        continue;
                    }
                    while capture.GetNextPacketSize().unwrap_or(0) > 0 {
                        let mut data = std::ptr::null_mut();
                        let mut frames = 0u32;
                        let mut flags = 0u32;
                        if capture
                            .GetBuffer(&mut data, &mut frames, &mut flags, None, None)
                            .is_err()
                        {
                            break;
                        }
                        let n = frames as usize;
                        mono.clear();
                        if flags & AUDCLNT_BUFFERFLAGS_SILENT.0 as u32 != 0 || data.is_null() {
                            mono.resize(n, 0.0);
                        } else if is_float {
                            let s = std::slice::from_raw_parts(data as *const f32, n * 2);
                            mono.extend(s.chunks(2).map(|f| (f[0] + f[1]) * 0.5));
                        } else {
                            let s = std::slice::from_raw_parts(data as *const i16, n * 2);
                            mono.extend(
                                s.chunks(2)
                                    .map(|f| (f[0] as f32 + f[1] as f32) / (2.0 * 32768.0)),
                            );
                        }
                        let _ = capture.ReleaseBuffer(frames);
                        shared.program.push(&mono);
                    }
                }
                let _ = client.Stop();
                Ok(())
            })();
            let _ = CloseHandle(event);
            result
        }
    }

    /// Stereo at `rate`.
    fn format(tag: u16, bits: u16, rate: u32) -> WAVEFORMATEX {
        let align = 2 * bits / 8;
        WAVEFORMATEX {
            wFormatTag: tag,
            nChannels: 2,
            nSamplesPerSec: rate,
            nAvgBytesPerSec: rate * align as u32,
            nBlockAlign: align,
            wBitsPerSample: bits,
            cbSize: 0,
        }
    }

    /// Asks the system for a recording of `pid` and its children.
    unsafe fn open(pid: u32) -> Result<IAudioClient, String> {
        unsafe {
            let mut params = AUDIOCLIENT_ACTIVATION_PARAMS {
                ActivationType: AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK,
                Anonymous: AUDIOCLIENT_ACTIVATION_PARAMS_0 {
                    ProcessLoopbackParams: AUDIOCLIENT_PROCESS_LOOPBACK_PARAMS {
                        TargetProcessId: pid,
                        ProcessLoopbackMode: PROCESS_LOOPBACK_MODE_INCLUDE_TARGET_PROCESS_TREE,
                    },
                },
            };
            // Never dropped: dropping a PROPVARIANT frees its blob, and this
            // blob is `params`, on the stack.
            let blob = std::mem::ManuallyDrop::new(PROPVARIANT {
                Anonymous: PROPVARIANT_0 {
                    Anonymous: std::mem::ManuallyDrop::new(PROPVARIANT_0_0 {
                        vt: VT_BLOB,
                        Anonymous: PROPVARIANT_0_0_0 {
                            blob: BLOB {
                                cbSize: std::mem::size_of::<AUDIOCLIENT_ACTIVATION_PARAMS>() as u32,
                                pBlobData: &mut params as *mut _ as *mut u8,
                            },
                        },
                        ..Default::default()
                    }),
                },
            });
            let (tx, rx) = mpsc::channel();
            let handler: IActivateAudioInterfaceCompletionHandler = Opened(tx).into();
            let operation = ActivateAudioInterfaceAsync(
                VIRTUAL_AUDIO_DEVICE_PROCESS_LOOPBACK,
                &IAudioClient::IID,
                Some(&*blob),
                &handler,
            )
            .map_err(|e| {
                format!(
                    "Can't capture the program: {} (it needs Windows 10 version 2004 or later)",
                    e.message()
                )
            })?;
            rx.recv_timeout(Duration::from_secs(5))
                .map_err(|_| "Can't capture the program: the system didn't answer".to_string())?;
            let mut result = HRESULT(0);
            let mut interface: Option<IUnknown> = None;
            operation
                .GetActivateResult(&mut result, &mut interface)
                .map_err(failed("open"))?;
            result.ok().map_err(failed("open"))?;
            interface
                .ok_or("Can't capture the program: no recording")?
                .cast()
                .map_err(failed("open"))
        }
    }

    #[cfg(test)]
    mod tests {
        use super::*;

        #[test]
        #[ignore = "needs Spotify playing"]
        fn records_spotify_alone() {
            let mut source = Source::new(|| {});
            source.scan();
            let (_, pid) = source
                .playing
                .iter()
                .find(|(p, _)| p.key == "spotify.exe")
                .cloned()
                .expect("Spotify isn't playing");
            let shared = Shared::new();
            let stop = Arc::new(AtomicBool::new(false));
            let thread = {
                let (shared, stop) = (Arc::clone(&shared), Arc::clone(&stop));
                std::thread::spawn(move || record(pid, 48000, &shared, &stop))
            };
            std::thread::sleep(Duration::from_secs(3));
            stop.store(true, Ordering::Relaxed);
            thread.join().unwrap().unwrap();
        }
    }
}
