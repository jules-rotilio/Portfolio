//! The step-by-step undo list, and knowing what is unsaved.
//!
//! The window edits the config directly. Once an edit is finished (the mouse
//! button is up and no text box has focus), `observe` notices the config
//! differs from the last finished state and keeps that state as one undo
//! step. So dragging a slider, or typing a page name, is one step, not one
//! per frame or per letter.

use crate::config::Config;

/// Steps kept; older ones are forgotten.
const MAX_STEPS: usize = 200;

pub struct History {
    /// Finished states before the current one, oldest first.
    past: Vec<Config>,
    /// The last finished state.
    committed: Config,
    /// What is in the file.
    saved: Config,
    /// `past.len()` when the file was written, if that state is still in the list.
    saved_at: Option<usize>,
}

impl History {
    /// `config` is what was loaded from the file (or the defaults, if there is none).
    pub fn new(config: &Config) -> History {
        History {
            past: Vec::new(),
            committed: config.clone(),
            saved: config.clone(),
            saved_at: Some(0),
        }
    }

    /// Call once per frame. `idle`: no edit is in progress.
    pub fn observe(&mut self, current: &Config, idle: bool) {
        if idle && *current != self.committed {
            let previous = std::mem::replace(&mut self.committed, current.clone());
            self.past.push(previous);
            if self.past.len() > MAX_STEPS {
                self.past.remove(0);
                self.saved_at = self.saved_at.and_then(|i| i.checked_sub(1));
            }
        }
    }

    pub fn can_undo(&self, current: &Config) -> bool {
        !self.past.is_empty() || *current != self.committed
    }

    /// Goes back one step. An edit still in progress is the step undone first.
    pub fn undo(&mut self, current: &mut Config) {
        if *current != self.committed {
            *current = self.committed.clone();
        } else if let Some(previous) = self.past.pop() {
            *current = previous.clone();
            self.committed = previous;
        }
    }

    pub fn mark_saved(&mut self, current: &Config) {
        self.saved = current.clone();
        if *current == self.committed {
            self.saved_at = Some(self.past.len());
        } else {
            // Saved in the middle of an edit: the next `observe` adds a step.
            self.saved_at = Some(self.past.len() + 1);
        }
    }

    /// How many steps separate `current` from the file (0: nothing unsaved).
    pub fn unsaved(&self, current: &Config) -> usize {
        if *current == self.saved {
            return 0;
        }
        let pending = usize::from(*current != self.committed);
        let steps = match self.saved_at {
            Some(at) => self.past.len().abs_diff(at),
            None => self.past.len(),
        };
        (steps + pending).max(1)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::keys::Key;

    fn with_volume(v: f32) -> Config {
        let mut c = Config::first_start();
        c.audio.headset_volume = v;
        c
    }

    #[test]
    fn a_drag_is_one_step() {
        let mut config = with_volume(0.8);
        let mut history = History::new(&config);
        for v in [0.7, 0.6, 0.5] {
            config.audio.headset_volume = v;
            history.observe(&config, false); // mouse still down
        }
        history.observe(&config, true); // released
        assert_eq!(history.unsaved(&config), 1);
        history.undo(&mut config);
        assert_eq!(config.audio.headset_volume, 0.8);
        assert_eq!(history.unsaved(&config), 0);
    }

    #[test]
    fn undo_goes_back_one_step_at_a_time() {
        let mut config = Config::first_start();
        let mut history = History::new(&config);
        for key in [Key::F2, Key::F3, Key::F4] {
            config.hotkeys.voice_toggle = key;
            history.observe(&config, true);
        }
        assert_eq!(history.unsaved(&config), 3);
        history.undo(&mut config);
        assert_eq!(config.hotkeys.voice_toggle, Key::F3);
        history.undo(&mut config);
        assert_eq!(config.hotkeys.voice_toggle, Key::F2);
        history.undo(&mut config);
        assert_eq!(config.hotkeys.voice_toggle, Key::F9);
        assert!(!history.can_undo(&config));
        history.undo(&mut config); // nothing left: no change
        assert_eq!(config.hotkeys.voice_toggle, Key::F9);
    }

    #[test]
    fn saving_resets_the_unsaved_count_but_keeps_undo() {
        let mut config = with_volume(0.8);
        let mut history = History::new(&config);
        config.audio.headset_volume = 0.5;
        history.observe(&config, true);
        history.mark_saved(&config);
        assert_eq!(history.unsaved(&config), 0);
        history.undo(&mut config);
        assert_eq!(config.audio.headset_volume, 0.8);
        assert_eq!(history.unsaved(&config), 1);
    }
}
