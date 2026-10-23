"""Show a Drakkar Valkyrie VCFG profile (.pfd) in human-readable form.

A .pfd file holds one profile: 14 button assignments, DPI levels, polling rate,
light colour and the Windows pointer settings VCFG applies with the profile. It
is a raw copy of VCFG's 121,400-byte profile record. The layout was worked out
by comparing VCFG's saved files with the USB traffic VCFG sends to the mouse,
then checked against the encoder functions in VCFG.exe.

Usage: pfd2txt.py [--json] FILE.pfd [FILE.pfd ...]
"""
import argparse
import datetime
import json
import os
import struct
import sys

from . import model
from .keys import CONSUMER, hid_to_vcfg, key_name, vcfg_to_hid, vk_name

PFD_SIZE = 121400

# Button records: the fixed header (index, function, category, action type,
# parameter) sits at HEADER0 + n * STRIDE; the action's data lives in the
# REC_DATA bytes just before it.
HEADER0 = 0x139C
STRIDE = 0x1048
REC_DATA = 0x1034
BUTTONS = 14

# Windows pointer settings (Win_ApplyMouseSettings in VCFG.exe)
SCROLL_LINES = 0x1287C         # u32
DOUBLE_CLICK = 0x12880         # u16, ms
POINTER_SPEED = 0x12882        # u16, 1-20
ACCELERATION = 0x12884         # u16, 0-3
POLLING = 0x12888
DPI_SELECTED = 0x1288C
DPI_TABLE = 0x128B0
DPI_COUNT = 0x1291E
LIGHT = 0x15136

MOUSE_ACTIONS = {t: label for t, label in model.SIMPLE.values()}
MOUSE_BUTTONS = {1: 'Left click', 2: 'Right click', 4: 'Middle click'}
FIRE_TARGETS = {0x81: 'Left click', 0x82: 'Right click', 0x84: 'Middle click'}

BRIGHTNESS = {0: 'Off', 1: 'Low', 2: 'Medium', 3: 'High'}
# Breathing value is a period: bigger means slower.
BREATHING = {0: 'Off (full brightness)', 1: 'High speed', 3: 'Medium speed', 6: 'Low speed'}

# Modifier flags used by VCFG shortcuts (checked against the mouse: Ctrl+W is 2,
# Ctrl+Shift+Tab is 6, Alt+F4 is 1, Win+D is 8). The mouse itself uses HID bits.
MODIFIERS = [(0x02, 'Ctrl'), (0x04, 'Shift'), (0x01, 'Alt'), (0x08, 'Win')]


def u16(d, o):
    return struct.unpack_from('<H', d, o)[0]


def u32(d, o):
    return struct.unpack_from('<I', d, o)[0]


def utf16z(d, o, maxlen=64):
    raw = d[o:o + maxlen * 2]
    end = next((i for i in range(0, len(raw) - 1, 2) if raw[i:i + 2] == b'\0\0'), len(raw))
    return raw[:end].decode('utf-16-le', errors='replace')


def _key_text(vk, flag):
    """Name of the key VCFG sends for a stored VK code and flag."""
    try:
        return key_name(vcfg_to_hid(vk, flag))
    except ValueError:
        return vk_name(vk)


def windows_settings(d):
    return model.WindowsSettings(u32(d, SCROLL_LINES), u16(d, DOUBLE_CLICK),
                                 u16(d, POINTER_SPEED), u16(d, ACCELERATION))


def decode_button(d, n):
    hdr = HEADER0 + n * STRIDE
    data = hdr - REC_DATA
    func, category = u16(d, hdr + 2), u32(d, hdr + 4)
    kind, param = u32(d, hdr + 8), u32(d, hdr + 12)
    raw = dict(function=func, category=category, type=kind, param=param)

    if kind in MOUSE_ACTIONS:
        text = MOUSE_ACTIONS[kind]
    elif kind == 0x0E:
        usage = d[data + 0x8C] | d[data + 0x8E] << 8   # low and high byte, each in a u16
        text = 'Disabled' if usage == 0 else 'Media: ' + CONSUMER.get(usage, f'consumer usage 0x{usage:03x}')
        raw['usage'] = usage
    elif kind == 0x10:
        vk, flag = u16(d, data + 0x02), u16(d, data + 0x04)
        label = utf16z(d, data + 0x06)
        text = 'Key: ' + _key_text(vk, flag) + (f'  ("{label}")' if label else '')
        raw.update(vk=vk, flag=flag)
    elif kind == 0x0F:
        vk, flag, vk2, flag2 = struct.unpack_from('<4H', d, data + 0x44)
        mods = u16(d, data + 0x4C)        # upper half is leftover memory
        names = [name for bit, name in MODIFIERS if mods & bit]
        names.append(_key_text(vk, flag))
        if vk2:
            names.append(_key_text(vk2, flag2))
        text = 'Shortcut: ' + '+'.join(names)
        raw.update(vk=vk, flag=flag, modifiers=mods)
        if vk2:
            raw.update(vk2=vk2, flag2=flag2)
    elif kind == 0x19:
        shots, delay, target = u16(d, data + 0xFE4), u16(d, data + 0xFE6), u16(d, data + 0xFE8)
        what = FIRE_TARGETS.get(target) or ('Key ' + key_name(target) if target < 0x80 else f'target 0x{target:02x}')
        text = f'Fire key: {what} x{shots}, {delay} ms apart'
        raw.update(shots=shots, delay_ms=delay, target=target)
    elif kind == 0x11:
        name, count = utf16z(d, data + 0x10E), u32(d, data + 0x44C)
        repeat = bool(u16(d, data + 0x452))
        loops = max(1, u16(d, data + 0x454))  # 0 means run once, like on the mouse
        steps = []
        # 6-byte steps: type (1 mouse, 4 keyboard, 6 delay), pressed, code
        for o in range(data + 0x14C, data + 0x14C + 6 * min(count, 128), 6):
            etype, pressed, code = struct.unpack_from('<3H', d, o)
            state = 'down' if pressed else 'up'
            if etype == 4:
                steps.append(f'{_key_text(code & 0xFF, code >> 8)} {state}')
            elif etype == 1:
                steps.append(f'{MOUSE_BUTTONS.get(code, f"mouse button {code}")} {state}')
            elif etype == 6:
                steps.append(f'wait {code} ms')
            else:
                steps.append(f'step type {etype} ({pressed}, 0x{code:02x})')
        runs = 'repeats while held' if repeat else f'runs {loops}x'
        text = f'Macro "{name}" ({runs}): ' + ', '.join(steps)
        raw.update(macro=name, loops=loops, repeat_while_held=repeat, steps=steps)
    else:
        text = f'Unknown action type 0x{kind:02x} (param {param})'
    return dict(button=n + 1, action=text, raw=raw)


def parse(path):
    with open(path, 'rb') as f:
        d = f.read()
    if len(d) != PFD_SIZE or d[:2] != b'\x03\x01':
        raise ValueError(f'{path}: not a Drakkar Valkyrie profile '
                         f'(expected {PFD_SIZE} bytes starting with 03 01)')

    created = datetime.datetime(1899, 12, 30) + datetime.timedelta(
        days=struct.unpack_from('<d', d, 0x40)[0])

    levels = []
    for i in range(u16(d, DPI_COUNT)):
        o = DPI_TABLE + i * 10
        x, y, enabled = u16(d, o), u16(d, o + 2), u16(d, o + 4)
        mouse = model.snap_dpi(max(x, y)) if x and y else 0      # what VCFG sends for X and Y
        levels.append(dict(level=i + 1, x=x, y=y, enabled=bool(enabled), mouse_x=mouse, mouse_y=mouse))

    r, g, b, level, speed = d[LIGHT:LIGHT + 5]
    return dict(
        file=path,
        created=created.strftime('%Y-%m-%d %H:%M'),
        polling_hz=u32(d, POLLING),
        dpi_selected=u32(d, DPI_SELECTED) + 1,
        dpi_levels=levels,
        light=dict(rgb=f'#{r:02X}{g:02X}{b:02X}', brightness=level, breathing=speed),
        buttons=[decode_button(d, n) for n in range(BUTTONS)],
        windows=vars(windows_settings(d)),
    )


def format_text(p):
    out = [p['file'], '=' * len(p['file']),
           f"Created          {p['created']}",
           f"Polling rate     {p['polling_hz']} Hz",
           f"DPI levels       {len(p['dpi_levels'])}, selected: level {p['dpi_selected']}"]
    for lv in p['dpi_levels']:
        dpi = f"{lv['x']}" if lv['x'] == lv['y'] else f"{lv['x']} x {lv['y']}"
        sent = f"{lv['mouse_x']}" if lv['mouse_x'] == lv['mouse_y'] else f"{lv['mouse_x']} x {lv['mouse_y']}"
        state = '' if lv['enabled'] else '  (disabled)'
        out.append(f"  level {lv['level']}        {dpi:>5} DPI  (mouse uses {sent}){state}")
    light = p['light']
    pick = lambda names, v: names.get(v, f'unknown ({v})')
    out.append(f"Light colour     {light['rgb']}")
    out.append(f"Brightness       {pick(BRIGHTNESS, light['brightness'])}")
    out.append(f"Breathing        {pick(BREATHING, light['breathing'])}")
    out.append('Buttons')
    for btn in p['buttons']:
        out.append(f"  {btn['button']:2d}  {btn['action']}")
    w = p['windows']
    out.append('Windows settings (applied by VCFG on Windows)')
    out.append(f"  scroll lines {w['scroll_lines']}, double-click {w['double_click_ms']} ms, "
               f"pointer speed {w['pointer_speed']}, acceleration {w['acceleration']}")
    return '\n'.join(out)


# --- Conversion to the mouse's model (import) --------------------------------

# .pfd shortcut modifier bits (Alt 1, Ctrl 2, Shift 4, Win 8) -> HID bits.
PFD_TO_HID_MODS = {0x01: 0x04, 0x02: 0x01, 0x04: 0x02, 0x08: 0x08}
MACRO_PARAM0 = 1102            # VCFG's parameter for Macro1 (library index 0)


def _hid_mods(pfd_mods):
    mods = 0
    for bit, hid in PFD_TO_HID_MODS.items():
        if pfd_mods & bit:
            mods |= hid
    if pfd_mods & ~0x0F:
        raise ValueError(f'unknown shortcut modifier bits 0x{pfd_mods:x}')
    return mods


def _import_action(d, n):
    """Button n of a .pfd -> (model.Action, model.Macro or None)."""
    hdr = HEADER0 + n * STRIDE
    data = hdr - REC_DATA
    kind, param = u32(d, hdr + 8), u32(d, hdr + 12)
    simple = {t: name for name, (t, _) in model.SIMPLE.items()}
    if kind in simple:
        return model.Action(simple[kind]), None
    if kind == 0x0E:
        usage = d[data + 0x8C] | d[data + 0x8E] << 8
        return model.Action('disable' if usage == 0 else 'media', code=usage), None
    if kind == 0x10:
        return model.Action('key', code=vcfg_to_hid(u16(d, data + 0x02), u16(d, data + 0x04))), None
    if kind == 0x0F:
        vk, flag, vk2, flag2 = struct.unpack_from('<4H', d, data + 0x44)
        return model.Action('shortcut', code=vcfg_to_hid(vk, flag), mods=_hid_mods(u16(d, data + 0x4C)),
                            code2=vcfg_to_hid(vk2, flag2) if vk2 else 0), None
    if kind == 0x19:
        shots, delay, target = u16(d, data + 0xFE4), u16(d, data + 0xFE6), u16(d, data + 0xFE8)
        if target not in FIRE_TARGETS and not 0 < target < 0x80:
            raise ValueError(f'button {n + 1}: unknown fire key target 0x{target:x}')
        return model.Action('fire', code=target, times=shots, delay=delay), None
    if kind == 0x11:
        slot = param - MACRO_PARAM0
        if not 0 <= slot < 0x7F:
            raise ValueError(f'button {n + 1}: unexpected macro number {param}')
        count = u32(d, data + 0x44C)
        if count > model.MACRO_MAX_STEPS:
            raise ValueError(f'button {n + 1}: the macro has {count} steps; VCFG and the mouse '
                             f'take at most {model.MACRO_MAX_STEPS}')
        steps = []
        for o in range(data + 0x14C, data + 0x14C + 6 * count, 6):
            etype, pressed, code = struct.unpack_from('<3H', d, o)
            if etype == 4:      # VK code, and the extended-key flag in the high byte
                steps.append(model.MacroStep('key', vcfg_to_hid(code & 0xFF, code >> 8), bool(pressed)))
            elif etype == 1 and code in MOUSE_BUTTONS:
                steps.append(model.MacroStep('mouse', code, bool(pressed)))
            elif etype == 6:
                steps.append(model.MacroStep('delay', code))
            else:
                raise ValueError(f'button {n + 1}: unknown macro step type {etype}')
        repeat = bool(u16(d, data + 0x452))
        macro = model.Macro(steps, max(1, u16(d, data + 0x454)))
        return model.Action('macro', code=slot, repeat=repeat), macro
    raise ValueError(f'button {n + 1}: unknown action type 0x{kind:02x}')


def to_profile(path):
    """Read a .pfd as the mouse would store it: (model.Profile, {macro slot: model.Macro})."""
    with open(path, 'rb') as f:
        d = f.read()
    if len(d) != PFD_SIZE or d[:2] != b'\x03\x01':
        raise ValueError(f'{path}: not a Drakkar Valkyrie profile')
    if u16(d, DPI_COUNT) != model.DPI_LEVELS:
        raise ValueError(f'{path}: expected {model.DPI_LEVELS} DPI levels')
    levels = []
    for i in range(model.DPI_LEVELS):
        o = DPI_TABLE + i * 10
        x, y, enabled = u16(d, o), u16(d, o + 2), u16(d, o + 4)
        # The file holds the DPI asked for; the mouse gets max(x, y) on its grid for
        # both axes. A level that is off sends zeros; its value is kept for later.
        level = model.DpiLevel(bool(enabled), 0, 0)
        if x and y:
            level.set(min(max(x, model.DPI_MIN), model.DPI_MAX), min(max(y, model.DPI_MIN), model.DPI_MAX))
        elif enabled:
            raise ValueError(f'{path}: DPI level {i + 1} is on but has no value')
        levels.append(level)
    selected = u32(d, DPI_SELECTED)
    if not (0 <= selected < model.DPI_LEVELS and levels[selected].enabled):
        raise ValueError(f'{path}: selected DPI level {selected + 1} is not usable')
    r, g, b, brightness, breathing = d[LIGHT:LIGHT + 5]
    buttons, macros = [], {}
    for n in range(BUTTONS):
        action, macro = _import_action(d, n)
        buttons.append(action)
        if macro is not None:
            macros[action.code] = macro
    profile = model.Profile(model.polling_value(u32(d, POLLING)), model.DPI_LEVELS, selected, levels,
                            model.Light((r, g, b), brightness, breathing), buttons,
                            windows_settings(d))
    return profile, macros



# --- Writing .pfd files (export) ------------------------------------------------

TEMPLATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'template.pfd')

# VCFG's list of button functions: function -> (action type, parameter). Copied
# from the table at offset 0x24d434 of VCFG.exe (48 entries of 3 u32 values).
FUNCTIONS = {
    0: (0x01, 1), 1: (0x02, 2), 2: (0x03, 3), 3: (0x05, 4), 4: (0x04, 5), 5: (0x10, 6),
    6: (0x0F, 7), **{f: (0x0F, 794 + f) for f in range(7, 15)},
    **{f: (0x0F, 886 + f) for f in range(15, 21)}, **{f: (0x0E, 886 + f) for f in range(21, 29)},
    **{f: (0x0E, 972 + f) for f in range(29, 37)}, 37: (0x11, 11), 38: (0x19, 12), 39: (0x08, 13),
    40: (0x08, 1301), 41: (0x0A, 1302), 42: (0x09, 1303), 43: (0x0D, 14), 44: (0x08, 15),
    45: (0x17, 1501), 46: (0x18, 1502), 47: (0x0E, 16),
}
# Category VCFG stores with each function, as seen in its own files. Functions
# missing here have never been seen in a VCFG file, so they are not exported.
CATEGORIES = {0: 1, 1: 1, 2: 1, 3: 1, 4: 1, 5: 8, 6: 3, 16: 3, 19: 3,
              **{f: 10 for f in range(21, 28)}, **{f: 10 for f in range(29, 37)},
              37: 4, 38: 13, 40: 1, 41: 1, 42: 1, 43: 1, 45: 1, 46: 1, 47: 10}
SIMPLE_FUNCTIONS = {'left': 0, 'right': 1, 'middle': 2, 'forward': 3, 'back': 4,
                    'dpi-cycle': 40, 'dpi-up': 41, 'dpi-down': 42, 'profile-switch': 43,
                    'rate-up': 45, 'rate-down': 46}
MEDIA_FUNCTIONS = {0x223: 21, 0x224: 22, 0x225: 23, 0x226: 24, 0x227: 25, 0x221: 26, 0x22A: 27,
                   0xCD: 29, 0xB7: 30, 0xB6: 31, 0xB5: 32, 0xE9: 33, 0xEA: 34, 0xE2: 35, 0x183: 36}
DISABLE = 47
CUSTOM_SHORTCUT = 6            # VCFG's "combo key" entry; the keys are in the record
PRESET_SHORTCUTS = {(0x04, 0x3D): 16, (0x08, 0x07): 19}     # (HID mods, key): Alt+F4, Win+D
KEY, MACRO, FIRE = 5, 37, 38
HID_TO_PFD_MODS = {hid: bit for bit, hid in PFD_TO_HID_MODS.items()}
LEFT_ON_SIDE_BUTTON = 0x102C   # flag VCFG sets for left click on a button other than 1


def _utf16(text):
    return text.encode('utf-16-le') + b'\0\0'


def _record(action, n, macros):
    """Data area and (function, category, type, parameter) for one button."""
    data = bytearray(REC_DATA)
    kind = action.kind
    if kind in SIMPLE_FUNCTIONS:
        func = SIMPLE_FUNCTIONS[kind]
        if kind == 'left' and n != 0:
            data[LEFT_ON_SIDE_BUTTON] = 1
    elif kind == 'key':
        func = KEY
        struct.pack_into('<HH', data, 0x02, *hid_to_vcfg(action.code))
    elif kind == 'shortcut':
        func = CUSTOM_SHORTCUT if action.code2 else \
            PRESET_SHORTCUTS.get((action.mods, action.code), CUSTOM_SHORTCUT)
        mods = 0
        for hid, bit in HID_TO_PFD_MODS.items():
            if action.mods & hid:
                mods |= bit
        second = hid_to_vcfg(action.code2) if action.code2 else (0, 0)
        struct.pack_into('<5H', data, 0x44, *hid_to_vcfg(action.code), *second, mods)
    elif kind == 'media' and action.code in MEDIA_FUNCTIONS:
        func = MEDIA_FUNCTIONS[action.code]
        struct.pack_into('<HH', data, 0x8C, action.code & 0xFF, action.code >> 8)
    elif kind == 'disable':
        func = DISABLE
    elif kind == 'fire':
        func = FIRE
        # Target: 0x81/0x82/0x84 for a mouse button, or a HID key followed by its VK code.
        vk = 0 if action.code in FIRE_TARGETS else hid_to_vcfg(action.code)[0]
        struct.pack_into('<4H', data, 0xFE4, action.times, action.delay, action.code, vk)
    elif kind == 'macro':
        func = MACRO
        macro = macros.get(action.code)
        if macro is None:
            raise ValueError(f'button {n + 1}: macro {action.code + 1} has no content')
        if len(macro.steps) > model.MACRO_MAX_STEPS:
            raise ValueError(f'button {n + 1}: VCFG macros hold at most {model.MACRO_MAX_STEPS} steps')
        name = _utf16(f'Macro{action.code + 1}')
        data[0xD0:0xD0 + 32] = _utf16('DefaultMacroSet')
        data[0x10E:0x10E + len(name)] = name
        for i, step in enumerate(macro.steps):
            etype, code = {'key': (4, None), 'mouse': (1, step.code), 'delay': (6, step.code)}[step.kind]
            if code is None:
                vk, flag = hid_to_vcfg(step.code)
                code = vk | flag << 8
            struct.pack_into('<3H', data, 0x14C + 6 * i, etype, int(step.pressed), code)
        struct.pack_into('<IHHH', data, 0x44C, len(macro.steps), 1, int(action.repeat),
                         0 if macro.loops == 1 else macro.loops)
        data[0x45A:0x45A + len(name)] = name
    else:
        raise ValueError(f'button {n + 1}: VCFG has no menu entry for "{model.describe_action(action)}"')
    if func not in CATEGORIES:
        raise ValueError(f'button {n + 1}: "{model.describe_action(action)}" was never seen in a VCFG '
                         'file, so it cannot be exported yet')
    kind_byte, param = FUNCTIONS[func]
    if func == MACRO:
        param = MACRO_PARAM0 + action.code
    return data, (func, CATEGORIES[func], kind_byte, param)


def from_profile(profile, macros, template=TEMPLATE):
    """A .pfd file (bytes) holding profile and the macros it uses ({slot: Macro})."""
    with open(template, 'rb') as f:
        d = bytearray(f.read())
    if len(d) != PFD_SIZE:
        raise ValueError(f'{template}: not a VCFG profile')
    for n, action in enumerate(profile.buttons):
        hdr = HEADER0 + n * STRIDE
        if n == BUTTONS - 1:
            # The switch under the mouse; VCFG keeps a fixed record for it.
            if action.kind != 'profile-switch':
                raise ValueError('button 14 must be the profile switch')
            continue
        data, (func, category, kind, param) = _record(action, n, macros)
        d[hdr - REC_DATA:hdr] = data
        struct.pack_into('<HHIII', d, hdr, n, func, category, kind, param)
    struct.pack_into('<II', d, POLLING, profile.polling_hz or 0, profile.dpi_selected)
    if not profile.polling_hz:
        raise ValueError(f'unknown polling value {profile.polling}')
    for i, lv in enumerate(profile.dpi_levels):
        struct.pack_into('<HHH', d, DPI_TABLE + 10 * i, *lv.wanted, int(lv.enabled))
    struct.pack_into('<H', d, DPI_COUNT, len(profile.dpi_levels))
    w = (profile.windows or model.WindowsSettings()).check()
    struct.pack_into('<I', d, SCROLL_LINES, w.scroll_lines)
    struct.pack_into('<HHH', d, DOUBLE_CLICK, w.double_click_ms, w.pointer_speed, w.acceleration)
    d[LIGHT:LIGHT + 5] = bytes([*profile.light.rgb, profile.light.brightness, profile.light.breathing])
    return bytes(d)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--json', action='store_true', help='print JSON instead of text')
    ap.add_argument('files', nargs='+', metavar='FILE.pfd')
    args = ap.parse_args()
    status = 0
    profiles = []
    for path in args.files:
        try:
            profiles.append(parse(path))
        except (OSError, ValueError) as e:
            print(e, file=sys.stderr)
            status = 1
    if args.json:
        print(json.dumps(profiles, indent=2))
    else:
        print('\n\n'.join(format_text(p) for p in profiles))
    return status
