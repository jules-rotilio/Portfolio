//! Windows: a low-level keyboard hook (`WH_KEYBOARD_LL`), plus a hook on
//! Intercom's own window thread.
//!
//! Windows calls `hook` for every key, on the thread that installed it,
//! which must run a message loop. The hook returns `CallNextHookEx`, so the
//! key always goes on to the game.
//!
//! While one of Intercom's own windows has the focus, Windows skips the
//! low-level hook (seen on Windows 11). `window_hook` (`WH_KEYBOARD`, for the
//! window thread only) hears those keys instead. A key both hooks hear is
//! only sent once.

use super::{KeyEvent, Status};
use crate::keys::Key;
use std::cell::RefCell;
use std::collections::HashSet;
use std::sync::OnceLock;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::mpsc::{Sender, channel};
use std::time::Instant;
use windows::Win32::Foundation::{LPARAM, LRESULT, WPARAM};
use windows::Win32::System::LibraryLoader::GetModuleHandleW;
use windows::Win32::System::Threading::GetCurrentThreadId;
use windows::Win32::UI::WindowsAndMessaging::{
    CallNextHookEx, GetMessageW, HC_ACTION, KBDLLHOOKSTRUCT, LLKHF_EXTENDED, LLKHF_INJECTED, MSG,
    SetWindowsHookExW, WH_KEYBOARD, WH_KEYBOARD_LL, WM_KEYDOWN, WM_SYSKEYDOWN,
};

static SENDER: OnceLock<Sender<KeyEvent>> = OnceLock::new();

/// When the low-level hook last heard each key go down (index: the key code)
/// or up (index: 256 + the key code), in ms since `START`, plus one; 0 is never.
static HEARD: [AtomicU64; 512] = [const { AtomicU64::new(0) }; 512];
static START: OnceLock<Instant> = OnceLock::new();

/// `window_hook` drops a key the low-level hook heard this recently: both
/// see the same press, the low-level hook first.
const SAME_PRESS_MS: u64 = 100;

thread_local! {
    /// Keys held down, to tell a repeat from a new press.
    static DOWN: RefCell<HashSet<Key>> = RefCell::new(HashSet::new());
}

/// Call on the thread that runs the windows: `window_hook` is installed there.
pub fn start(tx: Sender<KeyEvent>) -> Status {
    if SENDER.set(tx).is_err() {
        return Status::Running { refused: 0 };
    }
    let (ready_tx, ready_rx) = channel();
    std::thread::Builder::new()
        .name("keyboard hook".into())
        .spawn(move || {
            // SAFETY: plain Win32 calls; `hook` matches the HOOKPROC signature.
            let hook = unsafe {
                let module = GetModuleHandleW(None).ok();
                SetWindowsHookExW(WH_KEYBOARD_LL, Some(hook), module.map(Into::into), 0)
            };
            let ok = hook.is_ok();
            let _ = ready_tx.send(hook.map(|_| ()).map_err(|e| e.to_string()));
            if !ok {
                return;
            }
            let mut msg = MSG::default();
            // SAFETY: the message loop the hook needs; runs until the program ends.
            while unsafe { GetMessageW(&mut msg, None, 0, 0) }.as_bool() {}
        })
        .ok();
    match ready_rx.recv() {
        Ok(Ok(())) => {
            // SAFETY: a hook for the calling thread only; `window_hook` matches HOOKPROC.
            // Without it, the keys still work whenever Intercom is not in front.
            let _ = unsafe {
                SetWindowsHookExW(WH_KEYBOARD, Some(window_hook), None, GetCurrentThreadId())
            };
            Status::Running { refused: 0 }
        }
        Ok(Err(e)) => Status::Failed(format!("keyboard hook: {e}")),
        Err(_) => Status::Failed("keyboard hook thread did not start".into()),
    }
}

/// Milliseconds since `START`, plus one, so 0 can mean "never".
fn now_ms() -> u64 {
    START.get_or_init(Instant::now).elapsed().as_millis() as u64 + 1
}

fn heard_slot(vk: u32, pressed: bool) -> &'static AtomicU64 {
    &HEARD[(vk & 0xFF) as usize + if pressed { 0 } else { 256 }]
}

fn send(key: Key, pressed: bool, repeat: bool) {
    if let Some(tx) = SENDER.get() {
        let _ = tx.send(KeyEvent {
            key,
            pressed,
            repeat,
        });
    }
}

unsafe extern "system" fn hook(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    if code == HC_ACTION as i32 {
        // SAFETY: for WH_KEYBOARD_LL, lparam points to a KBDLLHOOKSTRUCT.
        let kb = unsafe { &*(lparam.0 as *const KBDLLHOOKSTRUCT) };
        // Keys Intercom itself sends (later: auto-click) are not hotkeys.
        let injected = kb.flags.0 & LLKHF_INJECTED.0 != 0;
        let extended = kb.flags.0 & LLKHF_EXTENDED.0 != 0;
        if !injected && let Some(key) = Key::from_windows(kb.vkCode, extended) {
            let message = wparam.0 as u32;
            let pressed = message == WM_KEYDOWN || message == WM_SYSKEYDOWN;
            heard_slot(kb.vkCode, pressed).store(now_ms(), Ordering::Relaxed);
            let repeat = DOWN.with_borrow_mut(|down| {
                if pressed {
                    !down.insert(key)
                } else {
                    down.remove(&key);
                    false
                }
            });
            send(key, pressed, repeat);
        }
    }
    // SAFETY: passes the key on to the next hook and to the game.
    unsafe { CallNextHookEx(None, code, wparam, lparam) }
}

/// Keys for Intercom's own windows. wparam: the key code. lparam bits: 24
/// extended key, 30 the key was already down, 31 the key is being released.
unsafe extern "system" fn window_hook(code: i32, wparam: WPARAM, lparam: LPARAM) -> LRESULT {
    // HC_ACTION only: HC_NOREMOVE is the same key, peeked at without taking it.
    if code == HC_ACTION as i32 {
        let vk = wparam.0 as u32;
        let flags = lparam.0 as u32;
        let extended = flags & (1 << 24) != 0;
        let pressed = flags & (1 << 31) == 0;
        let repeat = pressed && flags & (1 << 30) != 0;
        let heard = heard_slot(vk, pressed).load(Ordering::Relaxed);
        let low_level_had_it = heard != 0 && now_ms() - heard < SAME_PRESS_MS;
        if !low_level_had_it && let Some(key) = Key::from_windows(vk, extended) {
            send(key, pressed, repeat);
        }
    }
    // SAFETY: passes the key on to the window.
    unsafe { CallNextHookEx(None, code, wparam, lparam) }
}
