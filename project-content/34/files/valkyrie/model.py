"""Settings of the Drakkar Valkyrie and their byte encoding in the mouse's memory.

Every encoding here was checked against the bytes VCFG.exe sends (see the
usbmon captures in captures/). Values read from the mouse remember their raw
bytes, so anything left unchanged is written back exactly as it was.
"""
from dataclasses import dataclass, field

from . import keys

BUTTONS = 14
# The mouse stores the 14 actions in this order of VCFG button numbers.
SLOT_BUTTONS = (1, 2, 3, 4, 5, 6, 7, 8, 12, 9, 10, 11, 13, 14)

DPI_STEP = 250                # the mouse's own DPI steps
DPI_MIN, DPI_MAX = 250, 4000
DPI_LEVELS = 5
# DPI values may be asked for in steps of 50, like VCFG's sliders. The mouse uses the
# nearest multiple of 250; valkyrie-monitor (like VMON with its driver on Windows)
# scales the movement so the value asked for is exact.
DPI_FINE_STEP = 50

POLLING_HZ = {1: 1000, 2: 500, 4: 250, 8: 125}       # byte -> Hz
BRIGHTNESS = {0: 'off', 1: 'low', 2: 'medium', 3: 'high'}
BREATHING = {0: 'off', 6: 'low', 3: 'medium', 1: 'high'}  # bigger is slower

MACRO_SIZE = 200          # bytes per macro slot
MACRO_MAX_LOOPS = 255
MACRO_MAX_STEPS = 60      # VCFG's encoder stops at 60 steps (plus the end marker)

# Actions without parameters: name -> (type byte, label)
SIMPLE = {
    'left': (0x01, 'Left click'),
    'right': (0x02, 'Right click'),
    'middle': (0x03, 'Middle click'),
    'back': (0x04, 'Back (button 4)'),
    'forward': (0x05, 'Forward (button 5)'),
    'dpi-cycle': (0x08, 'DPI cycle'),
    'dpi-down': (0x09, 'DPI -'),
    'dpi-up': (0x0A, 'DPI +'),
    'profile-switch': (0x0D, 'Profile switch'),
    'rate-up': (0x17, 'Report rate +'),
    'rate-down': (0x18, 'Report rate -'),
}
SIMPLE_ALIASES = {
    'click': 'left', 'left-click': 'left', 'right-click': 'right', 'middle-click': 'middle',
    'backward': 'back', 'dpi+': 'dpi-up', 'dpi-': 'dpi-down', 'rate+': 'rate-up',
    'rate-': 'rate-down', 'report-rate+': 'rate-up', 'report-rate-': 'rate-down',
}
MOUSE_BITS = {'left': 1, 'right': 2, 'middle': 4}    # mouse buttons in macros and fire keys


# --- Button actions ----------------------------------------------------------

@dataclass(frozen=True)
class Action:
    """One button assignment.

    kind is a SIMPLE name, 'disable', 'media', 'key', 'shortcut', 'fire',
    'macro' or 'unknown'. code holds the HID key, media usage, fire target or
    macro slot (0-based), depending on kind. A shortcut has up to two keys
    (code, code2) besides its modifiers.
    """
    kind: str
    code: int = 0
    mods: int = 0
    code2: int = 0
    times: int = 0
    delay: int = 0
    repeat: bool = False
    raw: bytes | None = field(default=None, compare=False)


def decode_action(b):
    b = bytes(b)
    kind_by_type = {t: kind for kind, (t, _) in SIMPLE.items()}
    t = b[0]
    if t in kind_by_type:
        return Action(kind_by_type[t], raw=b)
    if t == 0x0E:
        usage = b[2] | b[3] << 8
        return Action('disable' if usage == 0 else 'media', code=usage, raw=b)
    if t == 0x0F:
        return Action('shortcut', code=b[2], mods=b[1], code2=b[3], raw=b)
    if t == 0x10:
        return Action('key', code=b[2], raw=b)
    if t == 0x11:
        return Action('macro', code=b[1] & 0x7F, repeat=bool(b[1] & 0x80), raw=b)
    if t == 0x19:
        return Action('fire', code=b[1], times=b[2], delay=b[3], raw=b)
    return Action('unknown', raw=b)


def encode_action(a, slot, macro_len=None):
    """4 bytes for action a in table slot `slot` (0-13, mouse order)."""
    if a.kind == 'macro':
        if macro_len is None:
            if a.raw is None:
                raise ValueError(f'macro {a.code + 1}: length unknown')
            macro_len = a.raw[2] | a.raw[3] << 8
        return bytes([0x11, a.code | (0x80 if a.repeat else 0), macro_len & 0xFF, macro_len >> 8])
    if a.raw is not None and decode_action(a.raw) == a:
        return a.raw
    if a.kind in SIMPLE:
        # VCFG sends left click as 01 01 on a side button, 01 00 on button 1.
        extra = 1 if a.kind == 'left' and slot != 0 else 0
        return bytes([SIMPLE[a.kind][0], extra, 0, 0])
    if a.kind == 'disable':
        return bytes([0x0E, 0, 0, 0])
    if a.kind == 'media':
        return bytes([0x0E, 0, a.code & 0xFF, a.code >> 8])
    if a.kind == 'shortcut':
        return bytes([0x0F, a.mods, a.code, a.code2])
    if a.kind == 'key':
        return bytes([0x10, 0, a.code, 0])
    if a.kind == 'fire':
        return bytes([0x19, a.code, a.times, a.delay])
    if a.kind == 'unknown' and a.raw is not None:
        return a.raw
    raise ValueError(f'cannot encode action {a}')


def fire_target_name(code):
    if code & 0x80:
        for name, bit in MOUSE_BITS.items():
            if code & 0x7F == bit:
                return name
        return f'0x{code:02x}'
    return keys.key_name(code)


def action_to_str(a):
    """Command-line form, e.g. 'key:Q' or 'shortcut:Ctrl+Shift+Z'."""
    if a.kind in SIMPLE or a.kind == 'disable':
        return a.kind
    if a.kind == 'media':
        return 'media:' + keys.media_slug(a.code)
    if a.kind == 'key':
        return 'key:' + keys.key_name(a.code)
    if a.kind == 'shortcut':
        return 'shortcut:' + keys.shortcut_name(a.mods, a.code, a.code2)
    if a.kind == 'fire':
        return f'fire:{fire_target_name(a.code)},{a.times},{a.delay}'
    if a.kind == 'macro':
        return f'macro:{a.code + 1}' + (',repeat' if a.repeat else '')
    return 'unknown:' + (a.raw.hex() if a.raw else '')


def describe_action(a):
    """Human-readable label, e.g. 'Media: Play/Pause'."""
    if a.kind in SIMPLE:
        return SIMPLE[a.kind][1]
    if a.kind == 'disable':
        return 'Disabled'
    if a.kind == 'media':
        return 'Media: ' + keys.CONSUMER.get(a.code, f'consumer usage 0x{a.code:03x}')
    if a.kind == 'key':
        return 'Key: ' + keys.key_name(a.code)
    if a.kind == 'shortcut':
        return 'Shortcut: ' + keys.shortcut_name(a.mods, a.code, a.code2)
    if a.kind == 'fire':
        target = fire_target_name(a.code)
        target = f'{target.capitalize()} click' if target in MOUSE_BITS else target
        return f'Fire key: {target} x{a.times}, {a.delay} ms apart'
    if a.kind == 'macro':
        return f'Macro {a.code + 1}' + (' (repeats while held)' if a.repeat else '')
    return 'Unknown action (' + (a.raw.hex(' ') if a.raw else '?') + ')'


def _int(text, low, high, what):
    try:
        value = int(text, 0)
    except ValueError:
        raise ValueError(f'{what} must be a number, got {text!r}') from None
    if not low <= value <= high:
        raise ValueError(f'{what} must be between {low} and {high}')
    return value


def parse_action(text):
    """Parse the command-line form of an action. Only verified encodings are accepted."""
    kind, _, arg = text.strip().partition(':')
    kind = SIMPLE_ALIASES.get(kind.lower(), kind.lower())
    if kind in SIMPLE or kind in ('disable', 'disabled'):
        if arg:
            raise ValueError(f'{kind} takes no parameter')
        return Action('disable' if kind == 'disabled' else kind)
    if kind == 'media':
        return Action('media', code=keys.media_code(arg))
    if kind == 'key':
        return Action('key', code=keys.key_code(arg))
    if kind in ('shortcut', 'combo'):
        mods, code, code2 = keys.parse_shortcut(arg)
        return Action('shortcut', code=code, mods=mods, code2=code2)
    if kind == 'fire':
        parts = [p.strip() for p in arg.split(',')]
        if len(parts) != 3:
            raise ValueError('fire needs target,times,delay_ms, e.g. fire:left,3,10')
        target = parts[0].lower()
        code = 0x80 | MOUSE_BITS[target] if target in MOUSE_BITS else keys.key_code(parts[0])
        return Action('fire', code=code, times=_int(parts[1], 1, 255, 'fire times'),
                      delay=_int(parts[2], 1, 255, 'fire delay (ms)'))
    if kind == 'macro':
        parts = [p.strip().lower() for p in arg.split(',')]
        repeat = parts[1:] == ['repeat']
        if parts[1:] and not repeat:
            raise ValueError("macro takes a slot number and optionally ',repeat'")
        return Action('macro', code=_int(parts[0], 1, 255, 'macro slot') - 1, repeat=repeat)
    if kind == 'unknown':
        raise ValueError('unknown actions can only be kept, not assigned')
    raise ValueError(f'unknown action {text!r} (run "valkyrie actions" for the list)')


def decode_buttons(b):
    """57-byte button table -> 14 actions in VCFG button order."""
    b = bytes(b)
    if len(b) != 1 + 4 * BUTTONS or b[0] != BUTTONS:
        raise ValueError(f'unexpected button table: {b[:8].hex(" ")}...')
    actions = [None] * BUTTONS
    for slot, button in enumerate(SLOT_BUTTONS):
        actions[button - 1] = decode_action(b[1 + 4 * slot:5 + 4 * slot])
    return actions


def encode_buttons(actions, macro_lengths=None):
    """actions in VCFG button order; macro_lengths maps macro slot -> byte length."""
    macro_lengths = macro_lengths or {}
    out = bytearray([BUTTONS])
    for slot, button in enumerate(SLOT_BUTTONS):
        a = actions[button - 1]
        out += encode_action(a, slot, macro_lengths.get(a.code) if a.kind == 'macro' else None)
    return bytes(out)


# --- DPI, light, polling --------------------------------------------------------

@dataclass
class DpiLevel:
    enabled: bool
    x: int                      # DPI the mouse uses (a multiple of 250)
    y: int
    extra: bytes = b'\0\0\0'    # trailing bytes, kept as read
    # DPI asked for, when it is not what the mouse uses (e.g. 1900 while the mouse
    # uses 2000). Kept on the PC (host.py) and in .pfd files, like VCFG does.
    req_x: int | None = None
    req_y: int | None = None

    @property
    def wanted(self):
        """(x, y) DPI asked for."""
        return (self.req_x or self.x, self.req_y or self.y)

    def set(self, x, y=None):
        """Ask for x (and y) DPI: the mouse gets max(x, y) on its 250 grid for both
        axes, like VCFG, and the exact values are kept as requested."""
        y = x if y is None else y
        hw = snap_dpi(max(x, y))
        self.x = self.y = hw
        self.req_x = x if x != hw else None
        self.req_y = y if y != hw else None

    @property
    def exact(self):
        """True when the mouse itself gives the DPI asked for."""
        return self.wanted == (self.x, self.y)


def snap_dpi(value):
    """The DPI the mouse uses for `value`: the nearest step of 250 (a tie goes
    down), at least 250 and at most 4000, like VCFG's Dpi_SnapToIndex."""
    steps = range(DPI_STEP, DPI_MAX + 1, DPI_STEP)
    return min(steps, key=lambda s: (abs(value - s), s))


def dpi_value(text):
    """A DPI asked for (250-4000, in steps of 50). The mouse uses snap_dpi() of it."""
    value = _int(str(text), 1, 100000, 'DPI')
    if not DPI_MIN <= value <= DPI_MAX:
        raise ValueError(f'DPI must be between {DPI_MIN} and {DPI_MAX}')
    if value % DPI_FINE_STEP:
        value = (value + DPI_FINE_STEP // 2) // DPI_FINE_STEP * DPI_FINE_STEP
    return value


def decode_dpi(b):
    """42-byte DPI block -> (count byte, selected index, levels)."""
    b = bytes(b)
    if len(b) != 2 + 8 * DPI_LEVELS:
        raise ValueError('DPI block must be 42 bytes')
    levels = []
    for i in range(DPI_LEVELS):
        e = b[2 + 8 * i:10 + 8 * i]
        x, y = e[1] | e[2] << 8, e[3] | e[4] << 8
        levels.append(DpiLevel(bool(e[0]), x * DPI_STEP, y * DPI_STEP, e[5:8]))
    return b[0], b[1], levels


def encode_dpi(count, selected, levels):
    out = bytearray([count, selected])
    for lv in levels:
        if lv.enabled:
            x, y = lv.x // DPI_STEP, lv.y // DPI_STEP
            out += bytes([1, x & 0xFF, x >> 8, y & 0xFF, y >> 8]) + lv.extra
        else:
            out += bytes(5) + lv.extra      # VCFG sends a disabled level as zeros
    return bytes(out)


@dataclass
class Light:
    rgb: tuple
    brightness: int
    breathing: int
    extra: int = 0


def decode_light(b):
    r, g, bl, brightness, breathing, extra = bytes(b)
    return Light((255 - r, 255 - g, 255 - bl), brightness, breathing, extra)


def encode_light(light):
    r, g, b = light.rgb
    return bytes([255 - r, 255 - g, 255 - b, light.brightness, light.breathing, light.extra])


def light_color(text):
    t = text.strip().lstrip('#')
    if len(t) != 6:
        raise ValueError(f'colour must look like #RRGGBB, got {text!r}')
    try:
        return tuple(int(t[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        raise ValueError(f'colour must look like #RRGGBB, got {text!r}') from None


def named_value(table, text, what):
    """Reverse lookup in BRIGHTNESS/BREATHING by name."""
    for value, name in table.items():
        if name == text.strip().lower():
            return value
    raise ValueError(f'{what} must be one of: ' + ', '.join(table.values()))


def polling_value(hz):
    for value, rate in POLLING_HZ.items():
        if rate == int(hz):
            return value
    raise ValueError('polling rate must be 125, 250, 500 or 1000')


# --- Windows pointer settings --------------------------------------------------

@dataclass
class WindowsSettings:
    """Pointer settings VCFG and VMON apply to Windows itself for each profile
    (Win_ApplyMouseSettings in VCFG.exe). The mouse does not store them; on Linux
    the desktop's own mouse settings do this job, so valkyrie only keeps them for
    .pfd files used on Windows."""
    scroll_lines: int = 3        # SPI_SETWHEELSCROLLLINES (VCFG: 1-10)
    double_click_ms: int = 550   # SetDoubleClickTime (VCFG: 200-900)
    pointer_speed: int = 10      # SPI_SETMOUSESPEED (1-20, 10 = no change)
    acceleration: int = 0        # 0-3, VCFG's levels of "enhance pointer precision"

    RANGES = {'scroll_lines': (1, 100), 'double_click_ms': (1, 5000),
              'pointer_speed': (1, 20), 'acceleration': (0, 3)}

    def check(self):
        for name, (low, high) in self.RANGES.items():
            value = getattr(self, name)
            if not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f'Windows setting {name} must be between {low} and {high}')
        return self


# --- Profiles ------------------------------------------------------------------

@dataclass
class Profile:
    polling: int                 # interval byte: 1, 2, 4 or 8 ms
    dpi_count: int
    dpi_selected: int            # 0-based
    dpi_levels: list
    light: Light
    buttons: list                # VCFG button order: buttons[0] is button 1
    windows: WindowsSettings | None = None    # PC side, not in the mouse

    @property
    def polling_hz(self):
        return POLLING_HZ.get(self.polling)

    def macro_slots(self):
        return sorted({a.code for a in self.buttons if a.kind == 'macro'})


def decode_profile(dpi, buttons, light, polling):
    """Byte blocks as stored in the mouse (polling is a 1-byte block) -> Profile."""
    count, selected, levels = decode_dpi(dpi)
    return Profile(polling[0], count, selected, levels, decode_light(light), decode_buttons(buttons))


def encode_profile(p, macro_lengths=None):
    """-> dict with the 'dpi', 'buttons', 'light' and 'polling' byte blocks."""
    return {
        'dpi': encode_dpi(p.dpi_count, p.dpi_selected, p.dpi_levels),
        'buttons': encode_buttons(p.buttons, macro_lengths),
        'light': encode_light(p.light),
        'polling': bytes([p.polling]),
    }


# --- Macros ------------------------------------------------------------------------

@dataclass(frozen=True)
class MacroStep:
    kind: str           # 'key', 'mouse', 'delay' or 'unknown'
    code: int           # HID key, mouse bit (1 left, 2 right, 4 middle), milliseconds or raw
    pressed: bool = False


@dataclass
class Macro:
    steps: list
    loops: int = 1
    raw: bytes | None = field(default=None, compare=False)


def _key_flag(code):
    # Macros written by VCFG store modifier keys (Ctrl, Shift, Alt, Win) with
    # a 01 after the key code, e.g. 84 e5 01 for Right Shift down.
    return 1 if 0xE0 <= code <= 0xE7 else 0


def decode_macro(b):
    """Macro bytes (up to the 07 end marker) -> Macro."""
    b = bytes(b)
    steps = []
    for i in range(0, len(b) - 2, 3):
        t, lo, hi = b[i], b[i + 1], b[i + 2]
        pressed = bool(t & 0x80)
        if t == 0x07:
            return Macro(steps, max(1, lo), raw=b[:i + 3])
        if t == 0x06:
            steps.append(MacroStep('delay', lo | hi << 8))
        elif t & 0x7F == 4 and hi == _key_flag(lo):
            steps.append(MacroStep('key', lo, pressed))
        elif t & 0x7F == 1 and hi == 0:
            steps.append(MacroStep('mouse', lo, pressed))
        else:
            steps.append(MacroStep('unknown', t << 16 | lo << 8 | hi))
    raise ValueError('macro has no end marker')


def encode_macro(m):
    if m.raw is not None and decode_macro(m.raw) == m:
        return m.raw
    out = bytearray()
    for s in m.steps:
        if s.kind == 'delay':
            out += bytes([0x06, s.code & 0xFF, s.code >> 8])
        elif s.kind == 'key':
            out += bytes([0x84 if s.pressed else 0x04, s.code, _key_flag(s.code)])
        elif s.kind == 'mouse':
            out += bytes([0x81 if s.pressed else 0x01, s.code, 0])
        else:
            raise ValueError(f'cannot encode macro step {s}')
    out += bytes([0x07, 0 if m.loops == 1 else m.loops, 0])   # VCFG sends 1 loop as 0
    if len(m.steps) > MACRO_MAX_STEPS:
        raise ValueError(f'macro too long: {len(m.steps)} steps, the limit is {MACRO_MAX_STEPS}')
    return bytes(out)


def step_to_str(s):
    state = 'down' if s.pressed else 'up'
    if s.kind == 'delay':
        return f'wait {s.code} ms'
    if s.kind == 'key':
        return f'{keys.key_name(s.code)} {state}'
    if s.kind == 'mouse':
        name = next((n for n, bit in MOUSE_BITS.items() if bit == s.code), f'0x{s.code:02x}')
        return f'mouse:{name} {state}'
    return f'unknown step 0x{s.code:06x}'


def parse_steps(text):
    """'A down, wait 100, A up, mouse:left down' -> [MacroStep, ...]"""
    steps = []
    for item in (p.strip() for p in text.split(',')):
        if not item:
            continue
        words = item.split()
        if words[0].lower() == 'wait':
            if len(words) not in (2, 3) or (len(words) == 3 and words[2].lower() != 'ms'):
                raise ValueError(f'bad wait step: {item!r} (use "wait 100")')
            steps.append(MacroStep('delay', _int(words[1], 1, 65535, 'wait (ms)')))
            continue
        if len(words) != 2 or words[1].lower() not in ('down', 'up'):
            raise ValueError(f'bad macro step: {item!r} (use "A down", "A up", '
                             '"mouse:left down" or "wait 100")')
        pressed = words[1].lower() == 'down'
        if words[0].lower().startswith('mouse:'):
            name = words[0][6:].lower()
            if name not in MOUSE_BITS:
                raise ValueError(f'unknown mouse button {name!r} (left, right, middle)')
            steps.append(MacroStep('mouse', MOUSE_BITS[name], pressed))
        else:
            steps.append(MacroStep('key', keys.key_code(words[0]), pressed))
    if not steps:
        raise ValueError('macro has no steps')
    return steps
