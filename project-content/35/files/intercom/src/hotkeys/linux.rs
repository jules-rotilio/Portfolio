//! Linux: one thread per keyboard, reading its events from `/dev/input/event*`.
//!
//! Devices come and go (a USB keyboard, or a mouse that sends F13 through
//! its own keyboard interface), so the folder is scanned again every few
//! seconds.

use super::{KeyEvent, Status};
use crate::keys::Key;
use evdev::{Device, EventSummary, KeyCode};
use std::collections::HashSet;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::Sender;
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;

/// Devices being read, and devices that are not keyboards (not opened again).
#[derive(Default)]
struct Seen {
    reading: HashSet<PathBuf>,
    ignored: HashSet<PathBuf>,
}

/// One list for the whole program, so starting again (the "Check again"
/// button) never opens a device twice, which would double every key.
static SEEN: OnceLock<Arc<Mutex<Seen>>> = OnceLock::new();
static RESCANNING: AtomicBool = AtomicBool::new(false);

pub fn start(tx: Sender<KeyEvent>) -> Status {
    let seen = Arc::clone(SEEN.get_or_init(Default::default));
    let (reading, denied) = scan(&tx, &seen);
    // Devices refused now are tried again too: permissions can change.
    if !RESCANNING.swap(true, Ordering::Relaxed) {
        std::thread::Builder::new()
            .name("keyboard scan".into())
            .spawn(move || {
                loop {
                    std::thread::sleep(Duration::from_secs(3));
                    scan(&tx, &seen);
                }
            })
            .ok();
    }
    if reading > 0 {
        Status::Running { refused: denied }
    } else if denied > 0 {
        Status::NoPermission
    } else {
        Status::Failed("no keyboard found under /dev/input".into())
    }
}

/// Opens the keyboards not read yet. -> (keyboards being read, devices refused).
fn scan(tx: &Sender<KeyEvent>, seen: &Arc<Mutex<Seen>>) -> (usize, usize) {
    let Ok(entries) = std::fs::read_dir("/dev/input") else {
        return (0, 0);
    };
    let mut denied = 0;
    for entry in entries.flatten() {
        let path = entry.path();
        let is_event = path
            .file_name()
            .and_then(|n| n.to_str())
            .is_some_and(|n| n.starts_with("event"));
        {
            let seen = seen.lock().unwrap();
            if !is_event || seen.reading.contains(&path) || seen.ignored.contains(&path) {
                continue;
            }
        }
        let device = match Device::open(&path) {
            Ok(device) => device,
            Err(e) if e.kind() == std::io::ErrorKind::PermissionDenied => {
                denied += 1;
                continue;
            }
            Err(_) => continue,
        };
        let keyboard = device.supported_keys().is_some_and(|keys| {
            keys.contains(KeyCode::KEY_A)
                || keys.contains(KeyCode::KEY_KP1)
                || keys.contains(KeyCode::KEY_F13)
        });
        if !keyboard {
            seen.lock().unwrap().ignored.insert(path);
            continue;
        }
        seen.lock().unwrap().reading.insert(path.clone());
        let (tx, seen) = (tx.clone(), Arc::clone(seen));
        std::thread::Builder::new()
            .name("keyboard".into())
            .spawn(move || {
                read(device, &tx);
                // Unplugged (or Intercom is closing): forget it, so a rescan reopens it.
                seen.lock().unwrap().reading.remove(&path);
            })
            .ok();
    }
    (seen.lock().unwrap().reading.len(), denied)
}

fn read(mut device: Device, tx: &Sender<KeyEvent>) {
    loop {
        let Ok(events) = device.fetch_events() else {
            return;
        };
        for event in events {
            // value: 1 pressed, 0 released, 2 auto-repeat.
            if let EventSummary::Key(_, code, value) = event.destructure()
                && let Some(key) = Key::from_linux(code.code())
            {
                let event = KeyEvent {
                    key,
                    pressed: value != 0,
                    repeat: value == 2,
                };
                if tx.send(event).is_err() {
                    return;
                }
            }
        }
    }
}
