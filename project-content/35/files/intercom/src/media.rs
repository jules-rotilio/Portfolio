//! What other programs are playing (Spotify, a browser, a video player...),
//! for the "Now playing" card, and their play / pause / skip buttons.
//!
//! - Linux: the MPRIS players on the session D-Bus, the standard every
//!   desktop player and browser speaks.
//! - Windows: the system's media sessions, the ones the volume flyout shows.
//!
//! A thread asks every second; the window reads its last answer.

use std::sync::mpsc::{Receiver, RecvTimeoutError, Sender, channel};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

/// One program's current track.
#[derive(Clone, Debug, PartialEq)]
pub struct Track {
    /// Which player, to send it commands.
    pub id: String,
    /// The program's name, e.g. "Spotify".
    pub app: String,
    pub title: String,
    pub artist: String,
    /// Playing, or paused.
    pub playing: bool,
    /// Seconds, when the player tells.
    pub position: Option<f32>,
    pub length: Option<f32>,
}

impl Track {
    /// Everything but the position, which changes every time.
    fn same_as(&self, other: &Track) -> bool {
        Track {
            position: None,
            ..self.clone()
        } == Track {
            position: None,
            ..other.clone()
        }
    }
}

#[derive(Clone, Copy, Debug)]
pub enum Command {
    PlayPause,
    Next,
    Previous,
}

pub struct Media {
    /// The last answer, and when it came.
    tracks: Arc<Mutex<(Vec<Track>, Instant)>>,
    commands: Sender<(String, Command)>,
}

impl Media {
    /// Starts the thread. `repaint` is called when a track or its state changes.
    pub fn start(repaint: impl Fn() + Send + 'static) -> Media {
        let tracks = Arc::new(Mutex::new((Vec::new(), Instant::now())));
        let (commands, rx) = channel();
        let shared = Arc::clone(&tracks);
        let _ = std::thread::Builder::new()
            .name("media".into())
            .spawn(move || watch(&shared, &rx, repaint));
        Media { tracks, commands }
    }

    /// The players with a track, playing ones first, positions moved on to now.
    pub fn tracks(&self) -> Vec<Track> {
        let (tracks, at) = &*self.tracks.lock().unwrap();
        let since = at.elapsed().as_secs_f32();
        tracks
            .iter()
            .map(|t| {
                let mut t = t.clone();
                if t.playing {
                    t.position = t.position.map(|p| {
                        let p = p + since;
                        t.length.map_or(p, |l| p.min(l))
                    });
                }
                t
            })
            .collect()
    }

    pub fn send(&self, id: &str, command: Command) {
        let _ = self.commands.send((id.to_string(), command));
    }
}

fn watch(
    shared: &Mutex<(Vec<Track>, Instant)>,
    rx: &Receiver<(String, Command)>,
    repaint: impl Fn(),
) {
    let mut source = Source::new();
    loop {
        let mut tracks = source.tracks();
        // Stable order: playing first, then by program.
        tracks.sort_by(|a, b| b.playing.cmp(&a.playing).then_with(|| a.app.cmp(&b.app)));
        let changed = {
            let mut last = shared.lock().unwrap();
            let changed = last.0.len() != tracks.len()
                || last.0.iter().zip(&tracks).any(|(a, b)| !a.same_as(b));
            *last = (tracks, Instant::now());
            changed
        };
        if changed {
            repaint();
        }
        match rx.recv_timeout(Duration::from_secs(1)) {
            Ok((id, command)) => source.send(&id, command),
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => return,
        }
    }
}

#[cfg(target_os = "linux")]
use linux::Source;
#[cfg(windows)]
use windows::Source;

/// Elsewhere: nothing is ever playing.
#[cfg(not(any(target_os = "linux", windows)))]
struct Source;
#[cfg(not(any(target_os = "linux", windows)))]
impl Source {
    fn new() -> Source {
        Source
    }
    fn tracks(&mut self) -> Vec<Track> {
        Vec::new()
    }
    fn send(&mut self, _id: &str, _command: Command) {}
}

#[cfg(target_os = "linux")]
mod linux {
    use super::{Command, Track};
    use std::collections::HashMap;
    use zbus::blocking::fdo::DBusProxy;
    use zbus::blocking::proxy::Builder;
    use zbus::blocking::{Connection, Proxy};
    use zbus::names::BusName;
    use zbus::proxy::CacheProperties;
    use zbus::zvariant::{OwnedValue, Value};

    const PREFIX: &str = "org.mpris.MediaPlayer2.";
    const PLAYER: &str = "org.mpris.MediaPlayer2.Player";
    /// playerctld repeats whichever player was used last: it would show twice.
    const SKIP: &str = "org.mpris.MediaPlayer2.playerctld";

    /// The session bus, kept open (and reopened after an error).
    pub struct Source {
        bus: Option<Connection>,
    }

    impl Source {
        pub fn new() -> Source {
            Source { bus: None }
        }

        pub fn tracks(&mut self) -> Vec<Track> {
            if self.bus.is_none() {
                self.bus = Connection::session().ok();
            }
            let Some(bus) = &self.bus else {
                return Vec::new();
            };
            let Ok(dbus) = DBusProxy::new(bus) else {
                self.bus = None;
                return Vec::new();
            };
            let Ok(names) = dbus.list_names() else {
                self.bus = None;
                return Vec::new();
            };
            let found: Vec<(Track, Option<u32>)> = names
                .iter()
                .map(|n| n.as_str())
                .filter(|n| n.starts_with(PREFIX) && *n != SKIP)
                .filter_map(|n| track(bus, n))
                .collect();
            // KDE's browser integration repeats a browser's media, with better
            // titles, and names the browser's process ("kde:pid"). The
            // browser's own player is then left out, as Plasma does.
            let repeated: Vec<u32> = found.iter().filter_map(|(_, pid)| *pid).collect();
            let is_repeated = |id: &str| {
                BusName::try_from(id)
                    .ok()
                    .and_then(|name| dbus.get_connection_unix_process_id(name).ok())
                    .is_some_and(|pid| repeated.contains(&pid))
            };
            found
                .into_iter()
                .filter(|(t, _)| repeated.is_empty() || !is_repeated(&t.id))
                .map(|(t, _)| t)
                .collect()
        }

        pub fn send(&mut self, id: &str, command: Command) {
            let Some(bus) = &self.bus else { return };
            let method = match command {
                Command::PlayPause => "PlayPause",
                Command::Next => "Next",
                Command::Previous => "Previous",
            };
            if let Ok(player) = proxy(bus, id, PLAYER) {
                let _ = player.call_method(method, &());
            }
        }
    }

    /// A proxy that reads properties when asked (no cache, no signals).
    fn proxy<'a>(bus: &Connection, name: &'a str, interface: &'a str) -> zbus::Result<Proxy<'a>> {
        Builder::new(bus)
            .destination(name)?
            .path("/org/mpris/MediaPlayer2")?
            .interface(interface)?
            .cache_properties(CacheProperties::No)
            .build()
    }

    /// The player's track, and the process it repeats ("kde:pid"), if any.
    fn track(bus: &Connection, name: &str) -> Option<(Track, Option<u32>)> {
        let player = proxy(bus, name, PLAYER).ok()?;
        let status: String = player.get_property("PlaybackStatus").ok()?;
        if status != "Playing" && status != "Paused" {
            return None;
        }
        let meta: HashMap<String, OwnedValue> = player.get_property("Metadata").ok()?;
        let title = meta.get("xesam:title").map(|v| text(v)).unwrap_or_default();
        if title.is_empty() {
            return None;
        }
        let app = proxy(bus, name, "org.mpris.MediaPlayer2")
            .ok()
            .and_then(|p| p.get_property::<String>("Identity").ok())
            // org.mpris.MediaPlayer2.vlc.instance123 → vlc
            .unwrap_or_else(|| {
                name[PREFIX.len()..]
                    .split('.')
                    .next()
                    .unwrap_or(name)
                    .into()
            });
        let track = Track {
            id: name.to_string(),
            app,
            title,
            artist: meta
                .get("xesam:artist")
                .map(|v| text(v))
                .unwrap_or_default(),
            playing: status == "Playing",
            position: player
                .get_property::<i64>("Position")
                .ok()
                .map(|us| us as f32 / 1e6),
            length: meta.get("mpris:length").and_then(|v| micros(v)),
        };
        let pid = meta.get("kde:pid").and_then(|v| match &**v {
            Value::I32(n) => u32::try_from(*n).ok(),
            Value::U32(n) => Some(*n),
            _ => None,
        });
        Some((track, pid))
    }

    /// A string, or a list of strings (artists) joined with commas.
    fn text(v: &Value) -> String {
        match v {
            Value::Str(s) => s.to_string(),
            Value::Array(a) => a
                .iter()
                .map(text)
                .filter(|s| !s.is_empty())
                .collect::<Vec<_>>()
                .join(", "),
            Value::Value(v) => text(v),
            _ => String::new(),
        }
    }

    /// Microseconds to seconds. Players disagree on the number's type.
    fn micros(v: &Value) -> Option<f32> {
        let us = match v {
            Value::I64(n) => *n as f64,
            Value::U64(n) => *n as f64,
            Value::I32(n) => *n as f64,
            Value::U32(n) => *n as f64,
            Value::Value(v) => return micros(v),
            _ => return None,
        };
        (us > 0.0).then_some((us / 1e6) as f32)
    }
}

#[cfg(windows)]
mod windows {
    use super::{Command, Track};
    use std::time::{SystemTime, UNIX_EPOCH};
    use windows::Media::Control::{
        GlobalSystemMediaTransportControlsSession as Session,
        GlobalSystemMediaTransportControlsSessionManager as Manager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
    };

    /// Windows times count 100 ns steps.
    const TICKS: f64 = 1e7;
    /// From 1601 (Windows' start of time) to 1970.
    const TO_1970: f64 = 11_644_473_600.0;

    pub struct Source {
        manager: Option<Manager>,
    }

    impl Source {
        pub fn new() -> Source {
            Source { manager: None }
        }

        fn sessions(&mut self) -> Vec<Session> {
            if self.manager.is_none() {
                self.manager = Manager::RequestAsync().and_then(|op| op.join()).ok();
            }
            self.manager
                .as_ref()
                .and_then(|m| m.GetSessions().ok())
                .map(|list| list.into_iter().collect())
                .unwrap_or_default()
        }

        pub fn tracks(&mut self) -> Vec<Track> {
            self.sessions().iter().filter_map(track).collect()
        }

        pub fn send(&mut self, id: &str, command: Command) {
            for session in self.sessions() {
                if session.SourceAppUserModelId().is_ok_and(|s| s == id) {
                    let _ = match command {
                        Command::PlayPause => session.TryTogglePlayPauseAsync(),
                        Command::Next => session.TrySkipNextAsync(),
                        Command::Previous => session.TrySkipPreviousAsync(),
                    }
                    .and_then(|op| op.join());
                }
            }
        }
    }

    fn track(session: &Session) -> Option<Track> {
        let id = session.SourceAppUserModelId().ok()?.to_string();
        let status = session.GetPlaybackInfo().ok()?.PlaybackStatus().ok()?;
        if status != Status::Playing && status != Status::Paused {
            return None;
        }
        let props = session
            .TryGetMediaPropertiesAsync()
            .and_then(|op| op.join())
            .ok()?;
        let title = props.Title().ok()?.to_string();
        if title.is_empty() {
            return None;
        }
        let playing = status == Status::Playing;
        let (position, length) = timeline(session, playing).unwrap_or((None, None));
        Some(Track {
            app: app_name(&id),
            id,
            title,
            artist: props.Artist().map(|a| a.to_string()).unwrap_or_default(),
            playing,
            position,
            length,
        })
    }

    /// The position and length, in seconds. The position is the one at the
    /// player's last update (players update it rarely), moved on to now.
    fn timeline(session: &Session, playing: bool) -> Option<(Option<f32>, Option<f32>)> {
        let t = session.GetTimelineProperties().ok()?;
        let start = t.StartTime().ok()?.Duration as f64;
        let end = t.EndTime().ok()?.Duration as f64;
        let mut position = (t.Position().ok()?.Duration as f64 - start) / TICKS;
        if playing {
            let updated = t.LastUpdatedTime().ok()?.UniversalTime as f64 / TICKS - TO_1970;
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .ok()?
                .as_secs_f64();
            position += (now - updated).max(0.0);
        }
        let length = (end - start) / TICKS;
        if length <= 0.0 {
            return Some((None, None));
        }
        Some((
            Some(position.clamp(0.0, length) as f32),
            Some(length as f32),
        ))
    }

    /// A readable name from the session's app id: "Spotify.exe" → "Spotify",
    /// "Microsoft.ZuneMusic_8wekyb3d8bbwe!Microsoft.ZuneMusic" → "ZuneMusic".
    fn app_name(id: &str) -> String {
        let name = id.rsplit('!').next().unwrap_or(id);
        let name = name.strip_suffix(".exe").unwrap_or(name);
        let name = name.rsplit('.').next().unwrap_or(name);
        // Firefox's id is a hash of its install folder.
        if name.len() == 16 && name.chars().all(|c| c.is_ascii_hexdigit()) {
            return "Firefox".into();
        }
        name.to_string()
    }
}
