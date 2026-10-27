//! Windows: clicks and moves with `SendInput`.
//!
//! Windows refuses them for a program in front that runs as administrator,
//! unless Intercom does too (see General › Windows).

use super::Status;
use super::clicker::Out;
use crate::config::MouseButton;
use windows::Win32::Media::{timeBeginPeriod, timeEndPeriod};
use windows::Win32::UI::Input::KeyboardAndMouse::{
    INPUT, INPUT_0, INPUT_MOUSE, MOUSE_EVENT_FLAGS, MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP,
    MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP, MOUSEEVENTF_MOVE, MOUSEEVENTF_RIGHTDOWN,
    MOUSEEVENTF_RIGHTUP, MOUSEINPUT, SendInput,
};

pub struct VirtualMouse {
    /// The 1 ms system timer is on.
    precise: bool,
}

fn flags(button: MouseButton, down: bool) -> MOUSE_EVENT_FLAGS {
    match (button, down) {
        (MouseButton::Left, true) => MOUSEEVENTF_LEFTDOWN,
        (MouseButton::Left, false) => MOUSEEVENTF_LEFTUP,
        (MouseButton::Right, true) => MOUSEEVENTF_RIGHTDOWN,
        (MouseButton::Right, false) => MOUSEEVENTF_RIGHTUP,
        (MouseButton::Middle, true) => MOUSEEVENTF_MIDDLEDOWN,
        (MouseButton::Middle, false) => MOUSEEVENTF_MIDDLEUP,
    }
}

impl VirtualMouse {
    pub fn open() -> Result<VirtualMouse, Status> {
        Ok(VirtualMouse { precise: false })
    }

    pub fn send(&mut self, outs: &[Out]) -> Result<(), String> {
        let inputs: Vec<INPUT> = outs
            .iter()
            .map(|out| {
                let (dx, dw_flags) = match *out {
                    Out::Button(button, down) => (0, flags(button, down)),
                    Out::Move(dx) => (dx, MOUSEEVENTF_MOVE),
                };
                INPUT {
                    r#type: INPUT_MOUSE,
                    Anonymous: INPUT_0 {
                        mi: MOUSEINPUT {
                            dx,
                            dwFlags: dw_flags,
                            ..Default::default()
                        },
                    },
                }
            })
            .collect();
        // SAFETY: plain Win32 call with a slice of fully built INPUTs.
        let sent = unsafe { SendInput(&inputs, std::mem::size_of::<INPUT>() as i32) };
        if sent as usize == inputs.len() {
            Ok(())
        } else {
            Err("Windows refused the clicks (is the program in front run as administrator?)".into())
        }
    }

    /// Asks for 1 ms timer steps while clicking or drifting, and gives them
    /// back when idle (they cost a little battery).
    pub fn set_busy(&mut self, busy: bool) {
        if busy != self.precise {
            self.precise = busy;
            // SAFETY: plain Win32 calls, always paired.
            unsafe {
                if busy {
                    timeBeginPeriod(1);
                } else {
                    timeEndPeriod(1);
                }
            }
        }
    }
}

impl Drop for VirtualMouse {
    fn drop(&mut self) {
        self.set_busy(false);
    }
}
