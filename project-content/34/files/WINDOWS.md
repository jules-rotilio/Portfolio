# Making valkyrie work on Windows

The plan for porting valkyrie to Windows while keeping Linux working. The steps are in
order: each one leaves something usable and testable on Windows, starting with the parts
that don't need the mouse.

## Status (2026-10-22)

Steps 1-7 are implemented. The code is split into what both systems share and what
each one runs: `hid_linux.py` / `hid_windows.py` (transport), `monitor_linux.py` /
`monitor_windows.py`, `autoclick_linux.py` / `autoclick_windows.py`, plus `paths.py`,
`instance.py`, `winsettings.py` and `winui.py`. Commands, settings files and messages
are the same on both; README.md notes the few differences. Every file is read and
written as UTF-8 on both systems.

Checked on Windows 11 with the mouse plugged in, VCFG not installed:

- the test suite: 117 tests pass on Windows, and also with `sys.platform` forced to
  `linux` (a stub `fcntl`), which exercises the Linux code paths; not yet re-run on a
  real Linux machine;
- reads through `hid_windows.py`: `valkyrie show --all` (1.3 s for 5 profiles), with
  each report's own size, as VCFG does; the 4 KB padding feared below is not needed;
- the input-report listener (timeouts, closing while a read waits);
- the window against the real mouse (offscreen), `valkyrie-monitor` and
  `valkyrie-autoclick` (start, single copy, `reload`, `check`, broken settings file).

Not checked yet:

- **writes on Windows**: no `set`/`apply` was sent from Windows; compare with USBPcap
  first, as described in step 2;
- input reports from the mouse's own buttons on Windows (needs pressing them while
  `valkyrie monitor` runs), and whether report 8 arrives on the vendor collection
  (`MI_02&COL02`) as expected;
- the auto-clicker's key hook and clicks with real F13-F24 presses, and the exact
  scan codes Qt gives for extended keys (step 4; `keys.SCANCODE_TO_HID` assumes
  0x100 + code);
- exact DPI on Windows (step 5.3): still off, with a message.

## What already works on Windows (before the port)

These modules are plain Python and move over unchanged: the protocol and safety checks
in `device.py` (`Mouse`, frames, `writable_ranges`, `FakeMouse`), plus `model.py`,
`pfd.py`, `store.py`, `host.py`, `ops.py`, `events.decode` and `keys.py` (though `ops.py`
and `events.py` could not be imported before step 1, because `device.py` imported `fcntl`). The GUI
(PyQt6) is portable too, except for the points in step 4.

What is Linux-only:

| Where | Linux mechanism | Windows replacement |
|---|---|---|
| `device.py` `find_hidraw`, `Hidraw` | `/sys/class/hidraw`, `fcntl.ioctl` HIDIOCSFEATURE/HIDIOCGFEATURE | SetupAPI + `HidD_SetFeature`/`HidD_GetFeature` (ctypes) |
| `device.py` `conflicting_programs` | `/proc/*/cmdline` | process list (`tasklist` or `CreateToolhelp32Snapshot`) |
| `events.py` `Listener` | non-blocking `os.read` on hidraw | `ReadFile` on the vendor HID handle, in a thread |
| `gui.py` `start_listening` | `QSocketNotifier` on the fd | a `QThread` emitting a signal per event |
| `gui.py` `event_key` | X/XKB keycode − 8 → `EVDEV_TO_HID` | Windows scan code → HID table |
| `cli.py` `monitor` | `select.select` on the fd | blocking read with a timeout |
| `monitor.py` | evdev grab + uinput proxy, `notify-send`, SIGHUP, `selectors` | tray app, VCFG's filter driver or nothing (see step 5) |
| `autoclick.py` | evdev grab, uinput, libpulse/aplay, SIGHUP, `selectors` | low-level keyboard hook, `SendInput`, `winsound` |
| `host.py`, `store.py`, pid files | `~/.config`, `~/.local/share`, `$XDG_RUNTIME_DIR` | `%APPDATA%`, `%LOCALAPPDATA%`, `tempfile.gettempdir()` |
| `udev/`, `*.service`, `*.desktop`, `bin/` | udev rule, systemd user units, menu entries | nothing (no permission needed), Startup folder, Start menu, `.exe` entry points |

## Step 1: make the package importable on Windows

Goal: `py -m valkyrie show --dry-run`, `pfd2txt.py`, the `.pfd` import/export and the
test suite run on Windows without a mouse.

1. Move the Linux transport out of `device.py` into `valkyrie/hid_linux.py` (`find_hidraw`,
   `Hidraw`, `_ioc`, the `fcntl` import). In `device.py`, pick the transport with
   `sys.platform` when one is needed, so importing `device` never imports `fcntl`.
   Do the same for the `fcntl` imports at the top of `monitor.py` and `autoclick.py`
   (later steps replace those modules' Linux parts anyway).
2. Add `valkyrie/paths.py` with one function per folder, used everywhere a path is built
   today:
   - config: `~/.config/valkyrie` on Linux, `%APPDATA%\valkyrie` on Windows
     (keep the `VALKYRIE_CONFIG_DIR` override from `host.py`)
   - backups: `~/.local/share/valkyrie/backups` / `%LOCALAPPDATA%\valkyrie\backups`
   - run dir for pid files: `$XDG_RUNTIME_DIR` (or `/tmp`) / `tempfile.gettempdir()`
3. Update the error messages that mention udev, `/dev/uinput` or `README.md` setup so
   they only say that on Linux.
4. Make the tests that need `/sys`, `/dev` or `fcntl` skip on Windows
   (`@unittest.skipUnless(sys.platform == 'linux', ...)`), then run
   `py -m unittest discover -s tests` on Windows. Everything that replays the usbmon
   captures through `FakeMouse` should pass unchanged, since it never touches the OS.

## Step 2: talk to the mouse (feature reports)

Goal: `valkyrie show --all`, `valkyrie backup` and a small write (`valkyrie set --color`)
work on Windows.

Write `valkyrie/hid_windows.py` with ctypes, doing exactly what VCFG does
(`re/FINDINGS.md` section 2, `HID_GetFeatureReport` 0x5edc68 / `HID_SetFeatureReport`
0x5ee08c in `re/decomp/uiHIDData.c`):

1. Enumerate HID interfaces: `HidD_GetHidGuid`, `SetupDiGetClassDevsW(DIGCF_PRESENT |
   DIGCF_DEVICEINTERFACE)`, `SetupDiEnumDeviceInterfaces`,
   `SetupDiGetDeviceInterfaceDetailW`.
2. Open each one with `CreateFileW(path, GENERIC_READ | GENERIC_WRITE,
   FILE_SHARE_READ | FILE_SHARE_WRITE, None, OPEN_EXISTING, ...)`. Shared access is what
   VCFG uses, so valkyrie and VMON can both have it open.
3. Keep the one with `HidD_GetAttributes` VID/PID `04d9:fc06` and `HidP_GetCaps`
   usage page `0xFFA0`, the same vendor interface `find_hidraw` finds through the report
   descriptor. On Windows, each top-level collection is its own device path, so the
   mouse and keyboard collections are simply skipped.
4. `set_feature(frame)` → `HidD_SetFeature(handle, frame, len(frame))`;
   `get_feature(rid)` → a buffer of `REPORT_SIZES[rid]` bytes with `buf[0] = rid`, then
   `HidD_GetFeature`. VCFG passes each report's own size, not the collection's
   `FeatureReportByteLength` (it only checks that the size isn't larger), so the frames
   `device.py` already builds are right as they are.
5. Map Windows errors to `DeviceError` (not found, unplugged, access denied).

I'd write this transport with ctypes rather than use the `hidapi` package: it adds no
dependency, and it is the exact path VCFG is known to use. Recent `hidapi` versions pad
feature reports to `FeatureReportByteLength` on Windows, which could mean 4 KB transfers
for every 16-byte command (a 1 KB report already takes 0.9 s, see `FINDINGS.md`).

Checking it:

- Read first: compare `valkyrie export` on Windows with the same export made on Linux.
- Before the first write, record VCFG and valkyrie doing the same change with
  [USBPcap](https://desowin.org/usbpcap/) + Wireshark and compare the frames, the way
  `captures/` was made with usbmon. The `--dry-run` output must match what goes out on
  the wire.
- `conflicting_programs()`: on Windows, list processes with `tasklist /fo csv /nh`
  (or `CreateToolhelp32Snapshot` through ctypes). Refuse writes only while **VCFG.exe**
  runs. `ETGMSrv.exe` is a service that is always running when VCFG is installed, and
  only reinstalls the driver. `VMON.exe` doesn't write the mouse's memory, so only warn
  about it (it re-applies its own Windows settings on profile switches; see step 5).

## Step 3: listen to the mouse's own buttons

Goal: `valkyrie monitor` and the window follow profile, DPI level and report rate
changes made on the mouse.

1. `hid_windows.Listener`: open the same vendor path (read access, shared) and read input
   reports with `ReadFile` in a background thread. Windows gives every open handle its
   own copy of each input report, so the GUI, the CLI and VMON can listen at once, like
   on hidraw. Use overlapped I/O or `CancelIoEx` so `close()` can stop a blocked read.
   Each report starts with the report ID, so `events.decode` works unchanged.
2. Give both Listeners the same interface: `read(timeout)` → list of `Event`, and
   `close()`. Then `cli.py`'s `monitor` loops on `read(timeout=...)` instead of
   `select.select`.
3. `gui.py`: replace the `QSocketNotifier` in `start_listening` with a `QThread` that
   calls `read` and emits a `pyqtSignal(object)` per event, connected to `mouse_event`.
   This works on Linux too, so there is a single code path.

## Step 4: the window

1. **Key capture** (`event_key`): on Windows, `QKeyEvent.nativeScanCode()` is the PS/2
   set-1 scan code, with the extended (E0) flag added for keys like RightCtrl and the
   arrows. Add a `SCANCODE_TO_HID` table to `keys.py` next to `EVDEV_TO_HID`, and pick one
   or the other by platform. Check the exact value of the extended flag on a real machine
   (`print(hex(event.nativeScanCode()))` for RightCtrl, Up and NumEnter). The keys Windows
   keeps for itself (Win+L, Ctrl+Alt+Del) must be ticked, as on Linux.
2. **VCFG pictures** (`find_vcfg_images`): also look in VCFG's install folder
   (`%ProgramFiles(x86)%\Drakkar Valkyrie\images\0409\background`, or the path in its
   uninstall registry key) before asking.
3. **Windows pointer settings**: on Windows, enable the group that is greyed out today
   (`_windows_box`) and apply its values on Apply and on **Make active**, as VCFG does
   (`FINDINGS.md` section 6):
   - pointer speed: `SystemParametersInfoW(SPI_SETMOUSESPEED, 0, speed, SPIF_SENDCHANGE)`
   - scroll lines: `SPI_SETWHEELSCROLLLINES`
   - acceleration: `SPI_SETMOUSE` with VCFG's 4 levels
     `{0,0,0}, {7,0,1}, {4,6,2}, {4,0,1}`
   - double-click: `SetDoubleClickTime(ms)`

   Put this in a small `valkyrie/winsettings.py` so the monitor can reuse it.

## Step 5: valkyrie-monitor

On Windows this replaces VMON, so it makes sense as a **tray app** (PyQt6 is already
needed for the window):

1. `QSystemTrayIcon` with a menu (Open settings, Reload, Quit), fed by the Listener
   thread from step 3. Notifications are `tray.showMessage(...)` instead of `notify-send`.
2. On a profile switch from the mouse, apply that profile's Windows pointer settings with
   `winsettings.py`. That is VMON's main job, and Linux doesn't need it.
3. **Exact DPI** (`exact_dpi = true`): Windows has no uinput, and grabbing one mouse
   needs a driver. Two possibilities, in order of preference:
   - Use VCFG's own filter driver `usbglcs1100302.sys` when it is installed: it already
     scales movement. Send the CPI table (IOCTL `0x80008004`, 0xee bytes) and the current
     stage (IOCTL `0x8000800c`) to `\\.\usbglcs1100302` like VMON's `Drv_SetCpiTable`
     (`FINDINGS.md` section 7). The table's byte layout still has to be read from
     `re/decomp/vmon_all.c`.
   - Otherwise, turn `exact_dpi` off on Windows with a clear message. A low-level mouse
     hook could rescale movement, but it would scale every mouse, and games that read
     raw input would ignore it.
4. Replace the SIGHUP reload (`send_reload`, the `signal.SIGHUP` handlers): on Windows,
   reload from the tray menu, and have the daemon notice changes to `monitor.toml` and
   `host.json` by their modification time (it already does this for `host.json` in
   `host_changed`). Use a named mutex (`CreateMutexW`) to keep a single instance instead
   of the pid file.
5. Start with the session: a shortcut in the Startup folder (`shell:startup`) to the
   `valkyrie-monitor` entry point from step 7.

## Step 6: valkyrie-autoclick

1. **Trigger keys**: install a low-level keyboard hook (`SetWindowsHookExW(WH_KEYBOARD_LL,
   ...)`) on a thread that runs a `GetMessageW` loop. The hook sees F13-F24 from the
   mouse, and returning 1 for the configured keys swallows them (`swallow = true`).
   The hook can't tell which device sent a key. That's fine for F13-F24, which normal
   keyboards don't have. A trigger key that a keyboard does have would be swallowed from
   every keyboard, so the docs should say so.
   The `[[click]]` key names map to Windows virtual-key codes (`VK_F13` = 0x7C ...), not
   evdev codes: add a `vk_code(name)` next to `evdev_code`.
2. **Clicks**: `SendInput` with `MOUSEEVENTF_LEFTDOWN/UP` (RIGHT, MIDDLE). No virtual
   device is needed. Windows blocks clicks sent into windows that run as administrator
   unless valkyrie-autoclick runs as administrator too, so the docs should mention it.
3. **Sounds**: `Sounds` already plays from a worker thread, so on Windows it can call
   `winsound.PlaySound(wav_bytes, winsound.SND_MEMORY)` synchronously from that thread
   (`SND_MEMORY` can't be combined with `SND_ASYNC`). Wrap the PCM in a WAV header with
   the `wave` module.
4. **Main loop**: `selectors` only works on sockets on Windows. Have the hook thread put
   key events in a `queue.Queue`, and let the click loop `get(timeout=...)` until the next
   click's deadline, which gives the same timing as the current `select` timeout.
5. Reload, single instance and autostart: as in step 5 (file modification time, named
   mutex, Startup folder). `notify-send` → a tray icon, or no notification at first.

## Step 7: install and run

1. Add a `pyproject.toml` with entry points, so `pip install .` creates real commands on
   both systems (`valkyrie.exe` etc. on Windows) and the `bin/` scripts are no longer
   needed there:
   ```toml
   [project.scripts]
   valkyrie = "valkyrie.cli:main"
   valkyrie-monitor = "valkyrie.monitor:main"
   valkyrie-autoclick = "valkyrie.autoclick:main"

   [project.gui-scripts]
   valkyrie-gui = "valkyrie.gui:main"     # no console window on Windows
   ```
   Include `valkyrie/data/*` as package data. Keep `requirements.txt` for a plain
   `pip install -r`.
2. Start menu entries: shortcuts to `valkyrie-gui.exe` (and the monitor) instead of the
   `.desktop` files.
3. For people without Python: build one folder with PyInstaller (`--windowed` for the GUI
   and the tray apps), and later an installer (Inno Setup, the same tool VCFG's setup
   uses).
4. README: a Windows section next to the Linux setup (no udev rule needed; what to do
   with VCFG, VMON and ETGMSrv; autostart).

## Step 8: living with VCFG's own software

If VCFG is installed, its parts run alongside valkyrie:

- **VMON.exe** (tray, starts with Windows) re-applies VCFG's Windows settings and CPI
  table on every profile switch, and shows its own OSD. Using valkyrie-monitor means
  removing VMON from startup, or uninstalling VCFG.
- **ETGMSrv.exe** (service) only keeps the filter driver installed. It can stay.
- **usbglcs1100302.sys** sits below the mouse interface (`MI_00`). Check that it doesn't
  change feature reports on the vendor interface (it shouldn't: VCFG's HID path goes
  through the normal HID stack). Without it, off-grid DPI values behave as on Linux
  without the monitor (the mouse uses the nearest step of 250).

## Testing on Windows

- Run `py -m unittest discover -s tests` on Windows from step 1 on, ideally in CI
  (GitHub Actions `windows-latest` and `ubuntu-latest`).
- Steps 2-6 need the real mouse: for each step, check against VCFG on the same machine
  (USBPcap for frames, VCFG's window for what it reads back).
- Keep running the full suite on Linux after each step: the refactoring in steps 1 and 3
  touches code that works there today.

## Open questions

- The CPI table layout for VCFG's driver (step 5), which is still to be found in `vmon_all.c`.
- Whether the driver installs at all on current Windows 11 with Secure Boot (it was
  signed in 2016).
- The exact extended-key flag in Qt's `nativeScanCode()` on Windows (step 4).
- Whether a GET_FEATURE of the large reports is as slow on Windows as on Linux.
