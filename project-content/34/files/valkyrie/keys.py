"""Key and media-key names.

The mouse uses USB HID codes: keyboard usages (page 0x07) for keys and consumer
usages (page 0x0C) for media keys. VCFG's .pfd files use Windows virtual-key
(VK) codes instead, so this module also maps VK codes to HID usages.

Key names follow the US layout, because HID usages name physical key
positions: on an AZERTY keyboard, the key called "Q" here types "A".
"""

# --- Keyboard usages -------------------------------------------------------

HID_KEYS = {
    0x28: 'Enter', 0x29: 'Esc', 0x2A: 'Backspace', 0x2B: 'Tab', 0x2C: 'Space',
    0x2D: 'Minus', 0x2E: 'Equal', 0x2F: 'LeftBracket', 0x30: 'RightBracket',
    0x31: 'Backslash', 0x32: 'NonUSHash', 0x33: 'Semicolon', 0x34: 'Quote',
    0x35: 'Grave', 0x36: 'Comma', 0x37: 'Period', 0x38: 'Slash', 0x39: 'CapsLock',
    0x46: 'PrintScreen', 0x47: 'ScrollLock', 0x48: 'Pause', 0x49: 'Insert',
    0x4A: 'Home', 0x4B: 'PageUp', 0x4C: 'Delete', 0x4D: 'End', 0x4E: 'PageDown',
    0x4F: 'Right', 0x50: 'Left', 0x51: 'Down', 0x52: 'Up', 0x53: 'NumLock',
    0x54: 'NumSlash', 0x55: 'NumStar', 0x56: 'NumMinus', 0x57: 'NumPlus', 0x58: 'NumEnter',
    0x62: 'Num0', 0x63: 'NumPeriod', 0x64: 'NonUSBackslash', 0x65: 'Menu',
    0xE0: 'LeftCtrl', 0xE1: 'LeftShift', 0xE2: 'LeftAlt', 0xE3: 'LeftWin',
    0xE4: 'RightCtrl', 0xE5: 'RightShift', 0xE6: 'RightAlt', 0xE7: 'RightWin',
}
HID_KEYS.update({0x04 + n: chr(ord('A') + n) for n in range(26)})
HID_KEYS.update({0x1E + n: str((n + 1) % 10) for n in range(10)})
HID_KEYS.update({0x3A + n: f'F{n + 1}' for n in range(12)})
HID_KEYS.update({0x68 + n: f'F{n + 13}' for n in range(12)})
HID_KEYS.update({0x59 + n: f'Num{n + 1}' for n in range(9)})

KEY_ALIASES = {
    'escape': 'Esc', 'return': 'Enter', 'del': 'Delete', 'ins': 'Insert',
    'pgup': 'PageUp', 'pgdn': 'PageDown', 'pagedn': 'PageDown', 'prtsc': 'PrintScreen',
    'ctrl': 'LeftCtrl', 'control': 'LeftCtrl', 'shift': 'LeftShift', 'alt': 'LeftAlt',
    'win': 'LeftWin', 'super': 'LeftWin', 'meta': 'LeftWin', 'altgr': 'RightAlt',
    '-': 'Minus', '=': 'Equal', '[': 'LeftBracket', ']': 'RightBracket', '\\': 'Backslash',
    ';': 'Semicolon', "'": 'Quote', '`': 'Grave', ',': 'Comma', '.': 'Period', '/': 'Slash',
    'num/': 'NumSlash', 'num*': 'NumStar', 'num-': 'NumMinus', 'num.': 'NumPeriod',
}

_KEY_LOOKUP = {name.lower(): code for code, name in HID_KEYS.items()}
_KEY_LOOKUP.update({alias: _KEY_LOOKUP[name.lower()] for alias, name in KEY_ALIASES.items()})

# Shortcut modifier bits, as the mouse stores them (standard HID left modifiers).
MODIFIERS = [('Ctrl', 0x01), ('Shift', 0x02), ('Alt', 0x04), ('Win', 0x08)]
_MOD_LOOKUP = {'ctrl': 0x01, 'control': 0x01, 'shift': 0x02, 'alt': 0x04,
               'win': 0x08, 'super': 0x08, 'meta': 0x08}


def key_name(code):
    return HID_KEYS.get(code, f'0x{code:02x}')


def key_code(name):
    """HID usage for a key name such as 'Q', 'F4', 'Left' or '0x14'."""
    text = name.strip()
    if text.lower().startswith('0x'):
        code = int(text, 16)
        if not 0 < code < 0x100:
            raise ValueError(f'key code out of range: {name}')
        return code
    try:
        return _KEY_LOOKUP[text.lower()]
    except KeyError:
        raise ValueError(f'unknown key name: {name!r}') from None


def shortcut_name(mods, code, code2=0):
    names = [name for name, bit in MODIFIERS if mods & bit]
    if mods & ~0x0F:
        names.append(f'mods 0x{mods:02x}')
    return '+'.join(names + [key_name(code)] + ([key_name(code2)] if code2 else []))


def parse_shortcut(text):
    """'Ctrl+Shift+Z' or 'Ctrl+K+C' -> (modifier bits, HID usage, second HID usage or 0).
    Modifiers come first; one or two keys follow."""
    parts = [p.strip() for p in text.split('+') if p.strip()]
    if not parts:
        raise ValueError('empty shortcut')
    mods, codes = 0, []
    for i, part in enumerate(parts):
        if part.lower() in _MOD_LOOKUP and i < len(parts) - 1 and not codes:
            mods |= _MOD_LOOKUP[part.lower()]
        else:
            codes.append(key_code(part))
    if len(codes) > 2:
        raise ValueError(f'a shortcut has at most two keys besides Ctrl, Shift, Alt and Win: {text!r}')
    return mods, codes[0], codes[1] if len(codes) == 2 else 0


# --- Consumer (media) usages -------------------------------------------------

CONSUMER = {
    0xB5: 'Next track', 0xB6: 'Previous track', 0xB7: 'Stop', 0xCD: 'Play/Pause',
    0xE2: 'Mute', 0xE9: 'Volume up', 0xEA: 'Volume down',
    0x183: 'Media player', 0x18A: 'Email', 0x192: 'Calculator', 0x194: 'My computer',
    0x221: 'Browser search', 0x223: 'Browser home', 0x224: 'Browser back',
    0x225: 'Browser forward', 0x226: 'Browser stop', 0x227: 'Browser refresh',
    0x22A: 'Browser favorites',
}


def media_slug(usage):
    """Short name used on the command line: 'play-pause', 'volume-up', ..."""
    label = CONSUMER.get(usage)
    if label is None:
        return f'0x{usage:03x}'
    return label.lower().replace('/', '-').replace(' ', '-')


_MEDIA_LOOKUP = {media_slug(u): u for u in CONSUMER}
_MEDIA_LOOKUP.update({'mail': 0x18A, 'next': 0xB5, 'previous': 0xB6, 'prev': 0xB6,
                      'play': 0xCD, 'pause': 0xCD})


def media_code(name):
    text = name.strip().lower()
    if text.startswith('0x'):
        code = int(text, 16)
        if not 0 < code < 0x10000:
            raise ValueError(f'media code out of range: {name}')
        return code
    try:
        return _MEDIA_LOOKUP[text]
    except KeyError:
        raise ValueError(f'unknown media key: {name!r}') from None


# --- Windows virtual-key codes (used in VCFG .pfd files) ----------------------

VK = {
    0x08: 'Backspace', 0x09: 'Tab', 0x0D: 'Enter', 0x13: 'Pause', 0x14: 'Caps Lock',
    0x1B: 'Esc', 0x20: 'Space', 0x21: 'Page Up', 0x22: 'Page Down', 0x23: 'End',
    0x24: 'Home', 0x25: 'Left', 0x26: 'Up', 0x27: 'Right', 0x28: 'Down',
    0x2C: 'Print Screen', 0x2D: 'Insert', 0x2E: 'Delete', 0x5B: 'Left Win',
    0x5C: 'Right Win', 0x5D: 'Menu', 0x6A: 'Num *', 0x6B: 'Num +', 0x6D: 'Num -',
    0x6E: 'Num .', 0x6F: 'Num /', 0x90: 'Num Lock', 0x91: 'Scroll Lock',
    0xA0: 'Left Shift', 0xA1: 'Right Shift', 0xA2: 'Left Ctrl', 0xA3: 'Right Ctrl',
    0xA4: 'Left Alt', 0xA5: 'Right Alt', 0xBA: ';', 0xBB: '=', 0xBC: ',', 0xBD: '-',
    0xBE: '.', 0xBF: '/', 0xC0: '`', 0xDB: '[', 0xDC: '\\', 0xDD: ']', 0xDE: "'",
}
VK.update({c: chr(c) for c in range(0x30, 0x3A)})
VK.update({c: chr(c) for c in range(0x41, 0x5B)})
VK.update({0x60 + n: f'Num {n}' for n in range(10)})
VK.update({0x70 + n: f'F{n + 1}' for n in range(24)})

VK_TO_HID = {
    0x08: 0x2A, 0x09: 0x2B, 0x0D: 0x28, 0x10: 0xE1, 0x11: 0xE0, 0x12: 0xE2,
    0x13: 0x48, 0x14: 0x39, 0x1B: 0x29, 0x20: 0x2C, 0x21: 0x4B, 0x22: 0x4E,
    0x23: 0x4D, 0x24: 0x4A, 0x25: 0x50, 0x26: 0x52, 0x27: 0x4F, 0x28: 0x51,
    0x2C: 0x46, 0x2D: 0x49, 0x2E: 0x4C, 0x30: 0x27, 0x5B: 0xE3, 0x5C: 0xE7,
    0x5D: 0x65, 0x60: 0x62, 0x6A: 0x55, 0x6B: 0x57, 0x6D: 0x56, 0x6E: 0x63,
    0x6F: 0x54, 0x90: 0x53, 0x91: 0x47, 0xA0: 0xE1, 0xA1: 0xE5, 0xA2: 0xE0,
    0xA3: 0xE4, 0xA4: 0xE2, 0xA5: 0xE6, 0xBA: 0x33, 0xBB: 0x2E, 0xBC: 0x36,
    0xBD: 0x2D, 0xBE: 0x37, 0xBF: 0x38, 0xC0: 0x35, 0xDB: 0x2F, 0xDC: 0x31,
    0xDD: 0x30, 0xDE: 0x34, 0xE2: 0x64,
}
VK_TO_HID.update({0x41 + n: 0x04 + n for n in range(26)})        # A-Z
VK_TO_HID.update({0x31 + n: 0x1E + n for n in range(9)})         # 1-9
VK_TO_HID.update({0x61 + n: 0x59 + n for n in range(9)})         # numpad 1-9
VK_TO_HID.update({0x70 + n: 0x3A + n for n in range(12)})        # F1-F12
VK_TO_HID.update({0x7C + n: 0x68 + n for n in range(12)})        # F13-F24


def vk_name(code):
    return VK.get(code, f'key 0x{code:02x}')


def vk_to_hid(vk):
    try:
        return VK_TO_HID[vk]
    except KeyError:
        raise ValueError(f'no HID code known for Windows key 0x{vk:02x}') from None


# VCFG's own conversion (Key_VkToHid at 0x5c0b50 in VCFG.exe, tables from 0x64a728).
# A .pfd stores each key as a VK code plus a flag: 0, or 1 for an extended key (the
# arrow keys, Insert, Delete, Home, End, Page Up/Down and Enter on the keypad). The
# flag picks the table: VK_LEFT without it is Num 4, with it the Left arrow.
VCFG_VK = {
    0x08: 0x2A, 0x09: 0x2B, 0x0C: 0x9C, 0x0D: 0x28, 0x13: 0x48, 0x14: 0x39, 0x1B: 0x29,
    0x20: 0x2C, 0x21: 0x61, 0x22: 0x5B, 0x23: 0x59, 0x24: 0x5F, 0x25: 0x5C, 0x26: 0x60,
    0x27: 0x5E, 0x28: 0x5A, 0x2C: 0x46, 0x2D: 0x62, 0x2E: 0x63, 0x30: 0x27, 0x5B: 0xE3,
    0x5C: 0xE7, 0x5D: 0x65, 0x60: 0x62, 0x6A: 0x55, 0x6B: 0x57, 0x6C: 0x97, 0x6D: 0x56,
    0x6E: 0x63, 0x6F: 0x54, 0x90: 0x53, 0x91: 0x47, 0xA0: 0xE1, 0xA1: 0xE5, 0xA2: 0xE0,
    0xA3: 0xE4, 0xA4: 0xE2, 0xA5: 0xE6, 0xBA: 0x33, 0xBB: 0x2E, 0xBC: 0x36, 0xBD: 0x2D,
    0xBE: 0x37, 0xBF: 0x38, 0xC0: 0x35, 0xDB: 0x2F, 0xDC: 0x31, 0xDD: 0x30, 0xDE: 0x34,
    0xE2: 0x64,
}
VCFG_VK.update({0x41 + n: 0x04 + n for n in range(26)})        # A-Z
VCFG_VK.update({0x31 + n: 0x1E + n for n in range(9)})         # 1-9
VCFG_VK.update({0x61 + n: 0x59 + n for n in range(9)})         # numpad 1-9
VCFG_VK.update({0x70 + n: 0x3A + n for n in range(12)})        # F1-F12
VCFG_VK.update({0x7C + n: 0x68 + n for n in range(12)})        # F13-F24
# Keys the main table marks as extended: the flag does not change them.
VCFG_EXTENDED_IN_MAIN = {0x2C, 0x5B, 0x5C, 0x5D, 0x6F, 0x90, 0xA1, 0xA3, 0xA5}
# The second table, used when the flag is set.
VCFG_VK_EXTENDED = {0x0D: 0x58, 0x21: 0x4B, 0x22: 0x4E, 0x23: 0x4D, 0x24: 0x4A, 0x25: 0x50,
                    0x26: 0x52, 0x27: 0x4F, 0x28: 0x51, 0x2D: 0x49, 0x2E: 0x4C}


def vcfg_to_hid(vk, flag=0):
    """HID usage VCFG sends for a key stored in a .pfd (VK code and flag).
    Falls back to the plain Windows meaning where VCFG's table has nothing
    (VK_SHIFT, for example); raises if neither knows the key."""
    if flag in (0, 0xE0) or (flag in (1, 0xE1) and vk in VCFG_EXTENDED_IN_MAIN):
        hid = VCFG_VK.get(vk)
    else:
        hid = VCFG_VK_EXTENDED.get(vk)
    if hid is None:
        hid = VK_TO_HID.get(vk)
    if hid is None:
        raise ValueError(f'no HID code known for Windows key 0x{vk:02x} (flag {flag})')
    return hid


def hid_to_vcfg(code):
    """(VK code, flag) VCFG stores for a HID key, as its key recorder would."""
    for vk, hid in VCFG_VK_EXTENDED.items():
        if hid == code:
            return vk, 1
    # Where two VK codes give the same key (VK_END and VK_NUMPAD1 without the flag
    # are both Num 1), the higher one is the key's own code.
    vks = [vk for vk, hid in VCFG_VK.items() if hid == code]
    if not vks:
        raise ValueError(f'key {key_name(code)} has no Windows key code, so VCFG cannot store it')
    vk = max(vks)
    return vk, 1 if vk in VCFG_EXTENDED_IN_MAIN else 0


# --- Linux key codes (for capturing a key press in the window) ------------------

# evdev code (linux/input-event-codes.h) -> HID usage. Both name physical key
# positions, so a key captured on any layout maps to the key the mouse sends.
EVDEV_TO_HID = {
    1: 0x29, 12: 0x2D, 13: 0x2E, 14: 0x2A, 15: 0x2B, 26: 0x2F, 27: 0x30, 28: 0x28,
    29: 0xE0, 39: 0x33, 40: 0x34, 41: 0x35, 42: 0xE1, 43: 0x31, 51: 0x36, 52: 0x37,
    53: 0x38, 54: 0xE5, 55: 0x55, 56: 0xE2, 57: 0x2C, 58: 0x39, 69: 0x53, 70: 0x47,
    71: 0x5F, 72: 0x60, 73: 0x61, 74: 0x56, 75: 0x5C, 76: 0x5D, 77: 0x5E, 78: 0x57,
    79: 0x59, 80: 0x5A, 81: 0x5B, 82: 0x62, 83: 0x63, 86: 0x64, 87: 0x44, 88: 0x45,
    96: 0x58, 97: 0xE4, 98: 0x54, 99: 0x46, 100: 0xE6, 102: 0x4A, 103: 0x52,
    104: 0x4B, 105: 0x50, 106: 0x4F, 107: 0x4D, 108: 0x51, 109: 0x4E, 110: 0x49,
    111: 0x4C, 119: 0x48, 125: 0xE3, 126: 0xE7, 127: 0x65,
}
EVDEV_TO_HID.update({2 + n: 0x1E + n for n in range(10)})                 # 1-9, 0
EVDEV_TO_HID.update({59 + n: 0x3A + n for n in range(10)})                # F1-F10
EVDEV_TO_HID.update({183 + n: 0x68 + n for n in range(12)})               # F13-F24
EVDEV_TO_HID.update(zip(range(16, 26), (0x14, 0x1A, 0x08, 0x15, 0x17, 0x1C, 0x18, 0x0C, 0x12, 0x13)))
EVDEV_TO_HID.update(zip(range(30, 39), (0x04, 0x16, 0x07, 0x09, 0x0A, 0x0B, 0x0D, 0x0E, 0x0F)))
EVDEV_TO_HID.update(zip(range(44, 51), (0x1D, 0x1B, 0x06, 0x19, 0x05, 0x11, 0x10)))


def evdev_to_hid(code):
    return EVDEV_TO_HID.get(code)


# --- Windows scan codes (for capturing a key press in the window, and the auto-clicker) --

# PS/2 set-1 scan code -> HID usage, with 0x100 added for extended (E0) keys: the form
# Qt's nativeScanCode() and the low-level keyboard hook (scanCode + LLKHF_EXTENDED)
# give on Windows. The plain codes 1-0x58 are the evdev codes above, except that
# Windows reports Pause as 0x45 and Num Lock as extended 0x45.
SCANCODE_TO_HID = {c: h for c, h in EVDEV_TO_HID.items() if c <= 0x58 and c != 69}
SCANCODE_TO_HID.update({
    0x45: 0x48, 0x145: 0x53, 0x11C: 0x58, 0x11D: 0xE4, 0x135: 0x54, 0x137: 0x46, 0x138: 0xE6,
    0x147: 0x4A, 0x148: 0x52, 0x149: 0x4B, 0x14B: 0x50, 0x14D: 0x4F, 0x14F: 0x4D, 0x150: 0x51,
    0x151: 0x4E, 0x152: 0x49, 0x153: 0x4C, 0x15B: 0xE3, 0x15C: 0xE7, 0x15D: 0x65,
    0x54: 0x46,                                                     # Alt+PrintScreen
})
SCANCODE_TO_HID.update({0x64 + n: 0x68 + n for n in range(11)})    # F13-F23
SCANCODE_TO_HID[0x76] = 0x73                                        # F24


def scancode_to_hid(code):
    return SCANCODE_TO_HID.get(code)


def native_table():
    """Native key code -> HID usage on this system: evdev codes on Linux, scan codes
    on Windows. Both name physical key positions, like HID usages."""
    import sys
    return SCANCODE_TO_HID if sys.platform == 'win32' else EVDEV_TO_HID


def native_code(name):
    """Native key code (see native_table) of a key name, for reading keys the mouse sends."""
    hid = key_code(name)
    for code, h in native_table().items():
        if h == hid:
            return code
    raise ValueError(f'key {name!r} cannot be read from the mouse')
