//! Global hotkeys: keys pressed anywhere, even while a game has the focus.
//!
//! Intercom only *listens*: every key still reaches the game. That way a
//! frozen Intercom can never block the keyboard.
//!
//! - Linux: reads every keyboard under `/dev/input` (works on X11 and
//!   Wayland alike; needs read access, see `Status::needs_permission`).
//! - Windows: a low-level keyboard hook, plus a hook on Intercom's own
//!   window thread for the keys typed while Intercom is in front.

use crate::keys::Key;
use std::sync::mpsc::Sender;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(windows)]
mod windows;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct KeyEvent {
    pub key: Key,
    pub pressed: bool,
    /// The key is held down and the system repeats it.
    pub repeat: bool,
}

#[derive(Clone, Debug, PartialEq)]
pub enum Status {
    /// Listening. `refused`: Linux devices that could not be read for lack of
    /// permission; the keyboard may be one of them.
    Running {
        refused: usize,
    },
    /// Linux: no keyboard can be read (the user is not in the `input` group).
    NoPermission,
    Failed(String),
}

impl Status {
    pub fn is_running(&self) -> bool {
        matches!(self, Status::Running { .. })
    }

    /// Some or all devices can't be read for lack of permission.
    pub fn needs_permission(&self) -> bool {
        match self {
            Status::NoPermission => true,
            Status::Running { refused } => *refused > 0,
            Status::Failed(_) => false,
        }
    }
}

/// Starts listening; key events go to `tx`. Call once, from the thread that
/// runs the windows.
pub fn start(tx: Sender<KeyEvent>) -> Status {
    #[cfg(target_os = "linux")]
    return linux::start(tx);
    #[cfg(windows)]
    return windows::start(tx);
    #[cfg(not(any(target_os = "linux", windows)))]
    {
        let _ = tx;
        Status::Failed("global keys are not supported on this system".into())
    }
}
