//! Linux: a virtual mouse made through `/dev/uinput`. The desktop sees it as
//! one more mouse, so clicks and moves work on X11 and Wayland alike, and in
//! games that read the mouse directly.

use super::Status;
use super::clicker::Out;
use crate::config::MouseButton;
use evdev::uinput::VirtualDevice;
use evdev::{AttributeSet, BusType, EventType, InputEvent, InputId, KeyCode, RelativeAxisCode};
use std::io::ErrorKind;

pub struct VirtualMouse(VirtualDevice);

fn code(button: MouseButton) -> KeyCode {
    match button {
        MouseButton::Left => KeyCode::BTN_LEFT,
        MouseButton::Right => KeyCode::BTN_RIGHT,
        MouseButton::Middle => KeyCode::BTN_MIDDLE,
    }
}

impl VirtualMouse {
    pub fn open() -> Result<VirtualMouse, Status> {
        let buttons =
            AttributeSet::from_iter([KeyCode::BTN_LEFT, KeyCode::BTN_RIGHT, KeyCode::BTN_MIDDLE]);
        // Moving axes are what makes the desktop treat it as a mouse.
        let axes = AttributeSet::from_iter([RelativeAxisCode::REL_X, RelativeAxisCode::REL_Y]);
        let device = VirtualDevice::builder().and_then(|b| {
            b.name("Intercom mouse")
                .input_id(InputId::new(BusType::BUS_VIRTUAL, 0, 0, 1))
                .with_keys(&buttons)?
                .with_relative_axes(&axes)?
                .build()
        });
        match device {
            Ok(device) => Ok(VirtualMouse(device)),
            Err(e) if e.kind() == ErrorKind::PermissionDenied => Err(Status::NoPermission),
            Err(e) if e.kind() == ErrorKind::NotFound => Err(Status::Failed(
                "/dev/uinput is missing (load it with: sudo modprobe uinput)".into(),
            )),
            Err(e) => Err(Status::Failed(format!("/dev/uinput: {e}"))),
        }
    }

    /// Sends the events as one report.
    pub fn send(&mut self, outs: &[Out]) -> Result<(), String> {
        let events: Vec<InputEvent> = outs
            .iter()
            .map(|out| match *out {
                Out::Button(button, down) => {
                    InputEvent::new(EventType::KEY.0, code(button).0, down as i32)
                }
                Out::Move(dx) => {
                    InputEvent::new(EventType::RELATIVE.0, RelativeAxisCode::REL_X.0, dx)
                }
            })
            .collect();
        self.0
            .emit(&events)
            .map_err(|e| format!("virtual mouse: {e}"))
    }

    /// Linux's timers are precise already.
    pub fn set_busy(&mut self, _busy: bool) {}
}
