//! Development aid: with `INTERCOM_SNAPSHOT=<folder>`, Intercom takes a
//! picture of the main window and of each Settings tab (as `.ppm` files in
//! that folder), then closes normally. Used to check the screens without
//! clicking through them.
//!
//! eframe can't photograph a second window, so for the Settings pictures the
//! Settings window is drawn inside the main one (egui's "embedded viewports"),
//! and the main window is made big enough to hold it.
//!
//! `INTERCOM_SNAPSHOT_PLAY=Num2` also presses that sound key once, early on,
//! and `INTERCOM_SNAPSHOT_WAIT=<seconds>` waits that long before the first
//! picture (to record the virtual mic meanwhile).
//!
//! `INTERCOM_SNAPSHOT_PROGRAM=spotify` captures that program's sound (its
//! executable's name) as soon as it plays, as if picked in "Now playing".
//!
//! `INTERCOM_SNAPSHOT_MAXIMIZED=1` maximizes the main window for its picture,
//! so everything fits (side by side, like a maximized window shows it).
//!
//! `INTERCOM_SNAPSHOT_KEYS=1.0:F17+,1.5:F17-` sends key events at those
//! times (seconds after start; `+` pressed, `-` released) as if they came
//! from the keyboard, to try auto-click and drift without touching it.

use crate::app::{App, Tab};
use eframe::egui::{self, ColorImage, ViewportCommand, ViewportId};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::{AtomicBool, Ordering};

pub struct Snapshot {
    dir: PathBuf,
    step: usize,
    frame: u32,
    /// Frame at which the current step's picture is taken.
    shoot_at: u32,
    requested: bool,
    done: Arc<AtomicBool>,
    play: Option<crate::keys::Key>,
    /// The program to capture, until it is.
    program: Option<String>,
    maximized: bool,
    started: std::time::Instant,
    wait: f32,
    /// Key events still to send: (seconds after start, event), soonest last.
    keys: Vec<(f32, crate::hotkeys::KeyEvent)>,
}

/// Reads `1.0:F17+,1.5:F17-`.
fn parse_keys(text: &str) -> Vec<(f32, crate::hotkeys::KeyEvent)> {
    let mut keys: Vec<(f32, crate::hotkeys::KeyEvent)> = text
        .split(',')
        .filter_map(|item| {
            let (at, key) = item.trim().split_once(':')?;
            let pressed = key.ends_with('+');
            let key = crate::keys::Key::from_name(key.strip_suffix(['+', '-'])?)?;
            let event = crate::hotkeys::KeyEvent {
                key,
                pressed,
                repeat: false,
            };
            Some((at.parse().ok()?, event))
        })
        .collect();
    keys.sort_by(|a, b| b.0.total_cmp(&a.0));
    keys
}

/// The main window's size for the Settings pictures, which draw the
/// Settings window inside it.
const SETTINGS_SIZE: egui::Vec2 = egui::vec2(1000.0, 800.0);

const TABS: [(Tab, &str); 6] = [
    (Tab::Audio, "settings-audio"),
    (Tab::Voice, "settings-voice"),
    (Tab::Sounds, "settings-sounds"),
    (Tab::Hotkeys, "settings-hotkeys"),
    (Tab::Input, "settings-input"),
    (Tab::General, "settings-general"),
];

impl Snapshot {
    pub fn from_env() -> Option<Snapshot> {
        let dir = PathBuf::from(std::env::var_os("INTERCOM_SNAPSHOT")?);
        std::fs::create_dir_all(&dir).ok()?;
        Some(Snapshot {
            dir,
            step: 0,
            frame: 0,
            shoot_at: 40,
            requested: false,
            done: Arc::new(AtomicBool::new(false)),
            play: std::env::var("INTERCOM_SNAPSHOT_PLAY")
                .ok()
                .and_then(|name| crate::keys::Key::from_name(&name)),
            program: std::env::var("INTERCOM_SNAPSHOT_PROGRAM").ok(),
            maximized: std::env::var_os("INTERCOM_SNAPSHOT_MAXIMIZED").is_some(),
            started: std::time::Instant::now(),
            wait: std::env::var("INTERCOM_SNAPSHOT_WAIT")
                .ok()
                .and_then(|w| w.parse().ok())
                .unwrap_or(0.0),
            keys: parse_keys(&std::env::var("INTERCOM_SNAPSHOT_KEYS").unwrap_or_default()),
        })
    }
}

/// Call at the end of every frame of the main window.
pub fn tick(app: &mut App, ctx: &egui::Context) {
    let Some(mut snap) = app.snapshot.take() else {
        return;
    };
    snap.frame += 1;
    if snap.frame == 1 && snap.maximized {
        ctx.send_viewport_cmd(ViewportCommand::Maximized(true));
    }
    if snap.frame == 10
        && let Some(key) = snap.play
    {
        app.controller.apply(crate::controller::Action::Play(key));
    }
    if let Some(key) = &snap.program
        && let Some(program) = app.programs.list().into_iter().find(|p| p.key == *key)
    {
        app.set_program(Some(program));
        snap.program = None;
    }
    let elapsed = snap.started.elapsed().as_secs_f32();
    while snap.keys.last().is_some_and(|(at, _)| *at <= elapsed) {
        let (_, event) = snap.keys.pop().unwrap();
        app.controller.handle(event);
    }
    if snap.step == 0 && snap.started.elapsed().as_secs_f32() < snap.wait {
        snap.shoot_at = snap.frame + 1;
    }
    ctx.request_repaint();
    if snap.requested && snap.done.swap(false, Ordering::Relaxed) {
        snap.requested = false;
        snap.step += 1;
        snap.shoot_at = snap.frame + 25;
        if let Some((tab, _)) = TABS.get(snap.step - 1) {
            if !app.settings_open {
                ctx.set_embed_viewports(true);
                if snap.maximized {
                    ctx.send_viewport_cmd(ViewportCommand::Maximized(false));
                    snap.shoot_at += 20;
                }
                ctx.send_viewport_cmd(ViewportCommand::InnerSize(SETTINGS_SIZE));
            }
            app.settings_open = true;
            app.tab = *tab;
        }
    }
    // Leaving the maximized state takes a few frames, and a size asked for
    // meanwhile is lost: ask again until the first Settings picture.
    if snap.maximized && snap.step == 1 && !snap.requested {
        ctx.send_viewport_cmd(ViewportCommand::InnerSize(SETTINGS_SIZE));
    }
    if !snap.requested && snap.frame >= snap.shoot_at {
        let (viewport, name) = match snap.step {
            0 => (ViewportId::ROOT, "main"),
            n if n <= TABS.len() => (ViewportId::ROOT, TABS[n - 1].1),
            _ => {
                app.allow_close();
                ctx.send_viewport_cmd_to(ViewportId::ROOT, ViewportCommand::Close);
                app.snapshot = Some(snap);
                return;
            }
        };
        let path = snap.dir.join(format!("{name}.ppm"));
        let done = Arc::clone(&snap.done);
        let callback = egui::ScreenshotCallback::new(move |image: Arc<ColorImage>| {
            let _ = save_ppm(&path, &image);
            done.store(true, Ordering::Relaxed);
        });
        ctx.send_viewport_cmd_to(viewport, ViewportCommand::Screenshot(callback));
        snap.requested = true;
    }
    app.snapshot = Some(snap);
}

/// The simplest picture format: a small header, then RGB bytes.
fn save_ppm(path: &std::path::Path, image: &ColorImage) -> std::io::Result<()> {
    let [w, h] = image.size;
    let mut data = format!("P6\n{w} {h}\n255\n").into_bytes();
    for pixel in &image.pixels {
        data.extend_from_slice(&[pixel.r(), pixel.g(), pixel.b()]);
    }
    std::fs::write(path, data)
}
