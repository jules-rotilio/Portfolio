//! Small system-specific helpers.

/// Windows: is Intercom running as administrator? (Elsewhere: false.)
/// Windows hides keys from, and blocks clicks into, a game running as
/// administrator unless Intercom runs that way too.
pub fn is_admin() -> bool {
    #[cfg(windows)]
    {
        use windows::Win32::Foundation::{CloseHandle, HANDLE};
        use windows::Win32::Security::{
            GetTokenInformation, TOKEN_ELEVATION, TOKEN_QUERY, TokenElevation,
        };
        use windows::Win32::System::Threading::{GetCurrentProcess, OpenProcessToken};
        let mut token = HANDLE::default();
        let mut elevation = TOKEN_ELEVATION::default();
        let mut size = 0u32;
        // SAFETY: plain Win32 queries on our own process; the buffer is the right size.
        unsafe {
            if OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token).is_err() {
                return false;
            }
            let ok = GetTokenInformation(
                token,
                TokenElevation,
                Some(&mut elevation as *mut _ as *mut _),
                std::mem::size_of::<TOKEN_ELEVATION>() as u32,
                &mut size,
            )
            .is_ok();
            let _ = CloseHandle(token);
            ok && elevation.TokenIsElevated != 0
        }
    }
    #[cfg(not(windows))]
    false
}

/// Windows: starts Intercom again as administrator (Windows asks first).
/// Returns true if the new copy started, so this one can close.
pub fn restart_as_admin() -> bool {
    #[cfg(windows)]
    {
        use windows::Win32::UI::Shell::ShellExecuteW;
        use windows::Win32::UI::WindowsAndMessaging::SW_SHOWNORMAL;
        use windows::core::{HSTRING, w};
        let Ok(exe) = std::env::current_exe() else {
            return false;
        };
        let exe = HSTRING::from(exe.as_os_str());
        // SAFETY: plain Win32 call; ShellExecute returns a value > 32 on success.
        let result = unsafe { ShellExecuteW(None, w!("runas"), &exe, None, None, SW_SHOWNORMAL) };
        result.0 as isize > 32
    }
    #[cfg(not(windows))]
    false
}

/// Starts Intercom when the user logs in, or stops doing so.
/// Windows: a value in the registry's `Run` key. Linux: a file in
/// `~/.config/autostart`, which every desktop reads.
pub fn set_autostart(on: bool) -> Result<(), String> {
    let exe = std::env::current_exe().map_err(|e| e.to_string())?;
    #[cfg(windows)]
    {
        use windows::Win32::System::Registry::{
            HKEY_CURRENT_USER, REG_SZ, RegDeleteKeyValueW, RegSetKeyValueW,
        };
        use windows::core::w;
        let run = w!("Software\\Microsoft\\Windows\\CurrentVersion\\Run");
        // SAFETY: plain registry calls; the data is a NUL-terminated UTF-16 string.
        let result = unsafe {
            if on {
                let command: Vec<u16> = format!("\"{}\"", exe.display())
                    .encode_utf16()
                    .chain([0])
                    .collect();
                RegSetKeyValueW(
                    HKEY_CURRENT_USER,
                    run,
                    w!("Intercom"),
                    REG_SZ.0,
                    Some(command.as_ptr().cast()),
                    (command.len() * 2) as u32,
                )
            } else {
                RegDeleteKeyValueW(HKEY_CURRENT_USER, run, w!("Intercom"))
            }
        };
        // Deleting a value that isn't there is fine.
        if result.is_ok() || (!on && result.0 == 2) {
            Ok(())
        } else {
            Err(format!("registry error {}", result.0))
        }
    }
    #[cfg(not(windows))]
    {
        let dir = directories::BaseDirs::new()
            .ok_or("no home folder")?
            .config_dir()
            .join("autostart");
        let file = dir.join("intercom.desktop");
        if on {
            std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
            let text = format!(
                "[Desktop Entry]\nType=Application\nName=Intercom\nExec=\"{}\"\nIcon=intercom\nX-GNOME-Autostart-enabled=true\n",
                exe.display()
            );
            std::fs::write(&file, text).map_err(|e| format!("{}: {e}", file.display()))
        } else {
            match std::fs::remove_file(&file) {
                Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
                    Err(format!("{}: {e}", file.display()))
                }
                _ => Ok(()),
            }
        }
    }
}
