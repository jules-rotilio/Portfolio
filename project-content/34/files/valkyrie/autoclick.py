"""Auto-clicker driven by keys the mouse sends (for example F13-F24).

The mouse's own fire key and macros cannot click fast or steadily, so a mouse
button is set to send a key (`valkyrie set --button 4=key:F13`) and this daemon
turns that key into clicks at a steady rate:

  hold    clicks while the key is held down
  toggle  one press starts clicking, the next press stops

This module holds what Linux and Windows share: the settings, the click timing and
the sounds. How keys are read and clicks sent is in autoclick_linux.py (the mouse's
keyboard interface and a virtual mouse, on Wayland and X11 alike) and
autoclick_windows.py (a low-level keyboard hook and SendInput). On both, the
trigger keys are hidden from other programs.

Settings live in autoclick.toml in the config folder (~/.config/valkyrie,
%APPDATA%\\valkyrie on Windows) and are read again on `valkyrie-autoclick reload`,
from the tray menu on Windows, or when the optional reload key is pressed.
"""
import argparse
import io
import math
import os
import struct
import sys
import time
import tomllib
import wave

from . import instance, keys, paths, utf8_stdio

NAME = 'valkyrie-autoclick'
CONFIG = os.path.join(paths.config_dir(), 'autoclick.toml')

BUTTONS = {'left': 0x110, 'right': 0x111, 'middle': 0x112}      # evdev BTN_* codes, used as ids
MAX_RATE = 100                             # the highest max_rate allowed
DEFAULT_MAX_RATE = 20

DEFAULT_CONFIG = '''\
# valkyrie-autoclick's settings. Reload after editing:
#   valkyrie-autoclick reload      (or press the reload key below)
#
# A mouse button must send the key, e.g.:  valkyrie set --button 4=key:F13

# Hide the trigger keys from other programs (they are still seen here).
swallow = true

# Pressing this key reads this file again. Remove the line to disable it.
# reload_key = "F1"

# Show a desktop notification when the settings are (re)loaded or wrong.
notify = true

# Highest click rate (clicks per second, up to 100): faster_key stops there, and
# no rate below may be higher.
max_rate = 20

# Toggle mode: two rising tones when clicking starts, two falling tones when it stops.
sound = true
volume = 0.3         # 0.0 - 1.0

[[click]]
key = "F13"          # F13 ... F24 (any key name from "valkyrie actions" works)
button = "left"      # left, right or middle
rate = 15            # clicks per second (1 to max_rate)
mode = "toggle"        # "hold": click while the key is down; "toggle": press to start/stop
# press_ms = 10      # how long each click holds the button (default: half the period, at most 20)

# Optional keys that change this [[click]] while running (until the next reload).
# A beep confirms: its pitch follows the new rate; for the mode, two short beeps
# mean "toggle" and one long beep means "hold".
slower_key = "F14"   # fewer clicks per second (hold the key to keep going)
faster_key = "F15"   # more clicks per second
mode_key = "F16"     # switch between hold and toggle
step = 1             # clicks per second per press

# [[click]]
# key = "F17"
# button = "right"
# rate = 8
# mode = "hold"
'''


# --- Settings -----------------------------------------------------------------------

def key_code(name):
    """The code this system reads for a key name: evdev on Linux, scan code on Windows."""
    return keys.native_code(name)


class Binding:
    def __init__(self, d, n, max_rate=MAX_RATE):
        where = f'[[click]] number {n}'
        unknown = set(d) - {'key', 'button', 'rate', 'mode', 'press_ms',
                            'slower_key', 'faster_key', 'mode_key', 'step'}
        if unknown:
            raise ValueError(f'{where}: unknown setting(s) {", ".join(sorted(unknown))}')
        try:
            self.key_name = str(d['key'])
            self.key = key_code(self.key_name)
        except KeyError:
            raise ValueError(f'{where}: "key" is missing') from None
        except ValueError as e:
            raise ValueError(f'{where}: {e}') from None
        self.button_name = str(d.get('button', 'left')).lower()
        if self.button_name not in BUTTONS:
            raise ValueError(f'{where}: button must be left, right or middle')
        self.button = BUTTONS[self.button_name]
        self.max_rate = max_rate
        rate = d.get('rate')
        if not isinstance(rate, (int, float)) or not 1 <= rate <= max_rate:
            raise ValueError(f'{where}: rate must be a number of clicks per second, 1-{max_rate:g} (max_rate)')
        self.mode = str(d.get('mode', 'hold')).lower()
        if self.mode not in ('hold', 'toggle'):
            raise ValueError(f'{where}: mode must be "hold" or "toggle"')
        press = d.get('press_ms')
        if press is not None and (not isinstance(press, (int, float)) or not 0 < press / 1000 < 1 / rate):
            raise ValueError(f'{where}: press_ms must be shorter than the time between clicks '
                             f'({1000 / rate:.0f} ms)')
        self.press_ms = press
        self.set_rate(rate)
        # Optional keys that change this binding while the daemon runs.
        self.controls = {}
        for name in ('slower_key', 'faster_key', 'mode_key'):
            if d.get(name):
                try:
                    self.controls[key_code(str(d[name]))] = name.removesuffix('_key')
                except ValueError as e:
                    raise ValueError(f'{where}: {name}: {e}') from None
        self.step = d.get('step', 1)
        if not isinstance(self.step, (int, float)) or not 0 < self.step < max_rate:
            raise ValueError(f'{where}: step must be a number of clicks per second')

    def set_rate(self, rate):
        """Change the rate (clamped to 1-max_rate); -> the rate now used."""
        self.rate = max(1, min(self.max_rate, rate))
        self.period = 1.0 / self.rate
        # A fixed press time never exceeds half the period, so clicks stay clicks.
        press = self.press_ms / 1000 if self.press_ms else 0.020
        self.press = min(self.period / 2, press)
        return self.rate

    def describe(self):
        text = f'{self.key_name}: {self.button_name} click {self.rate:g}/s ({self.mode})'
        if self.controls:
            text += ', ' + ', '.join(f'{keys.key_name(keys.native_table()[k])} {what}'
                                     for k, what in self.controls.items())
        return text


class Config:
    def __init__(self, text):
        try:
            d = tomllib.loads(text)
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f'not valid TOML: {e}') from None
        unknown = set(d) - {'swallow', 'reload_key', 'notify', 'sound', 'volume', 'device', 'max_rate', 'click'}
        if unknown:
            raise ValueError(f'unknown setting(s) {", ".join(sorted(unknown))}')
        self.swallow = bool(d.get('swallow', True))
        self.notify = bool(d.get('notify', True))
        self.sound = bool(d.get('sound', True))
        self.volume = d.get('volume', 0.3)
        if not isinstance(self.volume, (int, float)) or not 0 <= self.volume <= 1:
            raise ValueError('volume must be between 0.0 and 1.0')
        self.device = d.get('device', 'auto')           # an event node to read (Linux only)
        self.max_rate = d.get('max_rate', DEFAULT_MAX_RATE)
        if not isinstance(self.max_rate, (int, float)) or isinstance(self.max_rate, bool) or \
                not 1 <= self.max_rate <= MAX_RATE:
            raise ValueError(f'max_rate must be a number of clicks per second, 1-{MAX_RATE}')
        self.reload_key = key_code(d['reload_key']) if d.get('reload_key') else None
        clicks = d.get('click', [])
        if not isinstance(clicks, list) or not clicks:
            raise ValueError('add at least one [[click]] section')
        self.bindings = [Binding(c, i + 1, self.max_rate) for i, c in enumerate(clicks)]
        used = [b.key for b in self.bindings] + [k for b in self.bindings for k in b.controls]
        used += [self.reload_key] if self.reload_key else []
        if len(used) != len(set(used)):
            raise ValueError('each key can only be used once')
        # key code -> (binding index, 'click' | 'slower' | 'faster' | 'mode')
        self.actions = {}
        for i, b in enumerate(self.bindings):
            self.actions[b.key] = (i, 'click')
            self.actions.update({k: (i, what) for k, what in b.controls.items()})

    @property
    def keys(self):
        return set(self.actions) | ({self.reload_key} if self.reload_key else set())


def load_config(path):
    with open(path, encoding='utf-8') as f:
        return Config(f.read())


# --- Clicking (no I/O, so it can be tested with a fake clock) ---------------------

class Clicker:
    """Click state of one binding. Clicks are scheduled on a fixed grid from the
    first one, so the rate does not drift."""

    def __init__(self, binding):
        self.b = binding
        self.active = False
        self.held = False           # the trigger key is down
        self.down = False           # our button is pressed
        self.pressed_at = 0.0
        self.start = 0.0
        self.count = 0              # clicks started since start

    def key(self, value, now):
        """value: 1 pressed, 0 released (repeats are ignored by the caller).
        -> True if clicking started, False if it stopped, None otherwise."""
        was = self.active
        pressed = value == 1
        if self.b.mode == 'hold':
            if pressed and not self.active:
                self.begin(now)
            elif not pressed:
                self.active = False
        elif pressed:
            if self.active:
                self.active = False
            else:
                self.begin(now)
        self.held = pressed
        return self.active if self.active != was else None

    def set_rate(self, rate):
        """New rate, effective from the next click (clicking goes on if active)."""
        rate = self.b.set_rate(rate)
        if self.active and self.count:
            # Re-anchor the grid on the last click so the next one comes one new period after it.
            self.start, self.count = self.pressed_at, 1
        return rate

    def switch_mode(self):
        """hold <-> toggle. -> (new mode, True if clicking was stopped)."""
        stopped = self.active
        self.active = False
        self.b.mode = 'toggle' if self.b.mode == 'hold' else 'hold'
        return self.b.mode, stopped

    def begin(self, now):
        self.active, self.start, self.count = True, now, 0

    def next_press(self):
        return self.start + self.count * self.b.period

    def deadline(self):
        if self.down:
            return self.pressed_at + self.b.press                         # release time
        return self.next_press() if self.active else None

    def due(self, now):
        """-> list of (button, value) to send now."""
        out = []
        if self.down and now >= self.deadline():
            out.append((self.b.button, 0))
            self.down = False
        if self.active and not self.down and now >= self.next_press():
            missed = int((now - self.next_press()) / self.b.period)
            self.count += missed + 1          # skip clicks we are too late for
            out.append((self.b.button, 1))
            self.down, self.pressed_at = True, now
        return out

    def stop(self):
        """-> events that leave the button released."""
        self.active = False
        if self.down:
            self.down = False
            return [(self.b.button, 0)]
        return []


# --- Sounds -----------------------------------------------------------------------

LOW, HIGH = 660.0, 990.0          # Hz, a fifth apart
MID = 825.0


def rate_pitch(rate):
    """Pitch of the beep after a rate change: higher means faster."""
    return 300.0 + 17.0 * rate
RATE = 44100


def tones(freqs, volume, rate=RATE, tone=0.07, gap=0.03, fade=0.008):
    """16-bit mono samples: one short tone per frequency, with soft edges so it does not click."""
    samples = bytearray()
    for i, freq in enumerate(freqs):
        n = int(tone * rate)
        for k in range(n):
            edge = min(1.0, k / (fade * rate), (n - k) / (fade * rate))
            value = volume * edge * math.sin(2 * math.pi * freq * k / rate)
            samples += struct.pack('<h', int(value * 32767))
        if i < len(freqs) - 1:
            samples += bytes(2 * int(gap * rate))
    return bytes(samples)


def wav(pcm, rate=RATE):
    """16-bit mono samples as a WAV file (bytes)."""
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return out.getvalue()


def chime(freqs, volume, rate=RATE):
    """The same tones as a WAV file (bytes)."""
    return wav(tones(freqs, volume, rate), rate)


def chime_pcm(volume):
    """The named sounds: start/stop chimes and the hold/toggle confirmations."""
    return {'on': tones((LOW, HIGH), volume), 'off': tones((HIGH, LOW), volume),
            'toggle': tones((MID, MID), volume, tone=0.05, gap=0.04),
            'hold': tones((MID,), volume, tone=0.18)}


# --- Daemon -------------------------------------------------------------------

def log(text):
    print(time.strftime('%H:%M:%S ') + text, file=sys.stderr, flush=True)


class BaseDaemon:
    """What the daemon does with keys and clicks, on any system. A system's Daemon
    provides send_buttons(), make_sounds(), show_notification() and reopen()."""

    def __init__(self, path):
        self.path = path
        self.config = None
        self.clickers = {}
        self.reload_wanted = True
        self.stopping = False
        self.sounds = None

    def request_reload(self):
        """From `valkyrie-autoclick reload` (SIGHUP, or a named event on Windows)."""
        self.reload_wanted = True

    def stop(self):
        self.stopping = True

    def notify(self, text, urgent=False):
        log(text)
        if self.config is not None and not self.config.notify:
            return
        self.show_notification(text, urgent)

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
            self.notify(f'settings not reloaded, keeping the old ones: {e}', urgent=True)
            return
        self.release_all()
        self.config = config
        if self.sounds is not None:
            self.sounds.close()
        self.sounds = self.make_sounds(config.volume) if config.sound else None
        self.clickers = {b.key: Clicker(b) for b in config.bindings}
        self.reopen()                          # the keys or swallow may have changed
        self.notify('settings loaded: ' + '; '.join(b.describe() for b in config.bindings))

    def release_all(self):
        events = []
        for c in self.clickers.values():
            if c.active:
                self.chime(c.b, False)
            events += c.stop()
        self.send_buttons(events)

    def key_event(self, code, value, now):
        """A key read from the mouse: value 1 pressed, 0 released, 2 auto-repeat.
        -> True if it is one of ours (a trigger, control or reload key)."""
        if code not in self.config.keys:
            return False
        if code == self.config.reload_key:
            if value == 1:
                self.reload_wanted = True
        else:
            self.control(code, value, now)
        return True

    def control(self, code, value, now):
        """A trigger or control key: value 1 pressed, 0 released, 2 auto-repeat."""
        index, what = self.config.actions[code]
        clicker = self.clickers[self.config.bindings[index].key]
        if what == 'click':
            if value != 2:
                change = clicker.key(value, now)
                if change is not None:
                    self.chime(clicker.b, change)
        elif what in ('slower', 'faster') and value in (1, 2):      # holding the key repeats
            step = clicker.b.step if what == 'faster' else -clicker.b.step
            rate = clicker.set_rate(clicker.b.rate + step)
            log(f'{clicker.b.key_name}: {rate:g} clicks per second')
            if self.sounds is not None:
                self.sounds.beep(rate_pitch(rate))
        elif what == 'mode' and value == 1:
            mode, stopped = clicker.switch_mode()
            self.send_buttons(clicker.stop())
            if stopped:
                self.chime(clicker.b, False, force=True)
            log(f'{clicker.b.key_name}: mode {mode}')
            if self.sounds is not None:
                self.sounds.play(mode)

    def chime(self, binding, started, force=False):
        if self.sounds is not None and (binding.mode == 'toggle' or force):
            self.sounds.play('on' if started else 'off')

    def click_due(self, now):
        """Send the clicks due now; -> seconds until the next one, or None."""
        events = []
        for c in self.clickers.values():
            events += c.due(now)
        self.send_buttons(events)
        deadlines = [d for d in (c.deadline() for c in self.clickers.values()) if d is not None]
        return max(0.0, min(deadlines) - time.monotonic()) if deadlines else None


def main(argv=None):
    utf8_stdio()
    ap = argparse.ArgumentParser(prog=NAME,
                                 description='Turn keys sent by the mouse (e.g. F13) into steady clicks.')
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
        for b in config.bindings:
            print(b.describe())
        return 0
    if paths.WINDOWS:
        from .autoclick_windows import Daemon
    else:
        from .autoclick_linux import Daemon
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
