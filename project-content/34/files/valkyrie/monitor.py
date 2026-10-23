"""valkyrie-monitor: what VMON.exe does, on Linux and Windows.

When the profile, DPI level or report rate is changed with the mouse's own
buttons, the mouse says so on its vendor interface (events.py). This daemon:

- shows a notification, like VMON's on-screen popup;
- on Windows, applies the new profile's Windows pointer settings (pointer speed,
  acceleration, scroll lines, double-click time), as VMON does;
- on Linux with exact_dpi on, makes DPI values off the 250 grid exact (1900 while
  the mouse uses 2000), like VMON with its filter driver: pointer movement is scaled
  by asked / used DPI, carrying the remainder (monitor_linux.py). On Windows that
  needs VCFG's driver and is not done yet.

It reads the mouse once when it starts (and when the mouse is plugged in again),
then follows the mouse's reports, and host.json (see host.py) when the window or
the command line change something; it never reads the mouse in between.

This module holds what both systems share; monitor_linux.py and monitor_windows.py
hold the rest. Settings: monitor.toml in the config folder, read at start and on
`valkyrie-monitor reload` (or the tray menu on Windows).
"""
import argparse
import os
import sys
import time
import tomllib

from . import device, events, host, instance, model, ops, paths, utf8_stdio
from .autoclick import log

NAME = 'valkyrie-monitor'
CONFIG = os.path.join(host.CONFIG_DIR, 'monitor.toml')
REL_X, REL_Y = 0x00, 0x01                 # the movement axes Scaler scales (evdev codes)

DEFAULT_CONFIG = '''\
# valkyrie-monitor's settings. Reload after editing: valkyrie-monitor reload

# Show a notification when the profile, DPI level or report rate is changed
# with the mouse's own buttons.
notify = true

# Make DPI values off the mouse's 250 steps exact (e.g. 1900 while the mouse uses
# 2000) by scaling the pointer movement, like VCFG's driver on Windows. The mouse
# is grabbed and its movement sent through a virtual copy only while the DPI level
# in use needs it. Linux only for now.
exact_dpi = false

# Windows only: apply the profile's Windows pointer settings (pointer speed,
# acceleration, scroll lines, double-click time) when the profile is switched on
# the mouse, as VMON does.
pointer_settings = true
'''

SETTINGS = ('notify', 'exact_dpi', 'pointer_settings')


class Config:
    def __init__(self, text):
        try:
            d = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f'not valid TOML: {e}') from None
        unknown = set(d) - set(SETTINGS)
        if unknown:
            raise ValueError(f'unknown setting(s) {", ".join(sorted(unknown))}')
        for name in SETTINGS:
            if not isinstance(d.get(name, False), bool):
                raise ValueError(f'{name} must be true or false')
        self.notify = d.get('notify', True)
        self.exact_dpi = d.get('exact_dpi', False)
        self.pointer_settings = d.get('pointer_settings', True)


def load_config(path):
    with open(path, encoding='utf-8') as f:
        return Config(f.read())


# --- What the mouse is doing (no I/O, so it can be tested) --------------------------

class Tracker:
    """The mouse's profiles as the PC knows them, kept current with its reports."""

    def __init__(self, data):
        self.load(data)

    def load(self, data):
        active = data.get('active_profile')
        self.active = active - 1 if isinstance(active, int) and 1 <= active <= device.PROFILES else None
        self.profiles = {}
        self.windows = {}                      # n -> model.WindowsSettings, where known
        for key, entry in data.get('profiles', {}).items():
            try:
                polling, selected, levels = host.profile_view(entry)
                self.profiles[int(key) - 1] = {'polling': polling, 'selected': selected, 'levels': levels}
                self.windows[int(key) - 1] = host.windows_for(entry)
            except (TypeError, ValueError):
                continue

    def profile(self):
        return self.profiles.get(self.active)

    def level(self):
        """(on, (x, y) used, (x, y) asked for) of the DPI level in use, or None."""
        p = self.profile()
        if p is None or not 0 <= p['selected'] < len(p['levels']):
            return None
        return p['levels'][p['selected']]

    def factors(self):
        """Movement scale (x, y) that turns the DPI used into the DPI asked for."""
        level = self.level()
        if level is None:
            return 1.0, 1.0
        _, (hx, hy), (wx, wy) = level
        return (wx / hx if hx else 1.0), (wy / hy if hy else 1.0)

    def apply(self, event):
        """Update from an events.Event."""
        p = self.profile()
        if event.kind == 'profile':
            self.active = event.value
        elif event.kind == 'dpi' and p is not None:
            p['selected'] = event.value
        elif event.kind == 'rate' and p is not None:
            p['polling'] = event.value

    def message(self, event, scaling=False):
        """(title, body) of the notification for an event already applied, or None.
        scaling: the movement is being scaled, so the DPI asked for is exact."""
        if event.kind == 'profile':
            p = self.profile()
            parts = [self.dpi_text(scaling)] if self.level() else []
            if p and model.POLLING_HZ.get(p['polling']):
                parts.append(f"{model.POLLING_HZ[p['polling']]} Hz")
            return f'Profile {event.value + 1}', ' · '.join(parts)
        if event.kind == 'dpi':
            where = f' of profile {self.active + 1}' if self.active is not None else ''
            title = self.dpi_text(scaling) if self.level() else f'DPI level {event.value + 1}'
            return title, f'Level {event.value + 1}{where}'
        if event.kind == 'rate':
            hz = model.POLLING_HZ.get(event.value)
            return (f'Report rate {hz} Hz' if hz else 'Report rate changed'), ''
        return None

    def dpi_text(self, scaling=False):
        on, held, wanted = self.level()
        text = f'{wanted[0]} DPI' if wanted[0] == wanted[1] else f'{wanted[0]} × {wanted[1]} DPI'
        if wanted != held and not scaling:
            text += f' (mouse: {held[0]})'
        return text


class Scaler:
    """Scales relative movement by fixed factors, carrying the remainders so slow
    movements are not lost (like SetXYValueV2 in VCFG's driver)."""

    def __init__(self):
        self.fx = self.fy = 1.0
        self.rx = self.ry = 0.0

    def set(self, fx, fy):
        if (fx, fy) != (self.fx, self.fy):
            self.fx, self.fy = fx, fy
            self.rx = self.ry = 0.0          # the driver resets them on a DPI change too

    @property
    def needed(self):
        return abs(self.fx - 1.0) > 1e-9 or abs(self.fy - 1.0) > 1e-9

    def scale(self, code, value):
        if code == REL_X:
            exact = value * self.fx + self.rx
            out = int(exact)                  # towards zero
            self.rx = exact - out
            return out
        if code == REL_Y:
            exact = value * self.fy + self.ry
            out = int(exact)
            self.ry = exact - out
            return out
        return value


# --- Daemon -------------------------------------------------------------------------

class BaseDaemon:
    """The daemon on any system. A system's Daemon provides make_notifier(),
    exact_dpi_available(), scaling_changed(), close_proxy(), on_profile() and run()."""

    def __init__(self, path):
        self.path = path
        self.config = None
        self.reload_wanted = True
        self.stopping = False
        self.listener = None
        self.scaler = Scaler()
        self.notifier = self.make_notifier()
        self.tracker = Tracker(host.empty())
        self.host_mtime = None
        self.next_scan = 0.0

    def request_reload(self):
        """From `valkyrie-monitor reload` (SIGHUP, or a named event on Windows)."""
        self.reload_wanted = True

    def stop(self):
        self.stopping = True

    def reload(self):
        self.reload_wanted = False
        try:
            config = load_config(self.path)
        except FileNotFoundError:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            with open(self.path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(DEFAULT_CONFIG)
            config = load_config(self.path)
            log(f'created {self.path}')
        except (OSError, ValueError) as e:
            if self.config is None:
                raise SystemExit(f'{self.path}: {e}') from None
            log(f'settings not reloaded, keeping the old ones: {e}')
            return
        if config.exact_dpi and not self.exact_dpi_available():
            config.exact_dpi = False
        self.config = config
        if not config.exact_dpi:
            self.close_proxy()
        log(f'notify {"on" if config.notify else "off"}, exact DPI {"on" if config.exact_dpi else "off"}'
            + (f', pointer settings {"on" if config.pointer_settings else "off"}' if paths.WINDOWS else ''))
        self.update_scaling()

    def host_changed(self):
        try:
            mtime = os.stat(host.path()).st_mtime_ns
        except OSError:
            mtime = None
        if mtime != self.host_mtime:
            self.host_mtime = mtime
            return True
        return False

    def load_host(self):
        self.tracker.load(host.load())
        self.update_scaling()

    def read_mouse(self):
        """Read the mouse (at start and when it comes back): the active profile and
        DPI level may have been changed on it while nobody was listening."""
        found = device.conflicting_programs()
        if found:
            log(f'{device.conflict_text(found)}; not reading the mouse')
            return None
        try:
            mouse = device.open_mouse()
            try:
                state = ops.read_state(mouse)
            finally:
                mouse.io.close()
        except (OSError, device.DeviceError) as e:
            log(f'could not read the mouse: {e}')
            return None
        host.record(state.profiles, state.active)
        self.host_changed()
        log(f'read the mouse: profile {state.active + 1} active')
        self.load_host()
        return True

    def update_scaling(self):
        if self.config is None:
            return
        fx, fy = self.tracker.factors() if self.config.exact_dpi else (1.0, 1.0)
        self.scaler.set(fx, fy)
        self.scaling_changed()

    def open_listener(self):
        """-> True if the listener was opened now."""
        if self.listener is not None:
            return False
        try:
            self.listener = events.Listener()
        except device.DeviceError as e:
            log(str(e))
            return False
        log(f'listening on {self.listener.path}')
        self.read_mouse()
        return True

    def close_listener(self):
        if self.listener is not None:
            self.listener.close()
            self.listener = None

    def periodic(self):
        """Every 2 seconds: look for the mouse, and follow host.json."""
        now = time.monotonic()
        if now < self.next_scan:
            return
        self.next_scan = now + 2.0
        self.open_devices()
        if self.host_changed():
            log('host.json changed; using it')
            self.load_host()

    def open_devices(self):
        self.open_listener()

    def on_events(self, got):
        for event in got:
            self.tracker.apply(event)
            log(event.describe())
            if event.kind in ('profile', 'dpi'):
                self.update_scaling()
            if event.kind == 'profile':
                self.on_profile()
            message = self.tracker.message(event, scaling=self.scaler.needed)
            if message and self.config.notify:
                self.notifier.show(*message)

    def mouse_gone(self):
        log('the mouse was unplugged; waiting for it')
        self.close_listener()
        self.close_proxy()


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(prog=NAME,
                                 description='Notifications and exact DPI for the Drakkar Valkyrie (like VMON).')
    ap.add_argument('command', nargs='?', choices=['run', 'reload', 'check'], default='run',
                    help='run the daemon (default), make the running one reload its settings, '
                         'or check the settings file')
    ap.add_argument('--config', default=CONFIG, help=f'settings file (default: {CONFIG})')
    args = ap.parse_args(argv)
    if args.command == 'reload':
        if not instance.request_reload(NAME):
            print(f'{NAME} is not running', file=sys.stderr)
            return 1
        print('reload requested')
        return 0
    if args.command == 'check':
        try:
            config = load_config(args.config)
        except (OSError, ValueError) as e:
            print(f'{args.config}: {e}', file=sys.stderr)
            return 1
        print(f'notify = {str(config.notify).lower()}, exact_dpi = {str(config.exact_dpi).lower()}, '
              f'pointer_settings = {str(config.pointer_settings).lower()}')
        return 0
    if paths.WINDOWS:
        from .monitor_windows import Daemon
    else:
        from .monitor_linux import Daemon
    daemon = Daemon(args.config)
    try:
        running = instance.Instance(NAME, daemon.request_reload)
    except instance.AlreadyRunning as e:
        print(e, file=sys.stderr)
        return 1
    try:
        daemon.run()
    finally:
        running.close()
    return 0
