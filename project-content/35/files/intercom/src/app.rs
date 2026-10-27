//! The app: its state, what happens every frame, and the main window.
//!
//! The Settings window is in `settings.rs`; both are drawn by this `App`.

use crate::audio::{self, Engine, Routing, Shared};
use crate::config::{self, Config, EffectChoice, LinuxVirtualMic, Sound, State};
use crate::controller::{Action, Bindings, Controller, Runtime};
use crate::hotkeys::{self, KeyEvent};
use crate::keys::Key;
use crate::media::{self, Media};
use crate::mouse::{self, Mouse};
use crate::programs::{Program, Programs};
use crate::theme::Palette;
use crate::ui_kit::{Part, accent_button, chip, meter, muted, reducible_card, status_line};
use crate::undo::History;
use crate::virtual_mic::{self, VirtualMic};
use eframe::egui::{self, CornerRadius, Margin, Pos2, Rect, RichText, Sense, Stroke, Vec2};
use std::path::PathBuf;
use std::sync::Arc;
use std::sync::atomic::Ordering;
use std::sync::mpsc::{Receiver, Sender, channel};
use std::time::Duration;

/// Which setting the next key press goes to (the "Change" buttons).
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Binding {
    VoiceToggle,
    VolumeUp,
    VolumeDown,
    PageNext,
    PagePrev,
    StopSound,
    DriftLeft,
    DriftRight,
    ClickTrigger,
    ClickFaster,
    ClickSlower,
    ClickMode,
}

impl Binding {
    pub fn set(self, config: &mut Config, key: Key) {
        let h = &mut config.hotkeys;
        let a = &mut config.autoclick;
        match self {
            Binding::VoiceToggle => h.voice_toggle = key,
            Binding::VolumeUp => h.volume_up = key,
            Binding::VolumeDown => h.volume_down = key,
            Binding::PageNext => h.page_next = key,
            Binding::PagePrev => h.page_prev = key,
            Binding::StopSound => h.stop_sound = key,
            Binding::DriftLeft => h.drift_left = key,
            Binding::DriftRight => h.drift_right = key,
            Binding::ClickTrigger => a.trigger = key,
            Binding::ClickFaster => a.faster_key = Some(key),
            Binding::ClickSlower => a.slower_key = Some(key),
            Binding::ClickMode => a.mode_key = Some(key),
        }
    }
}

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Tab {
    Audio,
    Voice,
    Sounds,
    Hotkeys,
    Input,
    General,
}

/// The "edit a key" dialog: a draft, written to the config on OK.
pub struct KeyEdit {
    pub page: usize,
    pub key: Key,
    pub draft: Sound,
    /// Opened from the Settings window (drawn there) or the main window.
    pub in_settings: bool,
}

/// What was last handed to the engine, to notice changes.
#[derive(PartialEq, Clone)]
struct Applied {
    routing: Routing,
    virtual_mic: LinuxVirtualMic,
    /// "Make it the default mic", and the virtual mic it was applied to.
    default_mic: Option<(bool, virtual_mic::Status)>,
}

pub struct App {
    pub config: Config,
    pub history: History,
    pub config_path: PathBuf,
    state_path: PathBuf,
    state_saved: State,
    pub test_on: bool,
    pub message: Option<(String, bool)>,
    pub host: cpal::Host,
    pub devices: (Vec<String>, Vec<String>),
    pub engine: Engine,
    pub shared: Arc<Shared>,
    pub controller: Arc<Controller>,
    key_tx: Sender<KeyEvent>,
    pub hotkeys: hotkeys::Status,
    pub vmic: VirtualMic,
    pub mouse: Mouse,
    /// What other programs are playing.
    media: Media,
    /// The programs whose sound can be captured, and the capture.
    pub programs: Programs,
    /// The program captured for the virtual mic. Never saved: Intercom
    /// starts without one.
    pub program: Option<Program>,
    pub program_volume: f32,
    /// Turning the voice changer on stops the capture.
    voice_was_on: bool,
    /// The system's default mic before the virtual mic took its place.
    replaced_default_mic: Option<String>,
    pub default_mic_problem: Option<String>,
    /// Discord has been used on this computer: Settings › Audio has tips.
    pub discord: bool,
    /// The main window's blocks reduced to one line.
    reduced: config::Reduced,
    applied_mouse: mouse::Settings,
    /// The last `Live::key_changes` copied into the settings.
    mouse_key_changes: u64,
    applied: Applied,
    applied_voice: config::VoiceConfig,
    applied_bindings: Bindings,
    pub pal: Palette,
    applied_look: (config::Appearance, bool),
    meters: (f32, f32),
    pub settings_open: bool,
    pub tab: Tab,
    pub settings_page: usize,
    pub edit: Option<KeyEdit>,
    pub capture: Option<(Binding, Receiver<Key>)>,
    closing: bool,
    allow_close: bool,
    pub is_admin: bool,
    keep_on_top: bool,
    pub snapshot: Option<crate::snapshot::Snapshot>,
}

impl App {
    pub fn new(cc: &eframe::CreationContext) -> App {
        let dir = config::config_dir();
        let config_path = dir.join("config.toml");
        let state_path = dir.join("state.toml");
        let (mut config, message) = match Config::load(&config_path) {
            Ok(Some(config)) => (config, None),
            Ok(None) => (Config::first_start(), None),
            Err(e) => (
                Config::first_start(),
                Some((
                    format!("Settings not loaded, using the defaults: {e}"),
                    true,
                )),
            ),
        };
        let state = State::load(&state_path);

        // Keeps the start-at-login entry pointing at this copy of the program.
        if config.general.start_with_windows {
            let _ = crate::platform::set_autostart(true);
        }

        let shared = Shared::new();
        shared
            .voice_on
            .store(config.voice.on_at_start, Ordering::Relaxed);
        shared.test_on.store(state.test_on, Ordering::Relaxed);
        shared.headset_volume.set(config.audio.headset_volume);
        shared.program_volume.set(state.program_volume);

        let host = audio::host();
        let mut devices = audio::device_names(&host);
        let vmic = VirtualMic::setup(&config.audio.virtual_mic, &devices.1);
        if matches!(
            vmic.status,
            virtual_mic::Status::Ready { created: true, .. }
        ) {
            devices = audio::device_names(&host);
        }
        // The mic is always a real one, named: "the system default" can be
        // the virtual mic, which would loop what others hear back to them.
        if config.audio.mic.is_none() {
            config.audio.mic = audio::default_mic_name(&host);
        }

        let mut engine = Engine::new(Arc::clone(&shared));
        let routing = routing(&config, &vmic.status);
        engine.start(&host, &routing, &config.voice.effect_args());

        // Keys first: the virtual mouse's device file appears without its
        // permissions for a moment, and the keyboard scan would count it as refused.
        let (key_tx, key_rx) = channel();
        let hotkeys = hotkeys::start(key_tx.clone());
        let ctx = cc.egui_ctx.clone();
        let mouse = Mouse::start(mouse::Settings::of(&config), Arc::clone(&engine.player), {
            let ctx = ctx.clone();
            move || ctx.request_repaint()
        });
        let media = Media::start({
            let ctx = ctx.clone();
            move || ctx.request_repaint()
        });
        let programs = Programs::start(Arc::clone(&shared), {
            let ctx = ctx.clone();
            move || ctx.request_repaint()
        });
        let runtime = Runtime {
            page: state.page.min(config.pages.len().saturating_sub(1)),
            sound_volume: state.sound_volume,
            error: None,
        };
        let controller = Controller::new(
            Arc::clone(&engine.player),
            mouse.remote(),
            runtime,
            move || ctx.request_repaint(),
        );
        let bindings = Bindings {
            hotkeys: config.hotkeys.clone(),
            pages: config.pages.clone(),
            voice: config.voice.clone(),
            focus_only: config.general.focus_only,
            focus_program: config.general.focus_program.clone(),
        };
        *controller.bindings.write().unwrap() = bindings.clone();
        Arc::clone(&controller).run(key_rx);

        let system_dark = cc.egui_ctx.system_theme() != Some(egui::Theme::Light);
        let pal = Palette::new(&config.appearance, system_dark);
        pal.apply(&cc.egui_ctx);

        let mut app = App {
            history: History::new(&config),
            applied: Applied {
                routing,
                virtual_mic: config.audio.virtual_mic.clone(),
                default_mic: None,
            },
            applied_mouse: mouse::Settings::of(&config),
            mouse_key_changes: 0,
            mouse,
            media,
            programs,
            program: None,
            program_volume: state.program_volume,
            voice_was_on: config.voice.on_at_start,
            replaced_default_mic: state.replaced_default_mic.clone(),
            default_mic_problem: None,
            discord: crate::programs::discord_installed(),
            reduced: state.reduced,
            applied_voice: config.voice.clone(),
            applied_bindings: bindings,
            applied_look: (config.appearance, system_dark),
            keep_on_top: false,
            config,
            config_path,
            state_path,
            state_saved: state.clone(),
            test_on: state.test_on,
            message,
            host,
            devices,
            engine,
            shared,
            controller,
            key_tx,
            hotkeys,
            vmic,
            pal,
            meters: (0.0, 0.0),
            settings_open: false,
            tab: Tab::Audio,
            settings_page: 0,
            edit: None,
            capture: None,
            closing: false,
            allow_close: false,
            is_admin: crate::platform::is_admin(),
            snapshot: crate::snapshot::Snapshot::from_env(),
        };
        app.apply_default_mic();
        app
    }

    pub fn runtime(&self) -> Runtime {
        self.controller.runtime.lock().unwrap().clone()
    }

    pub fn save(&mut self) {
        match self.config.save(&self.config_path) {
            Ok(()) => {
                self.history.mark_saved(&self.config);
                self.message =
                    crate::platform::set_autostart(self.config.general.start_with_windows)
                        .err()
                        .map(|e| {
                            (
                                format!("Saved, but the start at login was not changed: {e}"),
                                true,
                            )
                        });
            }
            Err(e) => self.message = Some((format!("Not saved: {e}"), true)),
        }
    }

    pub fn undo(&mut self) {
        self.history.undo(&mut self.config);
    }

    /// Re-reads the device lists (and restarts the sound if a device came back).
    pub fn refresh_devices(&mut self) {
        self.devices = audio::device_names(&self.host);
        if let virtual_mic::Status::CableFound | virtual_mic::Status::CableMissing =
            self.vmic.status
        {
            self.vmic = VirtualMic::setup(&self.config.audio.virtual_mic, &self.devices.1);
        }
        self.restart_engine();
    }

    fn restart_engine(&mut self) {
        let routing = routing(&self.config, &self.vmic.status);
        self.engine
            .start(&self.host, &routing, &self.config.voice.effect_args());
        self.applied.routing = routing;
        // The capture follows the engine's sample rate.
        self.programs.nudge();
    }

    /// Captures `program` for the virtual mic, or nothing.
    pub fn set_program(&mut self, program: Option<Program>) {
        self.programs
            .capture(program.as_ref().map(|p| p.key.clone()));
        self.program = program;
    }

    /// Makes the virtual mic the system's default mic, or gives the old
    /// default back, as the settings say. Only when that or the virtual mic changed.
    fn apply_default_mic(&mut self) {
        let wanted = (
            self.config.audio.virtual_mic_default,
            self.vmic.status.clone(),
        );
        if self.applied.default_mic.as_ref() == Some(&wanted) {
            return;
        }
        self.applied.default_mic = Some(wanted);
        let ours = crate::default_mic::virtual_mic(&self.host);
        let now = crate::default_mic::current(&self.host);
        self.default_mic_problem = None;
        if self.config.audio.virtual_mic_default {
            let Some(ours) = ours else {
                self.default_mic_problem = Some("No virtual mic to make the default".into());
                return;
            };
            if now.as_ref() == Some(&ours) {
                return;
            }
            // Kept from a crash, the old default is still the one to give back.
            if self.replaced_default_mic.is_none() {
                self.replaced_default_mic = now;
            }
            if let Err(e) = crate::default_mic::set(&ours) {
                self.default_mic_problem = Some(format!("Not made the default: {e}"));
            }
        } else {
            self.restore_default_mic(ours, now);
        }
    }

    /// Gives the old default mic back, unless someone picked another one meanwhile.
    fn restore_default_mic(&mut self, ours: Option<String>, now: Option<String>) {
        let Some(old) = self.replaced_default_mic.take() else {
            return;
        };
        if ours.is_none() || now == ours {
            let _ = crate::default_mic::set(&old);
        }
    }

    /// Starts listening for the next key press for `binding`.
    pub fn start_capture(&mut self, binding: Binding) {
        let (tx, rx) = channel();
        if self.hotkeys.is_running() {
            self.controller.capture_next(tx);
        }
        self.capture = Some((binding, rx));
    }

    /// Whether keys typed in Intercom's own windows must be read from egui:
    /// only when the global keys can't hear every keyboard. When they can,
    /// they already hear those keys, and they tell the numpad from the
    /// digits, which egui doesn't (it would turn Numpad 1 into "1").
    pub fn reads_window_keys(&self) -> bool {
        !self.hotkeys.is_running() || self.hotkeys.needs_permission()
    }

    /// Ends the capture with `key`. Esc keeps the old key.
    pub fn finish_capture(&mut self, key: Key) {
        if let Some((binding, _)) = &self.capture
            && key != Key::Escape
        {
            binding.set(&mut self.config, key);
        }
        self.cancel_capture();
    }

    pub fn cancel_capture(&mut self) {
        self.controller.cancel_capture();
        self.capture = None;
    }

    /// Linux: tries reading the keyboards again (after a fix of the permissions).
    pub fn retry_hotkeys(&mut self) {
        self.hotkeys = hotkeys::start(self.key_tx.clone());
    }

    /// Everything that is not drawing: applying changes, saving the state.
    fn every_frame(&mut self, ctx: &egui::Context) {
        self.engine.collect_garbage();

        // The finished edit becomes one undo step.
        let idle = !ctx.input(|i| i.pointer.any_down()) && ctx.memory(|m| m.focused().is_none());
        self.history.observe(&self.config, idle);

        // The look.
        let system_dark = ctx.system_theme() != Some(egui::Theme::Light);
        if self.applied_look != (self.config.appearance, system_dark) {
            self.applied_look = (self.config.appearance, system_dark);
            self.pal = Palette::new(&self.config.appearance, system_dark);
            self.pal.apply(ctx);
        }
        if self.keep_on_top != self.config.general.keep_on_top {
            self.keep_on_top = self.config.general.keep_on_top;
            let level = if self.keep_on_top {
                egui::WindowLevel::AlwaysOnTop
            } else {
                egui::WindowLevel::Normal
            };
            ctx.send_viewport_cmd_to(
                egui::ViewportId::ROOT,
                egui::ViewportCommand::WindowLevel(level),
            );
        }

        // Live values.
        self.shared
            .headset_volume
            .set(self.config.audio.headset_volume);
        self.shared.test_on.store(self.test_on, Ordering::Relaxed);
        self.shared
            .gate_on
            .store(self.config.audio.noise_gate, Ordering::Relaxed);
        self.shared
            .gate_margin
            .set(self.config.audio.gate_margin_db);
        self.shared.program_volume.set(self.program_volume);
        // Turning the voice changer on (button or key) stops the capture.
        let voice_on = self.shared.voice_on.load(Ordering::Relaxed);
        if voice_on && !self.voice_was_on && self.program.is_some() {
            self.set_program(None);
        }
        self.voice_was_on = voice_on;
        if self.config.voice != self.applied_voice {
            self.applied_voice = self.config.voice.clone();
            self.engine.set_effect(&self.config.voice.effect_args());
        }
        let bindings = Bindings {
            hotkeys: self.config.hotkeys.clone(),
            pages: self.config.pages.clone(),
            voice: self.config.voice.clone(),
            focus_only: self.config.general.focus_only,
            focus_program: self.config.general.focus_program.clone(),
        };
        if bindings.hotkeys != self.applied_bindings.hotkeys
            || bindings.pages != self.applied_bindings.pages
            || bindings.voice != self.applied_bindings.voice
            || bindings.focus_only != self.applied_bindings.focus_only
            || bindings.focus_program != self.applied_bindings.focus_program
        {
            *self.controller.bindings.write().unwrap() = bindings.clone();
            self.applied_bindings = bindings;
            let mut runtime = self.controller.runtime.lock().unwrap();
            runtime.page = runtime.page.min(self.config.pages.len().saturating_sub(1));
        }

        // Auto-click and drift. What the rate and mode keys changed becomes
        // an ordinary (unsaved, undoable) change of the settings.
        let live = self.mouse.live();
        if live.key_changes != self.mouse_key_changes {
            self.mouse_key_changes = live.key_changes;
            self.config.autoclick.rate = live.rate;
            self.config.autoclick.mode = live.mode;
            self.applied_mouse.autoclick.rate = live.rate;
            self.applied_mouse.autoclick.mode = live.mode;
        }
        let mouse_settings = mouse::Settings::of(&self.config);
        if mouse_settings != self.applied_mouse {
            self.mouse.configure(mouse_settings.clone());
            self.applied_mouse = mouse_settings;
        }

        // Devices: only once the edit is finished, since reopening takes a moment.
        if idle {
            self.vmic
                .set_keep(self.config.audio.virtual_mic.keep_after_close);
            let vm = &self.config.audio.virtual_mic;
            let vm_changed = vm.name != self.applied.virtual_mic.name
                || vm.create_on_start != self.applied.virtual_mic.create_on_start;
            if vm_changed {
                self.engine.stop();
                self.vmic.close();
                self.vmic = VirtualMic::setup(vm, &self.devices.1);
                self.applied.virtual_mic = vm.clone();
                self.devices = audio::device_names(&self.host);
                self.restart_engine();
            } else if routing(&self.config, &self.vmic.status) != self.applied.routing {
                self.restart_engine();
            }
            self.apply_default_mic();
        }

        // The state file: page, volumes, voice test.
        let state = self.state();
        if state != self.state_saved && idle {
            let _ = state.save(&self.state_path);
            self.state_saved = state;
        }

        // A key pressed for a "Change" button.
        if let Some((_, rx)) = &self.capture {
            // Keys typed in Intercom's own window count too: the global
            // listener may not be able to read the keyboard. (The Settings
            // window reads its own keys, in `settings::show`.)
            let typed = || typed_key(ctx).filter(|_| self.reads_window_keys());
            if let Some(key) = rx.try_recv().ok().or_else(typed) {
                self.finish_capture(key);
            }
        }

        // F11 toggles fullscreen, unless it is being picked for a "Change" button.
        if self.capture.is_none() && ctx.input(|i| i.key_pressed(egui::Key::F11)) {
            let fullscreen = ctx.input(|i| i.viewport().fullscreen.unwrap_or(false));
            ctx.send_viewport_cmd_to(
                egui::ViewportId::ROOT,
                egui::ViewportCommand::Fullscreen(!fullscreen),
            );
        }

        // Meters fall back slowly, so short peaks stay visible.
        let (mic, out) = self.shared.take_peaks();
        self.meters = (mic.max(self.meters.0 * 0.85), out.max(self.meters.1 * 0.85));
        if self.engine.is_running() {
            ctx.request_repaint_after(Duration::from_millis(40));
        }
    }

    /// What goes in the state file.
    fn state(&self) -> State {
        let runtime = self.runtime();
        State {
            page: runtime.page,
            sound_volume: runtime.sound_volume,
            test_on: self.test_on,
            program_volume: self.program_volume,
            replaced_default_mic: self.replaced_default_mic.clone(),
            reduced: self.reduced,
        }
    }

    /// Files dropped on a numpad cell are assigned to that key.
    fn take_dropped_file(&mut self, ctx: &egui::Context, cells: &[(Key, Rect)]) {
        let dropped: Vec<PathBuf> = ctx.input(|i| {
            i.raw
                .dropped_files
                .iter()
                .map(|f| f.path().to_path_buf())
                .collect()
        });
        let Some(file) = dropped.into_iter().next() else {
            return;
        };
        let Some(pos) = ctx.input(|i| i.pointer.latest_pos()) else {
            return;
        };
        if let Some((key, _)) = cells.iter().find(|(_, r)| r.contains(pos)) {
            let page = self.runtime().page;
            if let Some(p) = self.config.pages.get_mut(page) {
                p.keys.insert(
                    *key,
                    Sound {
                        files: vec![file],
                        volume: 1.0,
                    },
                );
            }
        }
    }

    /// Lets the window close even with unsaved changes.
    pub fn allow_close(&mut self) {
        self.allow_close = true;
    }

    fn close_check(&mut self, ctx: &egui::Context) {
        let wants_close = ctx.input(|i| i.viewport().close_requested());
        if wants_close
            && !self.allow_close
            && self.config.general.ask_before_close
            && self.history.unsaved(&self.config) > 0
        {
            ctx.send_viewport_cmd(egui::ViewportCommand::CancelClose);
            self.closing = true;
        }
        if !self.closing {
            return;
        }
        let pal = self.pal;
        egui::Modal::new(egui::Id::unique("close")).show(ctx, |ui| {
            ui.set_width(380.0);
            ui.heading("Save changes before closing?");
            ui.label(muted(
                &pal,
                format!("{} unsaved change(s).", self.history.unsaved(&self.config)),
            ));
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if ui.add(accent_button(&pal, "Save and close")).clicked() {
                    self.save();
                    self.allow_close = true;
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
                if ui.button("Close without saving").clicked() {
                    self.allow_close = true;
                    ctx.send_viewport_cmd(egui::ViewportCommand::Close);
                }
                if ui.button("Cancel").clicked() {
                    self.closing = false;
                }
            });
        });
    }

    // ---- The main window ---------------------------------------------------------

    /// The virtual mic's line for the top bar, only when something is wrong.
    /// (When it works, its state is shown in Settings › Audio.)
    fn vmic_problem(&self) -> Option<(egui::Color32, egui::Color32, String)> {
        let pal = self.pal;
        use virtual_mic::Status as S;
        match &self.vmic.status {
            S::CableMissing => Some((
                pal.warn,
                pal.warn_bg,
                "No virtual cable found. Others can't hear the voice changer or the sounds yet."
                    .into(),
            )),
            S::Failed(e) => Some((
                pal.bad,
                pal.warn_bg,
                format!("Virtual mic not created: {e}"),
            )),
            S::Ready { .. } | S::CableFound | S::Off => None,
        }
    }

    /// Whether the top bar has nothing to say.
    fn top_bar_empty(&self) -> bool {
        self.vmic_problem().is_none()
            && self.engine.status.problems.is_empty()
            && !matches!(
                self.hotkeys,
                hotkeys::Status::NoPermission | hotkeys::Status::Failed(_)
            )
            && !matches!(self.hotkeys, hotkeys::Status::Running { refused } if refused > 0)
            && !self.config.general.focus_only
            && self.message.is_none()
    }

    fn top_bar(&mut self, ui: &mut egui::Ui) {
        if self.top_bar_empty() {
            return;
        }
        let pal = self.pal;
        use virtual_mic::Status as S;
        let vmic = self.vmic_problem();
        let bg = vmic.as_ref().map_or(pal.panel, |(_, bg, _)| *bg);
        egui::Frame::new()
            .fill(bg)
            .inner_margin(Margin::symmetric(16, 8))
            .show(ui, |ui| {
                ui.set_width(ui.available_width());
                if let Some((color, _, text)) = vmic {
                    status_line(ui, color, text);
                }
                if self.vmic.status == S::CableMissing {
                    ui.horizontal(|ui| {
                        ui.hyperlink_to("Open download page", "https://vb-audio.com/Cable/");
                        if ui.button("Check again").clicked() {
                            self.refresh_devices();
                        }
                    });
                }
                for problem in &self.engine.status.problems {
                    status_line(ui, pal.warn, problem);
                }
                if self.hotkeys == hotkeys::Status::NoPermission {
                    status_line(
                        ui,
                        pal.warn,
                        "Global keys can't read the keyboard yet: see Settings › General",
                    );
                } else if let hotkeys::Status::Running { refused } = self.hotkeys
                    && refused > 0
                {
                    status_line(
                        ui,
                        pal.warn,
                        format!(
                            "Global keys can't read {refused} device(s), maybe your keyboard: see Settings › General"
                        ),
                    );
                } else if let hotkeys::Status::Failed(e) = &self.hotkeys {
                    status_line(ui, pal.warn, format!("Global keys off: {e}"));
                }
                if self.config.general.focus_only {
                    let program = &self.config.general.focus_program;
                    if self.controller.focus.lock().unwrap().in_front {
                        status_line(ui, pal.good, format!("Keys on: {program} is in front"));
                    } else {
                        status_line(ui, pal.muted, format!("Keys paused until {program} is in front"));
                    }
                }
                if let Some((text, bad)) = &self.message {
                    status_line(ui, if *bad { pal.bad } else { pal.good }, text);
                }
            });
    }

    /// The voice changer's ON/OFF button, with its key.
    fn voice_button(&mut self, ui: &mut egui::Ui, size: Vec2) {
        let pal = self.pal;
        let on = self.shared.voice_on.load(Ordering::Relaxed);
        let key = self.config.hotkeys.voice_toggle.label();
        let button = if on {
            accent_button(&pal, format!("ON   {key}"))
        } else {
            egui::Button::new(RichText::new(format!("OFF   {key}")).strong())
        };
        if ui.add(button.min_size(size)).clicked() {
            self.controller.apply(Action::ToggleVoice);
        }
    }

    fn voice_section(&mut self, ui: &mut egui::Ui) {
        let pal = self.pal;
        let reduced = self.reduced.voice;
        self.reduced.voice = reducible_card(ui, &pal, "Voice changer", reduced, |ui, part| {
            if part == Part::Title {
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if reduced {
                        ui.label(muted(&pal, effect_summary(&self.config.voice)));
                        self.voice_button(ui, Vec2::ZERO);
                    } else {
                        let st = &self.engine.status;
                        ui.label(muted(
                            &pal,
                            format!(
                                "{} → {}",
                                st.mic.as_deref().unwrap_or("no mic"),
                                st.voice_out.as_deref().unwrap_or("no virtual output")
                            ),
                        ));
                    }
                });
                return;
            }
            ui.add_space(2.0);
            ui.horizontal(|ui| {
                self.voice_button(ui, Vec2::new(110.0, 44.0));
                ui.vertical(|ui| {
                    ui.label(muted(&pal, "Effect"));
                    let v = &mut self.config.voice;
                    egui::ComboBox::from_id_salt("effect")
                        .width(ui.available_width())
                        .selected_text(effect_summary(v))
                        .show_ui(ui, |ui| {
                            for choice in EffectChoice::ALL {
                                ui.selectable_value(&mut v.effect, choice, choice.label());
                            }
                        });
                });
            });
            ui.add_space(6.0);
            // The mark on the mic's meter: where the noise gate opens.
            let gate = self
                .shared
                .noise_floor()
                .filter(|_| self.config.audio.noise_gate)
                .map(|floor| floor + self.config.audio.gate_margin_db);
            meter(ui, &pal, "Mic in", self.meters.0, pal.meter, gate);
            meter(ui, &pal, "Virtual mic", self.meters.1, pal.accent, None);
            ui.horizontal(|ui| {
                ui.checkbox(&mut self.test_on, "Test: hear my voice in the headset");
                let device = if self.config.audio.separate_test_device {
                    self.config.audio.test_device.as_deref()
                } else {
                    self.engine.status.headset.as_deref()
                };
                ui.label(muted(
                    &pal,
                    format!("· {}", device.unwrap_or("default output")),
                ));
            });
        });
    }

    fn sounds_section(&mut self, ui: &mut egui::Ui) {
        let pal = self.pal;
        let mut runtime = self.runtime();
        let pages = self.config.pages.len();
        let mut cells: Vec<(Key, Rect)> = Vec::new();
        let reduced = self.reduced.sounds;
        self.reduced.sounds = reducible_card(ui, &pal, "Soundboard", reduced, |ui, part| {
            if part == Part::Title {
                if reduced {
                    let name = self
                        .config
                        .pages
                        .get(runtime.page)
                        .map_or("", |p| p.name.as_str());
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.label(muted(
                            &pal,
                            format!(
                                "{name} · page {} of {pages} · {:.0} %",
                                runtime.page + 1,
                                runtime.sound_volume * 100.0
                            ),
                        ));
                    });
                }
                return;
            }
            // Page switcher.
            ui.horizontal(|ui| {
                let prev = format!("◀ {}", self.config.hotkeys.page_prev.label());
                if ui
                    .add_enabled(runtime.page > 0, egui::Button::new(prev))
                    .clicked()
                {
                    self.controller.apply(Action::PagePrev);
                }
                let name = self
                    .config
                    .pages
                    .get(runtime.page)
                    .map(|p| p.name.clone())
                    .unwrap_or_default();
                let next = format!("{} ▶", self.config.hotkeys.page_next.label());
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    if ui
                        .add_enabled(runtime.page + 1 < pages, egui::Button::new(next))
                        .clicked()
                    {
                        self.controller.apply(Action::PageNext);
                    }
                    ui.centered_and_justified(|ui| {
                        ui.label(
                            RichText::new(format!(
                                "{name}   ·   page {} of {pages}",
                                runtime.page + 1
                            ))
                            .strong(),
                        );
                    });
                });
            });
            ui.add_space(4.0);
            // Volume.
            ui.horizontal(|ui| {
                ui.label(muted(&pal, "Volume"));
                let mut percent = (runtime.sound_volume * 100.0).round();
                let slider = egui::Slider::new(&mut percent, 0.0..=100.0)
                    .suffix(" %")
                    .step_by(1.0);
                if ui.add(slider).changed() {
                    let mut rt = self.controller.runtime.lock().unwrap();
                    rt.sound_volume = percent / 100.0;
                    self.shared.sound_volume.set(rt.sound_volume);
                }
                chip(ui, &pal, self.config.hotkeys.volume_up.label());
                chip(ui, &pal, self.config.hotkeys.volume_down.label());
            });
            ui.add_space(6.0);
            runtime = self.runtime();
            cells = self.numpad(ui, runtime.page);
            if let Some(error) = &runtime.error {
                status_line(ui, pal.bad, error);
            }
        });
        self.take_dropped_file(ui.ctx(), &cells);
    }

    /// What the soundboard and the other programs are playing.
    fn now_playing_section(&mut self, ui: &mut egui::Ui) {
        let pal = self.pal;
        let tracks = self.media.tracks();
        let mut command = None;
        let reduced = self.reduced.now_playing;
        self.reduced.now_playing = reducible_card(ui, &pal, "Now playing", reduced, |ui, part| {
            if part == Part::Title {
                if reduced {
                    let playing = match self.engine.player.now_playing() {
                        Some((title, _, _)) => title,
                        None => tracks.first().map_or("Nothing is playing".into(), |t| {
                            format!("{} · {}", t.title, t.app)
                        }),
                    };
                    let text = match &self.program {
                        Some(p) => format!("Others hear {} · {playing}", p.name),
                        None => playing,
                    };
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        ui.add(egui::Label::new(muted(&pal, text)).truncate());
                    });
                }
                return;
            }
            self.program_picker(ui);
            ui.add_space(4.0);
            let sound = self.engine.player.now_playing();
            if sound.is_none() && tracks.is_empty() {
                ui.label(muted(&pal, "Nothing is playing."));
            }
            if let Some((title, at, length)) = sound {
                media_row(
                    ui,
                    &pal,
                    "Soundboard",
                    &title,
                    "",
                    Some((at, length)),
                    |ui| {
                        if ui.button("■ Stop").clicked() {
                            self.controller.apply(Action::Stop);
                        }
                    },
                );
            }
            for track in &tracks {
                let timeline = track.position.zip(track.length);
                media_row(
                    ui,
                    &pal,
                    &track.app,
                    &track.title,
                    &track.artist,
                    timeline,
                    |ui| {
                        // Right to left: the last button first.
                        if ui.button("⏭").on_hover_text("Next").clicked() {
                            command = Some((track.id.clone(), media::Command::Next));
                        }
                        let (icon, tip) = if track.playing {
                            ("⏸", "Pause")
                        } else {
                            ("▶", "Play")
                        };
                        if ui.button(icon).on_hover_text(tip).clicked() {
                            command = Some((track.id.clone(), media::Command::PlayPause));
                        }
                        if ui.button("⏮").on_hover_text("Previous").clicked() {
                            command = Some((track.id.clone(), media::Command::Previous));
                        }
                    },
                );
            }
        });
        if let Some((id, command)) = command {
            self.media.send(&id, command);
        }
        // The positions move on.
        if tracks.iter().any(|t| t.playing) {
            ui.ctx().request_repaint_after(Duration::from_millis(500));
        }
    }

    /// "Capture program audio": which program others hear too, and how loud.
    fn program_picker(&mut self, ui: &mut egui::Ui) {
        let pal = self.pal;
        let programs = self.programs.list();
        let mut choice = self.program.clone();
        ui.horizontal(|ui| {
            ui.label(muted(&pal, "Capture program audio:"));
            let selected = choice.as_ref().map_or("None", |p| p.name.as_str());
            egui::ComboBox::from_id_salt("program")
                .width(ui.available_width().min(240.0))
                .selected_text(selected)
                .show_ui(ui, |ui| {
                    ui.selectable_value(&mut choice, None, "None");
                    for program in &programs {
                        ui.selectable_value(&mut choice, Some(program.clone()), &program.name);
                    }
                    // Still captured when it plays again.
                    if let Some(current) = self.program.clone()
                        && !programs.iter().any(|p| p.key == current.key)
                    {
                        let label = format!("{} (not playing)", current.name);
                        ui.selectable_value(&mut choice, Some(current), label);
                    }
                })
                .response
                .on_hover_text("Others hear this program through your virtual mic. You keep hearing it as usual.");
        });
        if choice != self.program {
            self.set_program(choice);
        }
        if self.program.is_none() {
            return;
        }
        ui.horizontal(|ui| {
            ui.label(muted(&pal, "Volume for others"));
            let mut percent = (self.program_volume * 100.0).round();
            let slider = egui::Slider::new(&mut percent, 0.0..=100.0)
                .suffix(" %")
                .step_by(1.0);
            if ui.add(slider).changed() {
                self.program_volume = percent / 100.0;
            }
        });
        if let Some(problem) = self.programs.problem() {
            status_line(ui, pal.warn, problem);
        }
    }

    /// The numpad, laid out like a real one. Returns each cell's rectangle.
    fn numpad(&mut self, ui: &mut egui::Ui, page: usize) -> Vec<(Key, Rect)> {
        let pal = self.pal;
        // (key, column, row, columns wide, rows tall)
        const LAYOUT: [(Key, u8, u8, u8, u8); 17] = [
            (Key::NumLock, 0, 0, 1, 1),
            (Key::NumSlash, 1, 0, 1, 1),
            (Key::NumStar, 2, 0, 1, 1),
            (Key::NumMinus, 3, 0, 1, 1),
            (Key::Num7, 0, 1, 1, 1),
            (Key::Num8, 1, 1, 1, 1),
            (Key::Num9, 2, 1, 1, 1),
            (Key::NumPlus, 3, 1, 1, 2),
            (Key::Num4, 0, 2, 1, 1),
            (Key::Num5, 1, 2, 1, 1),
            (Key::Num6, 2, 2, 1, 1),
            (Key::Num1, 0, 3, 1, 1),
            (Key::Num2, 1, 3, 1, 1),
            (Key::Num3, 2, 3, 1, 1),
            (Key::NumEnter, 3, 3, 1, 2),
            (Key::Num0, 0, 4, 2, 1),
            (Key::NumDot, 2, 4, 1, 1),
        ];
        let gap = 8.0;
        let width = ui.available_width();
        let cell = Vec2::new((width - 3.0 * gap) / 4.0, 56.0);
        let (area, _) =
            ui.allocate_exact_size(Vec2::new(width, 5.0 * cell.y + 4.0 * gap), Sense::hover());
        let playing = self.engine.player.now_playing().map(|n| n.0);
        let hovering_file = ui.ctx().input(|i| !i.raw.hovered_files.is_empty());
        let mut cells = Vec::new();
        let mut open_edit = None;
        let mut play = None;
        for (key, col, row, w, h) in LAYOUT {
            let min = Pos2::new(
                area.min.x + col as f32 * (cell.x + gap),
                area.min.y + row as f32 * (cell.y + gap),
            );
            let size = Vec2::new(
                w as f32 * cell.x + (w - 1) as f32 * gap,
                h as f32 * cell.y + (h - 1) as f32 * gap,
            );
            let rect = Rect::from_min_size(min, size);
            let sound = self.config.pages.get(page).and_then(|p| p.keys.get(&key));
            let is_stop = key == self.config.hotkeys.stop_sound;
            // How many more files the key picks from at random.
            let mut more = 0;
            let (title, dim) = if key == Key::NumLock {
                ("not a sound key".to_string(), true)
            } else if is_stop {
                ("Stop sound".to_string(), false)
            } else if let Some(sound) = sound.filter(|s| !s.files.is_empty()) {
                more = sound.files.len() - 1;
                (sound.title(), false)
            } else if !Key::SOUND_KEYS.contains(&key) {
                ("not used".to_string(), true)
            } else {
                ("Empty · drop a file".to_string(), true)
            };
            let is_playing = sound.is_some_and(|s| {
                playing.as_ref().is_some_and(|p| {
                    s.files.iter().any(|f| {
                        Sound {
                            files: vec![f.clone()],
                            volume: 1.0,
                        }
                        .title()
                            == *p
                    })
                })
            });
            let response = ui.interact(rect, ui.scope_id().with(("cell", key)), Sense::click());
            let hover_drop = hovering_file && response.contains_pointer();
            let (fill, stroke) = if is_playing {
                (
                    pal.accent.gamma_multiply(0.22),
                    Stroke::new(2.0, pal.accent),
                )
            } else if hover_drop || response.hovered() {
                (pal.raised, Stroke::new(1.0, pal.accent))
            } else if dim {
                (pal.panel, Stroke::new(1.0, pal.border))
            } else {
                (pal.raised, Stroke::new(1.0, pal.border))
            };
            let painter = ui.painter_at(rect);
            painter.rect(
                rect,
                CornerRadius::same(8),
                fill,
                stroke,
                egui::StrokeKind::Inside,
            );
            let label = match (is_playing, more) {
                (true, _) => format!("{} · playing", key.label()),
                (false, 0) => key.label().to_string(),
                (false, n) => format!("{} · +{n} random", key.label()),
            };
            painter.text(
                rect.min + Vec2::new(10.0, 8.0),
                egui::Align2::LEFT_TOP,
                label,
                egui::FontId::monospace(12.0),
                pal.muted,
            );
            // One line, cut with "…" when too long.
            let color = if dim { pal.muted } else { pal.text };
            let format = egui::TextFormat::simple(egui::FontId::proportional(13.0), color);
            let mut job = egui::text::LayoutJob::single_section(title, format);
            job.wrap = egui::text::TextWrapping::truncate_at_width(rect.width() - 20.0);
            let galley = painter.layout_job(job);
            let text_pos = Pos2::new(rect.min.x + 10.0, rect.max.y - 8.0 - galley.size().y);
            painter.galley(text_pos, galley, color);
            if key != Key::NumLock {
                cells.push((key, rect));
                if response.clicked() {
                    play = Some(key);
                }
                if response.secondary_clicked() && Key::SOUND_KEYS.contains(&key) {
                    open_edit = Some(key);
                }
                response.on_hover_text(if Key::SOUND_KEYS.contains(&key) {
                    "Click to play · right-click to edit · drop a file to assign"
                } else {
                    "Stops the sound"
                });
            }
        }
        if let Some(key) = play {
            if key == self.config.hotkeys.stop_sound {
                self.controller.apply(Action::Stop);
            } else if Key::SOUND_KEYS.contains(&key) {
                self.controller.apply(Action::Play(key));
            }
        }
        if let Some(key) = open_edit {
            self.open_edit(page, key, false);
        }
        cells
    }

    pub fn open_edit(&mut self, page: usize, key: Key, in_settings: bool) {
        let draft = self
            .config
            .pages
            .get(page)
            .and_then(|p| p.keys.get(&key))
            .cloned()
            .unwrap_or_default();
        self.edit = Some(KeyEdit {
            page,
            key,
            draft,
            in_settings,
        });
    }

    fn input_cards(&mut self, ui: &mut egui::Ui) {
        let pal = self.pal;
        let a = &self.config.autoclick;
        let d = &self.config.drift;
        let live = self.mouse.live();
        let ready = self.mouse.status == mouse::Status::Ready;
        // What each card says under its numbers: off, a problem, or what it is doing.
        let state = |enabled: bool, active: Option<String>, idle: &str| {
            if !enabled {
                ("Off (Settings › Auto-click & drift)".to_string(), pal.muted)
            } else if !ready {
                (
                    "No virtual mouse: see Settings › Auto-click & drift".into(),
                    pal.warn,
                )
            } else if let Some(active) = active {
                (active, pal.accent)
            } else {
                (idle.to_string(), pal.muted)
            }
        };
        let clicking = state(
            a.enabled,
            live.clicking.then(|| "● Clicking".to_string()),
            "Ready",
        );
        let drifting = state(
            d.enabled,
            live.drift.map(|dir| match dir {
                mouse::Direction::Left => "● Drifting ←".to_string(),
                mouse::Direction::Right => "● Drifting →".to_string(),
            }),
            "Ready",
        );
        // Reduced: the number and the state on the title line.
        let summary =
            |ui: &mut egui::Ui, number: String, (text, color): &(String, egui::Color32)| {
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    ui.add(
                        egui::Label::new(RichText::new(format!("{number} · {text}")).color(*color))
                            .truncate(),
                    );
                });
            };
        let speed = d.px as f32 * 1000.0 / d.every_ms.max(1) as f32;
        let (click_reduced, drift_reduced) = (self.reduced.autoclick, self.reduced.drift);
        ui.columns(2, |cols| {
            self.reduced.autoclick = reducible_card(
                &mut cols[0],
                &pal,
                "Auto-click",
                click_reduced,
                |ui, part| {
                    if part == Part::Title {
                        if click_reduced {
                            summary(ui, format!("{} clicks/s", a.rate), &clicking);
                        }
                        return;
                    }
                    ui.label(
                        RichText::new(format!("{} clicks/s", a.rate))
                            .size(18.0)
                            .strong(),
                    );
                    ui.horizontal(|ui| {
                        chip(ui, &pal, a.trigger.label());
                        ui.label(muted(&pal, format!("{:?} button · {:?}", a.button, a.mode)));
                    });
                    ui.label(RichText::new(&clicking.0).color(clicking.1));
                },
            );
            self.reduced.drift = reducible_card(
                &mut cols[1],
                &pal,
                "Mouse drift",
                drift_reduced,
                |ui, part| {
                    if part == Part::Title {
                        if drift_reduced {
                            summary(ui, format!("{speed:.0} px/s"), &drifting);
                        }
                        return;
                    }
                    ui.label(
                        RichText::new(format!("{speed:.0} px/s"))
                            .size(18.0)
                            .strong(),
                    );
                    ui.horizontal(|ui| {
                        chip(ui, &pal, self.config.hotkeys.drift_left.label());
                        chip(ui, &pal, self.config.hotkeys.drift_right.label());
                        ui.label(muted(&pal, format!("{} px every {} ms", d.px, d.every_ms)));
                    });
                    ui.label(RichText::new(&drifting.0).color(drifting.1));
                },
            );
        });
    }

    pub fn bottom_bar(&mut self, ui: &mut egui::Ui, settings_button: bool) {
        let pal = self.pal;
        egui::Frame::new()
            .fill(pal.bar)
            .inner_margin(Margin::symmetric(16, 10))
            .show(ui, |ui| {
                ui.set_width(ui.available_width());
                ui.horizontal(|ui| {
                    let conflicts = self.config.conflicts();
                    let unsaved = self.history.unsaved(&self.config);
                    let save = ui
                        .add_enabled(
                            conflicts.is_empty() && unsaved > 0,
                            accent_button(&pal, "Save"),
                        )
                        .on_disabled_hover_text(if conflicts.is_empty() {
                            "Nothing to save"
                        } else {
                            "Fix the key conflicts first"
                        });
                    if save.clicked() {
                        self.save();
                    }
                    if ui
                        .add_enabled(
                            self.history.can_undo(&self.config),
                            egui::Button::new("↶ Undo"),
                        )
                        .clicked()
                    {
                        self.undo();
                    }
                    if !conflicts.is_empty() {
                        ui.label(
                            RichText::new(format!("{} key conflict(s)", conflicts.len()))
                                .color(pal.bad),
                        );
                    } else if unsaved > 0 {
                        ui.label(
                            RichText::new(format!("● {unsaved} unsaved change(s)")).color(pal.warn),
                        );
                    } else {
                        ui.label(muted(&pal, "All changes saved"));
                    }
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if settings_button {
                            if ui.button("⚙ Settings").clicked() {
                                self.settings_open = true;
                            }
                        } else if ui.button("Close").clicked() {
                            self.settings_open = false;
                        }
                    });
                });
            });
    }
}

impl eframe::App for App {
    fn ui(&mut self, ui: &mut egui::Ui, _frame: &mut eframe::Frame) {
        let ctx = ui.ctx().clone();
        self.every_frame(&ctx);
        let pal = self.pal;

        egui::Panel::top("status")
            .frame(egui::Frame::NONE)
            .show(ui, |ui| self.top_bar(ui));
        egui::Panel::bottom("bar")
            .frame(egui::Frame::NONE)
            .show(ui, |ui| self.bottom_bar(ui, true));
        egui::CentralPanel::default()
            .frame(
                egui::Frame::new()
                    .fill(pal.ground)
                    .inner_margin(Margin::same(14)),
            )
            .show(ui, |ui| {
                egui::ScrollArea::vertical()
                    .auto_shrink(false)
                    .show(ui, |ui| {
                        ui.spacing_mut().item_spacing.y = 10.0;
                        self.voice_section(ui);
                        // Side by side when the window has the room, else one under the other.
                        let wide = ctx.input(|i| {
                            let v = i.viewport();
                            v.maximized == Some(true) || v.fullscreen == Some(true)
                        });
                        if wide {
                            ui.columns(2, |cols| {
                                self.sounds_section(&mut cols[0]);
                                self.now_playing_section(&mut cols[1]);
                            });
                        } else {
                            self.sounds_section(ui);
                            self.now_playing_section(ui);
                        }
                        self.input_cards(ui);
                    });
            });

        if self.settings_open {
            crate::settings::show(self, &ctx);
        }
        if self.edit.as_ref().is_some_and(|e| !e.in_settings) {
            crate::settings::edit_dialog(self, &ctx);
        }
        self.close_check(&ctx);
        crate::snapshot::tick(self, &ctx);
    }

    fn on_exit(&mut self) {
        self.mouse.stop_all();
        self.programs.close();
        // The old default mic back before the virtual one disappears.
        let ours = crate::default_mic::virtual_mic(&self.host);
        let now = crate::default_mic::current(&self.host);
        self.restore_default_mic(ours, now);
        let _ = self.state().save(&self.state_path);
        // Stop the streams before the virtual devices disappear under them.
        self.engine.stop();
        self.vmic.close();
    }
}

/// The first key pressed in `ctx`'s window this frame, if Intercom knows it.
pub fn typed_key(ctx: &egui::Context) -> Option<Key> {
    ctx.input(|i| {
        i.events.iter().find_map(|e| match e {
            egui::Event::Key {
                key,
                pressed: true,
                repeat: false,
                ..
            } => Key::from_name(key.name()),
            _ => None,
        })
    })
}

/// Which devices to use, from the settings and the virtual mic's state.
pub fn routing(config: &Config, vmic: &virtual_mic::Status) -> Routing {
    let a = &config.audio;
    let virtual_out = vmic.output_name().map(String::from);
    let voice_out = a.voice_out.clone().or(virtual_out);
    Routing {
        mic: a.mic.clone(),
        sound_out: a.sound_out.clone().or_else(|| voice_out.clone()),
        voice_out,
        headset: a.headset.clone(),
        test_out: if a.separate_test_device {
            a.test_device.clone()
        } else {
            a.headset.clone()
        },
        block_ms: a.block_ms,
    }
}

pub fn effect_summary(v: &config::VoiceConfig) -> String {
    match v.effect {
        EffectChoice::Pitch => format!("Pitch · {:+} semitones", v.pitch),
        EffectChoice::Robot => format!("Robot · {} Hz", v.freq),
        other => format!("{} console", other.label()),
    }
}

/// One playing thing: where it plays, its title and artist, its progress,
/// and its buttons (`buttons` adds them right to left).
fn media_row(
    ui: &mut egui::Ui,
    pal: &Palette,
    source: &str,
    title: &str,
    artist: &str,
    timeline: Option<(f32, f32)>,
    buttons: impl FnOnce(&mut egui::Ui),
) {
    egui::Frame::new()
        .fill(pal.raised)
        .corner_radius(CornerRadius::same(10))
        .inner_margin(Margin::symmetric(12, 8))
        .show(ui, |ui| {
            ui.set_width(ui.available_width());
            ui.horizontal(|ui| {
                ui.label(RichText::new("▶").color(pal.accent));
                ui.label(muted(pal, source));
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), buttons);
            });
            ui.add(egui::Label::new(RichText::new(title).strong()).truncate());
            if !artist.is_empty() {
                ui.add(egui::Label::new(muted(pal, artist)).truncate());
            }
            if let Some((at, length)) = timeline {
                ui.horizontal(|ui| {
                    // Drawn like the meters: the bar's own background would
                    // have the row's color.
                    let width = (ui.available_width() - 90.0).max(40.0);
                    let (rect, _) = ui.allocate_exact_size(Vec2::new(width, 6.0), Sense::hover());
                    ui.painter()
                        .rect_filled(rect, CornerRadius::same(3), pal.panel);
                    let mut filled = rect;
                    filled.set_width(rect.width() * (at / length.max(0.001)).clamp(0.0, 1.0));
                    ui.painter()
                        .rect_filled(filled, CornerRadius::same(3), pal.accent);
                    ui.label(muted(pal, format!("{} / {}", time(at), time(length))));
                });
            }
        });
}

fn time(seconds: f32) -> String {
    let s = seconds.max(0.0) as u32;
    format!("{}:{:02}", s / 60, s % 60)
}
