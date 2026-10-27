//! Which program is in front (has the keyboard), for the "Only while a
//! program is in front" option.
//!
//! - Windows: the foreground window's program file.
//! - Linux: Wayland doesn't tell programs which window is in front, but
//!   games run through XWayland (Proton, and native games like SCP:SL), and
//!   the desktop keeps XWayland's "active window" up to date. So Intercom asks
//!   XWayland, then reads that window's process names from `/proc`. A native
//!   Wayland window in front (a browser, an editor) shows up as `None`: not
//!   the game, which is what the option needs.

/// The program in front: its names, the most readable first. A program has
/// several (its file, its process name, Wine's `.exe` name), and the user's
/// setting may match any of them.
#[derive(Clone, Debug, PartialEq)]
pub struct Front {
    pub names: Vec<String>,
    /// It is Intercom itself.
    pub is_us: bool,
}

impl Front {
    /// Is this the program called `wanted` (case doesn't matter)?
    pub fn is(&self, wanted: &str) -> bool {
        let wanted = wanted.trim().to_lowercase();
        !wanted.is_empty()
            && self.names.iter().any(|name| {
                let name = name.to_lowercase();
                // Linux cuts process names to 15 characters.
                name == wanted || (name.len() == 15 && wanted.starts_with(&name))
            })
    }

    pub fn name(&self) -> &str {
        self.names.first().map_or("?", |n| n.as_str())
    }
}

/// The last part of a path, with either kind of slash (Wine gives `C:\...\x.exe`).
fn file_name(path: &str) -> &str {
    path.rsplit(['/', '\\']).next().unwrap_or(path)
}

/// Adds `name` to `names` unless it is empty or already there.
fn push(names: &mut Vec<String>, name: &str) {
    let name = name.trim_matches(char::from(0)).trim();
    if !name.is_empty() && !names.iter().any(|n| n == name) {
        names.push(name.to_string());
    }
}

#[cfg(target_os = "linux")]
pub use linux::Watcher;
#[cfg(windows)]
pub use windows::Watcher;

/// Elsewhere: never knows.
#[cfg(not(any(target_os = "linux", windows)))]
pub struct Watcher;
#[cfg(not(any(target_os = "linux", windows)))]
impl Watcher {
    pub fn new() -> Watcher {
        Watcher
    }
    pub fn front(&mut self) -> Option<Front> {
        None
    }
}

#[cfg(target_os = "linux")]
mod linux {
    use super::{Front, file_name, push};
    use x11rb::connection::Connection;
    use x11rb::protocol::xproto::{Atom, AtomEnum, ConnectionExt, Window};
    use x11rb::rust_connection::RustConnection;

    /// A connection to XWayland, kept open (and reopened after an error).
    pub struct Watcher {
        x: Option<X>,
    }

    struct X {
        conn: RustConnection,
        root: Window,
        active: Atom,
        pid: Atom,
    }

    impl X {
        fn connect() -> Option<X> {
            let (conn, screen) = x11rb::connect(None).ok()?;
            let root = conn.setup().roots.get(screen)?.root;
            let atom = |name: &[u8]| Some(conn.intern_atom(false, name).ok()?.reply().ok()?.atom);
            let active = atom(b"_NET_ACTIVE_WINDOW")?;
            let pid = atom(b"_NET_WM_PID")?;
            Some(X {
                conn,
                root,
                active,
                pid,
            })
        }

        /// The 32-bit property `name` of `window` (a window id, a pid).
        fn number(&self, window: Window, name: Atom, kind: AtomEnum) -> Result<Option<u32>, ()> {
            let reply = self
                .conn
                .get_property(false, window, name, kind, 0, 1)
                .map_err(|_| ())?
                .reply()
                .map_err(|_| ())?;
            Ok(reply.value32().and_then(|mut v| v.next()))
        }

        /// Err: the connection broke.
        fn front(&self) -> Result<Option<Front>, ()> {
            let window = match self.number(self.root, self.active, AtomEnum::WINDOW)? {
                Some(w) if w != 0 => w,
                _ => return Ok(None),
            };
            let mut names = Vec::new();
            let pid = self
                .number(window, self.pid, AtomEnum::CARDINAL)
                .ok()
                .flatten();
            if let Some(pid) = pid {
                let proc = format!("/proc/{pid}");
                if let Ok(exe) = std::fs::read_link(format!("{proc}/exe")) {
                    push(&mut names, file_name(&exe.to_string_lossy()));
                }
                if let Ok(cmdline) = std::fs::read(format!("{proc}/cmdline")) {
                    let argv0 = cmdline.split(|b| *b == 0).next().unwrap_or_default();
                    push(&mut names, file_name(&String::from_utf8_lossy(argv0)));
                }
                if let Ok(comm) = std::fs::read_to_string(format!("{proc}/comm")) {
                    push(&mut names, &comm);
                }
            }
            // WM_CLASS: "instance\0Class\0", set by nearly every X program.
            if let Ok(reply) = self
                .conn
                .get_property(false, window, AtomEnum::WM_CLASS, AtomEnum::STRING, 0, 64)
                .map_err(|_| ())?
                .reply()
            {
                for part in reply.value.split(|b| *b == 0) {
                    push(&mut names, &String::from_utf8_lossy(part));
                }
            }
            // Wine runs a game through its own loader: put the .exe name first.
            if let Some(i) = names
                .iter()
                .position(|n| n.to_lowercase().ends_with(".exe"))
            {
                let exe = names.remove(i);
                names.insert(0, exe);
            }
            Ok(Some(Front {
                names,
                is_us: pid == Some(std::process::id()),
            }))
        }
    }

    impl Watcher {
        pub fn new() -> Watcher {
            Watcher { x: X::connect() }
        }

        pub fn front(&mut self) -> Option<Front> {
            if self.x.is_none() {
                self.x = X::connect();
            }
            match self.x.as_ref()?.front() {
                Ok(front) => front,
                Err(()) => {
                    self.x = None;
                    None
                }
            }
        }
    }
}

#[cfg(windows)]
mod windows {
    use super::{Front, file_name, push};
    use windows::Win32::Foundation::CloseHandle;
    use windows::Win32::System::Threading::{
        OpenProcess, PROCESS_NAME_WIN32, PROCESS_QUERY_LIMITED_INFORMATION,
        QueryFullProcessImageNameW,
    };
    use windows::Win32::UI::WindowsAndMessaging::{GetForegroundWindow, GetWindowThreadProcessId};
    use windows::core::PWSTR;

    pub struct Watcher;

    impl Watcher {
        pub fn new() -> Watcher {
            Watcher
        }

        pub fn front(&mut self) -> Option<Front> {
            let mut pid = 0u32;
            let mut buffer = [0u16; 1024];
            let mut len = buffer.len() as u32;
            // SAFETY: plain Win32 queries; the buffer and its length match.
            unsafe {
                let window = GetForegroundWindow();
                if window.is_invalid() {
                    return None;
                }
                GetWindowThreadProcessId(window, Some(&mut pid));
                let process = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, false, pid).ok()?;
                let ok = QueryFullProcessImageNameW(
                    process,
                    PROCESS_NAME_WIN32,
                    PWSTR(buffer.as_mut_ptr()),
                    &mut len,
                )
                .is_ok();
                let _ = CloseHandle(process);
                if !ok {
                    return None;
                }
            }
            let path = String::from_utf16_lossy(&buffer[..len as usize]);
            let mut names = Vec::new();
            push(&mut names, file_name(&path));
            Some(Front {
                names,
                is_us: pid == std::process::id(),
            })
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn matches_any_name_ignoring_case_and_cut_names() {
        let front = Front {
            names: vec!["SCPSL.exe".into(), "wine64-preloader".into()],
            is_us: false,
        };
        assert!(front.is("scpsl.EXE"));
        assert!(!front.is("SCPSL.x86_64"));
        assert!(!front.is(""));
        let cut = Front {
            names: vec!["VeryLongGameNam".into()],
            is_us: false,
        };
        assert!(cut.is("VeryLongGameName.x86_64"));
        assert_eq!(file_name(r"Z:\games\SCPSL.exe"), "SCPSL.exe");
    }
}
