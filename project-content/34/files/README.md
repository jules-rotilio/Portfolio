# valkyrie: configure the Konix Drakkar Valkyrie mouse on Linux and Windows

A replacement for VCFG.exe, on Linux and on Windows. It talks to the mouse (USB `04d9:fc06`)
directly and stores the same settings VCFG does, using byte-identical USB traffic:

- the 5 profiles stored in the mouse, and which one is active
- DPI levels (250 to 4000; each level on or off), polling rate (125 to 1000 Hz)
- light colour, brightness and breathing
- the actions of buttons 1-13 (button 14 is the profile switch under the mouse),
  including shortcuts with two keys (Ctrl+K+C)
- macros in 30 slots (keys, mouse clicks, delays, loops, repeat while held)
- importing and exporting VCFG `.pfd` profile files
- VCFG's factory settings
- `valkyrie-monitor`, which does on Linux what VCFG's tray program VMON does on Windows:
  a notification when the profile, DPI level or report rate is changed with the mouse's
  own buttons, and exact DPI values between the mouse's steps of 250

The mouse itself only has DPI steps of 250. Like VCFG, valkyrie accepts values in steps of
50 (1900, say): the mouse then uses the nearest step (2000), and `valkyrie-monitor` scales
the pointer movement so the value asked for is exact, as VCFG's driver does on Windows.
Separate X and Y values work the same way: the mouse uses the larger one for both axes.

Acceleration, pointer speed, scroll speed and double-click speed are not stored in the
mouse: VCFG and VMON set them in Windows for each profile. On Windows, valkyrie does the
same (the window on Apply and Make active, `valkyrie-monitor` on a profile switch). On
Linux it shows them greyed out, keeps them from imported `.pfd` files and the factory
settings, and writes them to exported `.pfd` files; use your desktop's mouse settings.

The command line needs only the Python 3 standard library (3.11 or newer); the window needs
PyQt6 (`sudo apt install python3-pyqt6`, or `pip install -r requirements.txt` in a virtualenv).

## Setup on Linux

Allow your user to open the mouse's hidraw device (once):

```
sudo cp udev/70-drakkar-valkyrie.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Run it from this folder as `bin/valkyrie`, or put it on your PATH:

```
ln -s "$PWD/bin/valkyrie" ~/.local/bin/valkyrie
```

## Setup on Windows

Nothing to install for the mouse: valkyrie uses the HID driver Windows already has, like
VCFG. Run it from this folder with the `.cmd` launchers, which use the active virtualenv,
else `%USERPROFILE%\.venv`, else the `py` launcher:

```
bin\valkyrie show
bin\valkyrie-gui
```

Or install the commands into your virtualenv, so `valkyrie`, `valkyrie-gui`,
`valkyrie-monitor` and `valkyrie-autoclick` work anywhere it is active (this also works
on Linux):

```
pip install -e .[gui]
```

Everything below works the same on both systems; the differences are noted where they
are. Files go to `%APPDATA%\valkyrie` (settings) and `%LOCALAPPDATA%\valkyrie\backups`
instead of `~/.config/valkyrie` and `~/.local/share/valkyrie/backups`.

If VCFG is installed: close VCFG.exe before writing (valkyrie refuses while it runs; `--force`
overrides). VMON.exe can stay, but run either VMON or `valkyrie-monitor`, not both: each
re-applies its own pointer settings on a profile switch. ETGMSrv.exe only installs VCFG's
driver and can stay.

## The window

```
bin/valkyrie-gui
```

To add it to the application menu (and optionally the launcher to your PATH):

```
sed "s|@DIR@|$PWD|" valkyrie-gui.desktop > ~/.local/share/applications/valkyrie-gui.desktop
ln -s "$PWD/bin/valkyrie-gui" ~/.local/bin/valkyrie-gui
```

The Buttons tab shows VCFG's front and side pictures of the mouse: click a numbered button
to change it, hover a row to see where that button is. The pictures are read from the VCFG
folder (`Drakkar Valkyrie/images/0409/background` or `Official Drakkar Valkyrie/…`, next to
this one, or VCFG's install folder on Windows); if VCFG is elsewhere, use View → Locate
VCFG images….

Pick a profile at the top, change it in the tabs (Buttons, DPI and polling, Light, Macros),
then click **Apply**. Nothing is written before Apply, except the light preview, which
the mouse does not save. Changed profiles are marked with `*`; **Revert** forgets the
changes. **Make active** switches the mouse to the profile shown. **Factory settings…**
loads VCFG's factory settings into the profile shown or into all profiles (written by
Apply).

The window follows the mouse's own buttons: when you change profile, DPI level or report
rate on the mouse, it shows the new one. Apply keeps a DPI level picked on the mouse,
as VCFG does, unless you chose another one in the window.

In key dialogs, "Press a key…" captures the physical key you press, so it is right on
any layout. Shortcuts the desktop takes for itself (Alt+Tab, Win+L) must be ticked
instead of pressed.

## Command line

```
valkyrie show                       # active profile
valkyrie show --all                 # all 5 profiles (--json for JSON)
valkyrie profile 2                  # make profile 2 active

valkyrie set --dpi 3=1600 --dpi-default 3
valkyrie set --dpi 2=1900                   # the mouse uses 2000; exact with valkyrie-monitor
valkyrie set --dpi-off 5 --polling 1000
valkyrie set --color "#00aaff" --brightness high --breathing off
valkyrie set --profile 2 --button 10=key:Q --button 11=shortcut:Ctrl+Shift+Z
valkyrie set --button 6=shortcut:Ctrl+K+C   # two keys after the modifiers
valkyrie set --button 4=fire:left,3,10       # 3 left clicks, 10 ms apart
valkyrie actions                             # every action and key name

valkyrie macro 1 "A down, wait 50, A up, mouse:left down, mouse:left up" --button 9
valkyrie macro 2 "LeftCtrl down, C down, C up, LeftCtrl up" --button 12 --repeat

valkyrie export profiles.json       # editable JSON of all profiles and macros
valkyrie apply profiles.json --profile 5 --to 2
valkyrie import-pfd Configs/base.pfd --profile 5
valkyrie export-pfd Profile5.pfd --profile 5   # open in VCFG with LOAD FILE

valkyrie backup                     # raw copy, kept in ~/.local/share/valkyrie/backups/ (Windows: %LOCALAPPDATA%\valkyrie\backups)
valkyrie restore ~/.local/share/valkyrie/backups/20261014-233557.json

valkyrie factory-reset              # VCFG's factory settings, all profiles (--profile N: one)
valkyrie monitor                    # print what the mouse reports when its buttons are used
```

Every command that writes accepts `--dry-run`, which prints the exact USB frames
instead of sending them.

Key names follow the US keyboard layout because the mouse sends key positions: on an
AZERTY keyboard, `key:Q` types "a" and `key:A` types "q".

Exported `.pfd` files start from a VCFG-saved file (`valkyrie/data/template.pfd`) and
only change the known fields. Every action in VCFG's menus can be exported; media keys
VCFG has no entry for (Email, Calculator, My computer) are refused.

## valkyrie-monitor

```
bin/valkyrie-monitor                     # first run writes ~/.config/valkyrie/monitor.toml
```

```toml
notify = true        # notification for profile, DPI level and report-rate changes on the mouse
exact_dpi = false    # make DPI values between the mouse's steps of 250 exact (Linux only for now)
pointer_settings = true   # Windows only: apply the profile's Windows pointer settings on a switch
```

On Windows, `valkyrie-monitor` replaces VMON: it sits in the tray (right-click: Reload
settings, Quit), shows the notifications from there, and applies the new profile's
pointer speed, acceleration, scroll lines and double-click time when you switch profile
on the mouse. `exact_dpi` is not available there yet (it needs VCFG's driver, whose
settings format is still unknown), so off-grid DPI values use the nearest step of 250.
To start it with Windows, put a shortcut to `bin\valkyrie-monitor.cmd` (or to the
installed `valkyrie-monitor.exe`) in the Startup folder (Win+R, `shell:startup`), and
remove VMON from startup.

With `exact_dpi = true`, while the DPI level in use is between steps (1900 while the mouse
uses 2000), the daemon grabs the mouse's pointer node and sends the movement, scaled by
1900/2000, through a virtual copy of the mouse. The copy has the same name and USB IDs,
so your desktop applies the same mouse settings to it. On levels the mouse has itself,
nothing is grabbed. Reload after editing with `valkyrie-monitor reload`.

The daemon knows the profiles from `~/.config/valkyrie/host.json`, which the window and
the command line keep up to date. This file also holds the DPI asked for and the Windows
settings of each profile. If it is missing, the daemon reads the mouse once at start.

It needs the same permissions as the auto-clicker (the udev rule above, and `/dev/uinput`
for exact DPI). To start it with your session:

```
sed "s|@DIR@|$PWD|" valkyrie-monitor.service > ~/.config/systemd/user/valkyrie-monitor.service
systemctl --user daemon-reload && systemctl --user enable --now valkyrie-monitor
```

## Auto-clicker

The mouse's fire key and macros cannot click fast or steadily. Instead, make a button
send an unused key (F13-F24) and let `valkyrie-autoclick` turn that key into clicks:

```
valkyrie set --button 4=key:F13          # or Buttons tab → Key… → F13
bin/valkyrie-autoclick                   # first run writes ~/.config/valkyrie/autoclick.toml
```

Each `[[click]]` section in the settings file binds one key:

```toml
[[click]]
key = "F13"
button = "left"      # left, right, middle
rate = 15            # clicks per second (1 to max_rate)
mode = "hold"        # "hold": while the key is down; "toggle": press to start, again to stop
```

`max_rate` (at the top of the file, default 20, at most 100) is the highest rate: no
`rate` may be above it, and `faster_key` stops there.

Optional keys in a `[[click]]` section change it while running (until the next reload):

```toml
slower_key = "F14"   # fewer clicks per second; hold the key to keep going
faster_key = "F15"   # more clicks per second
mode_key = "F16"     # switch between hold and toggle
step = 1             # clicks per second per press
```

A beep confirms each change: its pitch follows the new rate (higher is faster); after a
mode switch, two short beeps mean toggle and one long beep means hold. In toggle mode,
two rising tones mean clicking started and two falling tones that it stopped.

After editing, reload with `valkyrie-autoclick reload` (or `systemctl --user reload
valkyrie-autoclick`, or a `reload_key`). A broken file is reported and the previous
settings stay active; `valkyrie-autoclick check` validates the file without running.

By default (`swallow = true`) the trigger keys are hidden from other programs: the daemon
grabs the mouse's keyboard interface and forwards every other key through a virtual
keyboard. Clicks come from a virtual mouse (`/dev/uinput`), so it works on Wayland.
If the mouse disconnects (USB dock), the daemon waits for it to come back.

On Windows, a keyboard hook reads and hides the trigger keys and clicks are sent with
`SendInput`; nothing needs setting up. It sits in the tray (Reload settings, Quit), where
the notifications appear. Two differences: the hook cannot tell keyboards apart, so a
trigger key your keyboard also has (anything but F13-F24) is hidden from it too; and
Windows blocks clicks into programs run as administrator unless the auto-clicker runs as
administrator as well. Autostart: a shortcut to `bin\valkyrie-autoclick.cmd` in
`shell:startup`.

Setup: the udev rule above also lets you read the mouse's key events. `/dev/uinput`
must be writable too; Steam's udev rules already allow it, otherwise add
`KERNEL=="uinput", SUBSYSTEM=="misc", TAG+="uaccess", OPTIONS+="static_node=uinput"`.
To start it with your session:

```
mkdir -p ~/.config/systemd/user
sed "s|@DIR@|$PWD|" valkyrie-autoclick.service > ~/.config/systemd/user/valkyrie-autoclick.service
systemctl --user daemon-reload && systemctl --user enable --now valkyrie-autoclick
```

## Safety

- Before every write, the current state is saved to `~/.local/share/valkyrie/backups/`;
  undo with `valkyrie restore FILE`.
- After every write, the data is read back and compared.
- Writes are refused outside the memory ranges VCFG itself writes (for example the USB
  ID stored at 0x44-0x47), and only the kinds of settings and actions VCFG's own
  encoder produces can be created (for example, the mouse always gets the same X and Y
  DPI, as from VCFG).
- Writing is refused while VCFG.exe, VMON.EXE or ETGMSrv.exe runs under Wine/Proton, or
  while VCFG.exe runs on Windows, because they talk to the mouse at the same time
  (override with `--force`).

## Macros

The mouse has 30 macro slots of at most 60 steps each, as in VCFG's encoder (VCFG's window
lets you assign only 5 macros at a time; that limit is its own). Slots are shared by all
profiles, like VCFG's macro library: changing macro 1 changes it wherever it is assigned,
and every profile using it is rewritten automatically.

## Files

| Path | Contents |
|---|---|
| `valkyrie/device.py` | frames, VCFG's command sequences, safety checks; picks the transport below |
| `valkyrie/hid_linux.py`, `hid_windows.py` | the transport: hidraw on Linux, the HID class driver (ctypes) on Windows |
| `valkyrie/paths.py` | where files go on each system |
| `valkyrie/instance.py` | a running daemon: single copy, `reload` (pid file + SIGHUP on Linux, named mutex/event on Windows) |
| `valkyrie/model.py` | settings and their byte encoding |
| `valkyrie/keys.py` | key and media-key names, Windows key codes |
| `valkyrie/pfd.py` | VCFG `.pfd` files (also used by `pfd2txt.py`) |
| `valkyrie/store.py` | JSON export/apply, raw backups |
| `valkyrie/host.py` | what the PC keeps beside the mouse (`~/.config/valkyrie/host.json`) |
| `valkyrie/ops.py` | write steps shared by the command and the window (plan, backup, write, verify), factory settings |
| `valkyrie/events.py` | the reports the mouse sends when its own buttons change a setting |
| `valkyrie/monitor.py` | `bin/valkyrie-monitor`: what both systems share; `monitor_linux.py` (notify-send, exact DPI), `monitor_windows.py` (tray, pointer settings) |
| `valkyrie/winsettings.py`, `winui.py` | Windows only: applying pointer settings; the daemons' tray icon |
| `valkyrie/data/factory.json` | VCFG's factory settings (extracted from VCFG.exe, see `../re/FINDINGS.md`) |
| `valkyrie/cli.py` | the `valkyrie` command |
| `valkyrie/gui.py` | the window (`bin/valkyrie-gui`) |
| `valkyrie/autoclick.py` | the auto-clicker (`bin/valkyrie-autoclick`); `autoclick_linux.py` (evdev, uinput), `autoclick_windows.py` (keyboard hook, SendInput) |
| `valkyrie/linux_input.py` | Linux only: evdev and uinput, shared by the two Linux daemons |
| `bin/*.cmd`, `pyproject.toml` | Windows launchers; `pip install -e .` for real commands on both systems |
| `pfd2txt.py` | show a `.pfd` file as text |
| `captures/` | usbmon recordings of VCFG and `usbcap.py`, the recorder |
| `tests/` | `python3 -m unittest discover -s tests` (`py -m unittest discover -s tests` on Windows) |
| `WINDOWS.md` | the Windows port: what is done, what is left |

## How the protocol was found

By recording VCFG.exe (running under Proton) with usbmon while changing one setting at a
time, then checking every encoding against VCFG's saved `.pfd` files. The tests replay
those recordings: every frame VCFG sent is rebuilt byte for byte. The rest (30 macro
slots, two-key shortcuts, DPI rounding, the key tables of `.pfd` files, the mouse's own
reports, the factory settings) comes from reverse-engineering VCFG.exe and VMON.exe;
see `../re/FINDINGS.md`.
