//! The simulated mouse: Valkyrie's auto-click and the .NET app's drift.
//!
//! Both send through one virtual mouse, from one thread that sleeps until
//! the next click or move is due:
//!
//! - Linux: a virtual mouse made with `/dev/uinput` (works on X11 and
//!   Wayland alike; needs write access, see `Status::NoPermission`).
//! - Windows: `SendInput`, with the system timer set to 1 ms while clicking
//!   (otherwise it wakes up in 15.6 ms steps and the rate stutters).
//!
//! `Machine` decides what to send and when; it takes times from the caller
//! and is tested below. The thread around it does the waiting and sending.

mod clicker;
mod drift;
#[cfg(target_os = "linux")]
mod linux;
#[cfg(windows)]
mod windows;

use crate::audio::Player;
use crate::config::{AutoClick, ClickMode, Config, Drift};
use crate::hotkeys::KeyEvent;
use crate::keys::Key;
use clicker::{Clicker, Out};
pub use drift::Direction;
use drift::Drifter;
use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender, channel};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

#[cfg(target_os = "linux")]
use linux::VirtualMouse;
#[cfg(windows)]
use windows::VirtualMouse;

#[derive(Clone, Debug, PartialEq)]
pub enum Status {
    Ready,
    /// Linux: `/dev/uinput` can't be opened.
    #[cfg_attr(not(target_os = "linux"), allow(dead_code))]
    NoPermission,
    #[cfg_attr(windows, allow(dead_code))]
    Failed(String),
}

/// What the mouse thread needs from the config.
#[derive(Clone, PartialEq, Debug)]
pub struct Settings {
    pub autoclick: AutoClick,
    pub drift: Drift,
    pub left: Key,
    pub right: Key,
}

impl Settings {
    pub fn of(config: &Config) -> Settings {
        Settings {
            autoclick: config.autoclick.clone(),
            drift: config.drift.clone(),
            left: config.hotkeys.drift_left,
            right: config.hotkeys.drift_right,
        }
    }
}

/// What the window shows, and what the rate and mode keys changed.
#[derive(Clone, Debug, PartialEq)]
pub struct Live {
    pub rate: f32,
    pub mode: ClickMode,
    pub clicking: bool,
    pub drift: Option<Direction>,
    /// Counts the changes made with the faster/slower/mode keys, so the
    /// window can copy them into the settings.
    pub key_changes: u64,
    /// The last problem sending to the mouse.
    pub error: Option<String>,
}

/// The sounds that confirm what the keys did (heard in the headset only).
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Cue {
    /// Clicking started (two rising tones) or stopped (two falling tones).
    On,
    Off,
    /// A new rate: the higher the beep, the faster.
    Rate(f32),
    /// The new mode: two short beeps for toggle, one long beep for hold.
    Mode(ClickMode),
}

impl Cue {
    /// The sound at `rate` samples per second, full volume.
    fn samples(self, rate: u32) -> Vec<f32> {
        const LOW: f32 = 660.0; // a fifth apart
        const HIGH: f32 = 990.0;
        const MID: f32 = 825.0;
        match self {
            Cue::On => tones(&[LOW, HIGH], rate, 0.07, 0.03),
            Cue::Off => tones(&[HIGH, LOW], rate, 0.07, 0.03),
            Cue::Rate(clicks) => tones(&[300.0 + 17.0 * clicks], rate, 0.05, 0.0),
            Cue::Mode(ClickMode::Toggle) => tones(&[MID, MID], rate, 0.05, 0.04),
            Cue::Mode(ClickMode::Hold) => tones(&[MID], rate, 0.18, 0.0),
        }
    }
}

/// One tone per frequency, `tone` seconds each, `gap` seconds apart, with
/// 8 ms fades so they don't click.
fn tones(freqs: &[f32], rate: u32, tone: f32, gap: f32) -> Vec<f32> {
    let rate_f = rate as f32;
    let n = (tone * rate_f) as usize;
    let fade = 0.008 * rate_f;
    let mut out = Vec::new();
    for (i, freq) in freqs.iter().enumerate() {
        if i > 0 {
            out.resize(out.len() + (gap * rate_f) as usize, 0.0);
        }
        out.extend((0..n).map(|k| {
            let edge = (k as f32 / fade).min((n - k) as f32 / fade).min(1.0);
            edge * (std::f32::consts::TAU * freq * k as f32 / rate_f).sin()
        }));
    }
    out
}

/// Which clicks and moves to send, and when.
pub struct Machine {
    settings: Settings,
    clicker: Clicker,
    drifter: Drifter,
    key_changes: u64,
    /// Waiting to be sent, and to be played.
    out: Vec<Out>,
    cues: Vec<Cue>,
}

impl Machine {
    pub fn new(settings: Settings) -> Machine {
        Machine {
            clicker: Clicker::new(&settings.autoclick),
            drifter: Drifter::new(&settings.drift),
            settings,
            key_changes: 0,
            out: Vec::new(),
            cues: Vec::new(),
        }
    }

    pub fn configure(&mut self, settings: Settings) {
        let out = self.clicker.configure(&settings.autoclick);
        self.out.extend(out);
        // Off, or a new trigger key (whose release would never come): stop clicking.
        if !settings.autoclick.enabled
            || settings.autoclick.trigger != self.settings.autoclick.trigger
        {
            let out = self.clicker.stop();
            self.out.extend(out);
        }
        if !settings.drift.enabled {
            self.drifter.stop();
        }
        self.drifter.configure(&settings.drift);
        self.settings = settings;
    }

    pub fn key(&mut self, event: KeyEvent, now: f64) {
        let a = &self.settings.autoclick;
        let key = Some(event.key);
        if a.enabled && event.key == a.trigger {
            if !event.repeat
                && let Some(started) = self.clicker.key(event.pressed, now)
                && self.clicker.mode == ClickMode::Toggle
            {
                self.cue(if started { Cue::On } else { Cue::Off });
            }
        } else if a.enabled && (key == a.faster_key || key == a.slower_key) {
            // Holding the key keeps going (the system repeats it).
            if event.pressed {
                let step = if key == a.faster_key { a.step } else { -a.step };
                let rate = self.clicker.set_rate(self.clicker.rate + step);
                self.key_changes += 1;
                self.cue(Cue::Rate(rate));
            }
        } else if a.enabled && key == a.mode_key {
            if event.pressed && !event.repeat {
                let (mode, out, stopped) = self.clicker.switch_mode();
                self.out.extend(out);
                self.key_changes += 1;
                if stopped {
                    self.cue(Cue::Off);
                }
                self.cue(Cue::Mode(mode));
            }
        } else if self.settings.drift.enabled && event.pressed && !event.repeat {
            if event.key == self.settings.left {
                self.drifter.key(Direction::Left, now);
            } else if event.key == self.settings.right {
                self.drifter.key(Direction::Right, now);
            }
        }
    }

    fn cue(&mut self, cue: Cue) {
        if self.settings.autoclick.sounds {
            self.cues.push(cue);
        }
    }

    /// Stops clicking and drifting; a pressed button is released.
    pub fn stop_all(&mut self) {
        let out = self.clicker.stop();
        self.out.extend(out);
        self.drifter.stop();
    }

    /// Queues what is due at `now`.
    pub fn due(&mut self, now: f64) {
        let out = self.clicker.due(now);
        self.out.extend(out);
        self.out.extend(self.drifter.due(now));
    }

    /// When `due` has something to do next, if ever.
    pub fn deadline(&self) -> Option<f64> {
        match (self.clicker.deadline(), self.drifter.deadline()) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        }
    }

    fn live(&self, error: Option<String>) -> Live {
        Live {
            rate: self.clicker.rate,
            mode: self.clicker.mode,
            clicking: self.clicker.active,
            drift: self.drifter.direction,
            key_changes: self.key_changes,
            error,
        }
    }
}

enum Msg {
    Key(KeyEvent),
    Configure(Settings),
    StopAll,
    Quit,
}

/// Sends key events to the mouse thread; cheap to clone.
#[derive(Clone)]
pub struct Remote(Sender<Msg>);

impl Remote {
    pub fn key(&self, event: KeyEvent) {
        let _ = self.0.send(Msg::Key(event));
    }

    pub fn stop_all(&self) {
        let _ = self.0.send(Msg::StopAll);
    }
}

/// The mouse thread. Dropping it stops everything and releases the button.
pub struct Mouse {
    remote: Remote,
    pub status: Status,
    live: Arc<Mutex<Live>>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl Mouse {
    pub fn start(
        settings: Settings,
        player: Arc<Player>,
        repaint: impl Fn() + Send + 'static,
    ) -> Mouse {
        let device = open();
        let status = match &device {
            Ok(_) => Status::Ready,
            Err(status) => status.clone(),
        };
        let machine = Machine::new(settings);
        let live = Arc::new(Mutex::new(machine.live(None)));
        let (tx, rx) = channel();
        let thread = {
            let live = Arc::clone(&live);
            std::thread::Builder::new()
                .name("mouse".into())
                .spawn(move || run(rx, machine, device.ok(), &player, &live, repaint))
                .ok()
        };
        Mouse {
            remote: Remote(tx),
            status,
            live,
            thread,
        }
    }

    pub fn remote(&self) -> Remote {
        self.remote.clone()
    }

    pub fn configure(&self, settings: Settings) {
        let _ = self.remote.0.send(Msg::Configure(settings));
    }

    pub fn stop_all(&self) {
        let _ = self.remote.0.send(Msg::StopAll);
    }

    pub fn live(&self) -> Live {
        self.live.lock().unwrap().clone()
    }
}

impl Drop for Mouse {
    fn drop(&mut self) {
        let _ = self.remote.0.send(Msg::Quit);
        if let Some(thread) = self.thread.take() {
            let _ = thread.join();
        }
    }
}

fn open() -> Result<VirtualMouse, Status> {
    #[cfg(any(target_os = "linux", windows))]
    return VirtualMouse::open();
    #[cfg(not(any(target_os = "linux", windows)))]
    Err(Status::Failed("not supported on this system".into()))
}

#[cfg(not(any(target_os = "linux", windows)))]
struct VirtualMouse;
#[cfg(not(any(target_os = "linux", windows)))]
impl VirtualMouse {
    fn send(&mut self, _: &[Out]) -> Result<(), String> {
        Ok(())
    }
    fn set_busy(&mut self, _: bool) {}
}

fn run(
    rx: Receiver<Msg>,
    mut machine: Machine,
    mut device: Option<VirtualMouse>,
    player: &Player,
    live: &Mutex<Live>,
    repaint: impl Fn(),
) {
    let origin = Instant::now();
    let now = || origin.elapsed().as_secs_f64();
    let mut error = None;
    loop {
        let msg = match machine.deadline() {
            Some(deadline) => {
                let wait = Duration::from_secs_f64((deadline - now()).max(0.0));
                match rx.recv_timeout(wait) {
                    Ok(msg) => Some(msg),
                    Err(RecvTimeoutError::Timeout) => None,
                    Err(RecvTimeoutError::Disconnected) => break,
                }
            }
            None => match rx.recv() {
                Ok(msg) => Some(msg),
                Err(_) => break,
            },
        };
        match msg {
            Some(Msg::Key(event)) => machine.key(event, now()),
            Some(Msg::Configure(settings)) => machine.configure(settings),
            Some(Msg::StopAll) => machine.stop_all(),
            Some(Msg::Quit) => break,
            None => {}
        }
        machine.due(now());

        if let Some(device) = &mut device {
            if !machine.out.is_empty()
                && let Err(e) = device.send(&machine.out)
            {
                error = Some(e);
            }
            device.set_busy(machine.deadline().is_some());
        }
        machine.out.clear();
        let gain = machine.settings.autoclick.sound_volume;
        for cue in machine.cues.drain(..) {
            player.cue(|rate| cue.samples(rate), gain);
        }

        let now_live = machine.live(error.clone());
        let mut shown = live.lock().unwrap();
        if *shown != now_live {
            *shown = now_live;
            repaint();
        }
    }
    machine.stop_all();
    if let Some(device) = &mut device {
        let _ = device.send(&machine.out);
        device.set_busy(false);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::MouseButton;

    fn settings() -> Settings {
        Settings {
            autoclick: AutoClick {
                trigger: Key::F13,
                faster_key: Some(Key::F15),
                slower_key: Some(Key::F14),
                mode_key: Some(Key::F16),
                rate: 10.0,
                ..AutoClick::default()
            },
            drift: Drift::default(),
            left: Key::Left,
            right: Key::Right,
        }
    }

    fn event(key: Key, pressed: bool, repeat: bool) -> KeyEvent {
        KeyEvent {
            key,
            pressed,
            repeat,
        }
    }

    #[test]
    fn trigger_clicks_and_chimes_in_toggle_mode() {
        let mut m = Machine::new(settings());
        m.key(event(Key::F13, true, false), 0.0);
        m.due(0.0);
        assert_eq!(m.out, [Out::Button(MouseButton::Left, true)]);
        assert_eq!(m.cues, [Cue::On]);
        m.key(event(Key::F13, false, false), 0.01);
        assert!(m.live(None).clicking); // toggle: the release changes nothing
    }

    #[test]
    fn rate_keys_repeat_and_count_as_changes() {
        let mut m = Machine::new(settings());
        m.key(event(Key::F15, true, false), 0.0);
        m.key(event(Key::F15, true, true), 0.1);
        m.key(event(Key::F14, true, false), 0.2);
        let live = m.live(None);
        assert_eq!((live.rate, live.key_changes), (11.0, 3));
        assert_eq!(m.cues, [Cue::Rate(11.0), Cue::Rate(12.0), Cue::Rate(11.0)]);
    }

    #[test]
    fn mode_key_stops_and_releases() {
        let mut m = Machine::new(settings());
        m.key(event(Key::F13, true, false), 0.0);
        m.due(0.0);
        m.out.clear();
        m.key(event(Key::F16, true, false), 0.005);
        assert_eq!(m.out, [Out::Button(MouseButton::Left, false)]);
        assert_eq!(m.cues, [Cue::On, Cue::Off, Cue::Mode(ClickMode::Hold)]);
        assert!(!m.live(None).clicking);
    }

    #[test]
    fn turning_it_off_stops_and_ignores_the_keys() {
        let mut m = Machine::new(settings());
        m.key(event(Key::F13, true, false), 0.0);
        m.due(0.0);
        let mut off = settings();
        off.autoclick.enabled = false;
        off.drift.enabled = false;
        m.configure(off);
        assert_eq!(m.out.last(), Some(&Out::Button(MouseButton::Left, false)));
        m.key(event(Key::F13, true, false), 1.0);
        m.key(event(Key::Left, true, false), 1.0);
        assert_eq!(m.deadline(), None);
    }

    #[test]
    fn drift_and_clicks_share_the_clock() {
        let mut m = Machine::new(settings());
        m.key(event(Key::Right, true, false), 0.0);
        m.key(event(Key::F13, true, false), 0.0);
        m.due(0.0);
        assert_eq!(m.out, [Out::Button(MouseButton::Left, true), Out::Move(15)]);
        assert_eq!(m.deadline(), Some(0.02)); // release and next move
    }

    #[test]
    fn cues_have_soft_edges() {
        let on = Cue::On.samples(48_000);
        assert_eq!(on.len(), 2 * 3360 + 1440);
        assert!(on[0].abs() < 1e-6 && on.iter().all(|s| s.abs() <= 1.0));
    }
}
