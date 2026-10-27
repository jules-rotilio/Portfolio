//! Turns key presses into actions, on its own thread, so hotkeys work while
//! the window is hidden behind a game.
//!
//! `decide` (which action a key means) is a plain function, tested below;
//! `Controller::apply` then does it.

use crate::audio::Player;
use crate::config::{Hotkeys, Page, VoiceConfig};
use crate::focus::{self, Front};
use crate::hotkeys::KeyEvent;
use crate::keys::Key;
use crate::mouse;
use std::sync::atomic::Ordering;
use std::sync::mpsc::{Receiver, Sender};
use std::sync::{Arc, Mutex, RwLock};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Action {
    Play(Key),
    Stop,
    PageNext,
    PagePrev,
    VolumeUp,
    VolumeDown,
    ToggleVoice,
}

/// What the keys are bound to, copied from the config by the window.
#[derive(Clone, Default)]
pub struct Bindings {
    pub hotkeys: Hotkeys,
    pub pages: Vec<Page>,
    /// For the spoken "voice changer on/off".
    pub voice: VoiceConfig,
    /// Only act while `focus_program` is in front.
    pub focus_only: bool,
    pub focus_program: String,
}

/// The program in front, checked a few times per second.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Focus {
    pub front: Option<Front>,
    /// The last program in front other than Intercom, to offer it in Settings.
    pub last_other: Option<String>,
    /// `focus_program` is in front.
    pub in_front: bool,
}

/// What hotkeys change and the window shows: shared by both.
#[derive(Clone, Debug, PartialEq)]
pub struct Runtime {
    pub page: usize,
    pub sound_volume: f32,
    /// The last problem playing a sound, to show in the window.
    pub error: Option<String>,
}

/// Which action `event` asks for, if any.
pub fn decide(event: KeyEvent, hotkeys: &Hotkeys) -> Option<Action> {
    if !event.pressed {
        return None;
    }
    let key = event.key;
    let action = if key == hotkeys.volume_up {
        Action::VolumeUp
    } else if key == hotkeys.volume_down {
        Action::VolumeDown
    } else if event.repeat {
        // Holding a key only repeats the volume; one sound per press.
        return None;
    } else if key == hotkeys.stop_sound {
        Action::Stop
    } else if key == hotkeys.page_next {
        Action::PageNext
    } else if key == hotkeys.page_prev {
        Action::PagePrev
    } else if key == hotkeys.voice_toggle {
        Action::ToggleVoice
    } else if Key::SOUND_KEYS.contains(&key) {
        Action::Play(key)
    } else {
        return None;
    };
    Some(action)
}

pub struct Controller {
    pub bindings: RwLock<Bindings>,
    pub runtime: Mutex<Runtime>,
    pub focus: Mutex<Focus>,
    player: Arc<Player>,
    /// Auto-click and drift get every key too (they need the releases).
    mouse: mouse::Remote,
    /// While set, the next key press is sent here instead of acting
    /// (the "Change" button in the Hotkeys tab).
    capture: Mutex<Option<Sender<Key>>>,
    repaint: Box<dyn Fn() + Send + Sync>,
}

impl Controller {
    pub fn new(
        player: Arc<Player>,
        mouse: mouse::Remote,
        runtime: Runtime,
        repaint: impl Fn() + Send + Sync + 'static,
    ) -> Arc<Controller> {
        player.shared.sound_volume.set(runtime.sound_volume);
        Arc::new(Controller {
            bindings: RwLock::new(Bindings::default()),
            runtime: Mutex::new(runtime),
            focus: Mutex::new(Focus::default()),
            player,
            mouse,
            capture: Mutex::new(None),
            repaint: Box::new(repaint),
        })
    }

    /// Handles key events until the sender side is gone, and watches the
    /// program in front.
    pub fn run(self: Arc<Self>, events: Receiver<KeyEvent>) {
        let keys = Arc::clone(&self);
        std::thread::Builder::new()
            .name("hotkeys".into())
            .spawn(move || {
                for event in events {
                    keys.handle(event);
                }
            })
            .ok();
        let weak = Arc::downgrade(&self);
        drop(self);
        std::thread::Builder::new()
            .name("focus".into())
            .spawn(move || {
                let mut watcher = focus::Watcher::new();
                while let Some(controller) = weak.upgrade() {
                    controller.check_focus(watcher.front());
                    drop(controller);
                    std::thread::sleep(std::time::Duration::from_millis(250));
                }
            })
            .ok();
    }

    /// Notes the program in front. Leaving the chosen program stops the
    /// clicking, the drift and the sound.
    fn check_focus(&self, front: Option<Front>) {
        let (only, program) = {
            let b = self.bindings.read().unwrap();
            (b.focus_only, b.focus_program.clone())
        };
        let mut focus = self.focus.lock().unwrap();
        let in_front = front.as_ref().is_some_and(|f| f.is(&program));
        let mut last_other = focus.last_other.clone();
        if let Some(f) = front.as_ref().filter(|f| !f.is_us) {
            last_other = Some(f.name().to_string());
        }
        let now = Focus {
            front,
            last_other,
            in_front,
        };
        if *focus == now {
            return;
        }
        if only && focus.in_front && !in_front {
            self.mouse.stop_all();
            self.player.stop();
        }
        *focus = now;
        drop(focus);
        (self.repaint)();
    }

    /// The next key pressed goes to `to` instead of doing anything.
    pub fn capture_next(&self, to: Sender<Key>) {
        *self.capture.lock().unwrap() = Some(to);
    }

    pub fn cancel_capture(&self) {
        *self.capture.lock().unwrap() = None;
    }

    pub fn handle(&self, event: KeyEvent) {
        if event.pressed
            && !event.repeat
            && let Some(to) = self.capture.lock().unwrap().take()
        {
            let _ = to.send(event.key);
            (self.repaint)();
            return;
        }
        {
            let b = self.bindings.read().unwrap();
            if b.focus_only && !self.focus.lock().unwrap().in_front {
                return;
            }
        }
        self.mouse.key(event);
        let action = decide(event, &self.bindings.read().unwrap().hotkeys);
        if let Some(action) = action {
            self.apply(action);
            (self.repaint)();
        }
    }

    pub fn apply(&self, action: Action) {
        let mut runtime = self.runtime.lock().unwrap();
        let bindings = self.bindings.read().unwrap();
        let pages = bindings.pages.len().max(1);
        let step = bindings.hotkeys.volume_step as f32 / 100.0;
        match action {
            Action::Play(key) => {
                let sound = bindings
                    .pages
                    .get(runtime.page)
                    .and_then(|p| p.keys.get(&key));
                if let Some(sound) = sound {
                    runtime.error = self.player.play(sound, false).err();
                }
            }
            Action::Stop => self.player.stop(),
            Action::PageNext => runtime.page = (runtime.page + 1).min(pages - 1),
            Action::PagePrev => runtime.page = runtime.page.saturating_sub(1),
            Action::VolumeUp | Action::VolumeDown => {
                let sign = if action == Action::VolumeUp {
                    1.0
                } else {
                    -1.0
                };
                let volume = (runtime.sound_volume + sign * step).clamp(0.0, 1.0);
                // Round to whole percents, so ten steps of 10 % land exactly on 100 %.
                runtime.sound_volume = (volume * 100.0).round() / 100.0;
                self.player.shared.sound_volume.set(runtime.sound_volume);
            }
            Action::ToggleVoice => {
                let was_on = self
                    .player
                    .shared
                    .voice_on
                    .fetch_xor(true, Ordering::Relaxed);
                crate::announce::announce(&self.player, &bindings.voice, !was_on);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn press(key: Key) -> KeyEvent {
        KeyEvent {
            key,
            pressed: true,
            repeat: false,
        }
    }

    #[test]
    fn keys_map_to_their_actions() {
        let h = Hotkeys::default();
        assert_eq!(decide(press(Key::Num1), &h), Some(Action::Play(Key::Num1)));
        assert_eq!(
            decide(press(Key::NumEnter), &h),
            Some(Action::Play(Key::NumEnter))
        );
        assert_eq!(decide(press(Key::NumDot), &h), Some(Action::Stop));
        assert_eq!(decide(press(Key::PageDown), &h), Some(Action::PageNext));
        assert_eq!(decide(press(Key::F9), &h), Some(Action::ToggleVoice));
        assert_eq!(decide(press(Key::Q), &h), None);
    }

    #[test]
    fn releases_do_nothing_and_only_volume_repeats() {
        let h = Hotkeys::default();
        let release = KeyEvent {
            key: Key::Num1,
            pressed: false,
            repeat: false,
        };
        assert_eq!(decide(release, &h), None);
        let held = |key| KeyEvent {
            key,
            pressed: true,
            repeat: true,
        };
        assert_eq!(decide(held(Key::Up), &h), Some(Action::VolumeUp));
        assert_eq!(decide(held(Key::Num1), &h), None);
    }

    #[test]
    fn a_rebound_hotkey_wins_over_a_sound_key() {
        let h = Hotkeys {
            stop_sound: Key::Num0,
            ..Hotkeys::default()
        };
        assert_eq!(decide(press(Key::Num0), &h), Some(Action::Stop));
    }
}
