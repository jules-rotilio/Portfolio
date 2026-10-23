"""Readable (JSON-friendly) form of profiles and macros, and raw backups."""
import copy
import datetime
import json
import os

from . import model, paths

BACKUP_DIR = paths.backup_dir()
BACKUP_FORMAT = 'valkyrie-backup-1'


def save_backup(state, path=None):
    """Save the raw bytes `state` read from the mouse; returns the file path."""
    if path is None:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        path = os.path.join(BACKUP_DIR, f'{stamp}.json')
    data = {
        'format': BACKUP_FORMAT,
        'time': datetime.datetime.now().isoformat(timespec='seconds'),
        'active_profile': state.active + 1,
        'profiles': {str(n + 1): {name: block.hex() for name, block in blocks.items()}
                     for n, blocks in sorted(state.blocks.items())},
        'macros': {str(slot + 1): model.encode_macro(m).hex() for slot, m in sorted(state.macros.items())},
    }
    with open(path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2)
    return path


def load_backup(path):
    """-> (active profile 0-4, {n: blocks}, {macro slot: bytes})"""
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    if data.get('format') != BACKUP_FORMAT:
        raise ValueError(f'{path} is not a valkyrie backup')
    profiles = {int(n) - 1: {name: bytes.fromhex(h) for name, h in blocks.items()}
                for n, blocks in data['profiles'].items()}
    macros = {int(slot) - 1: bytes.fromhex(h) for slot, h in data['macros'].items()}
    return data['active_profile'] - 1, profiles, macros


def _named(table, value):
    return table.get(value, value)


def dpi_to_dict(level):
    """The DPI asked for: 1600, '1600x800', or 'off'."""
    if not level.enabled:
        return 'off'
    x, y = level.wanted
    return x if x == y else f'{x}x{y}'


def windows_to_dict(w):
    return dict(vars(w))


def windows_from_dict(d, base=None):
    w = copy.deepcopy(base) if base is not None else model.WindowsSettings()
    for key, value in d.items():
        if key not in model.WindowsSettings.RANGES:
            raise ValueError(f'unknown Windows setting {key!r}')
        setattr(w, key, value)
    return w.check()


def profile_to_dict(p):
    return {
        'polling_hz': p.polling_hz if p.polling_hz else f'raw {p.polling}',
        'dpi': {
            'selected': p.dpi_selected + 1,
            'levels': [dpi_to_dict(lv) for lv in p.dpi_levels],
        },
        'light': {
            'color': '#{:02X}{:02X}{:02X}'.format(*p.light.rgb),
            'brightness': _named(model.BRIGHTNESS, p.light.brightness),
            'breathing': _named(model.BREATHING, p.light.breathing),
        },
        'buttons': {str(n + 1): model.action_to_str(a) for n, a in enumerate(p.buttons)},
        **({'windows': windows_to_dict(p.windows)} if p.windows is not None else {}),
    }


def macro_to_dict(m):
    return {
        'loops': m.loops,
        'steps': ', '.join(model.step_to_str(s) for s in m.steps),
    }


PROFILES_FORMAT = 'valkyrie-profiles-1'


def export_dict(state, numbers):
    """Readable form of the given profiles (0-based) and the macros they use."""
    used = sorted({s for n in numbers for s in state.profiles[n].macro_slots()})
    return {
        'format': PROFILES_FORMAT,
        'active_profile': state.active + 1,
        'profiles': {str(n + 1): profile_to_dict(state.profiles[n]) for n in numbers},
        'macros': {str(s + 1): macro_to_dict(state.macros[s]) for s in used if s in state.macros},
    }


def _dpi_from(value, what):
    """1600 or '1600x800' -> (x, y) asked for."""
    if isinstance(value, int):
        x = y = model.dpi_value(value)
    else:
        x, _, y = str(value).lower().partition('x')
        x, y = model.dpi_value(x), model.dpi_value(y or x)
    return x, y


def profile_from_dict(d, base):
    """Apply the settings in d (as written by profile_to_dict) on top of profile `base`."""
    p = copy.deepcopy(base)
    if 'polling_hz' in d:
        p.polling = model.polling_value(d['polling_hz'])
    dpi = d.get('dpi', {})
    if 'levels' in dpi:
        if len(dpi['levels']) != model.DPI_LEVELS:
            raise ValueError(f'dpi.levels must list {model.DPI_LEVELS} values')
        for i, value in enumerate(dpi['levels']):
            if value == 'off':
                p.dpi_levels[i].enabled = False
            else:
                x, y = _dpi_from(value, f'DPI level {i + 1}')
                level = p.dpi_levels[i]
                if (x, y) != level.wanted or not level.enabled:     # unchanged levels keep their bytes
                    level = model.DpiLevel(True, 0, 0, level.extra)
                    level.set(x, y)
                p.dpi_levels[i] = level
    if 'selected' in dpi:
        p.dpi_selected = model._int(str(dpi['selected']), 1, model.DPI_LEVELS, 'dpi.selected') - 1
    if not p.dpi_levels[p.dpi_selected].enabled:
        raise ValueError(f'the selected DPI level {p.dpi_selected + 1} is off')
    light = d.get('light', {})
    if 'color' in light:
        p.light.rgb = model.light_color(light['color'])
    if 'brightness' in light:
        p.light.brightness = model.named_value(model.BRIGHTNESS, str(light['brightness']), 'brightness')
    if 'breathing' in light:
        p.light.breathing = model.named_value(model.BREATHING, str(light['breathing']), 'breathing')
    if 'windows' in d:
        p.windows = windows_from_dict(d['windows'], p.windows)
    for key, text in d.get('buttons', {}).items():
        b = model._int(str(key), 1, model.BUTTONS, 'button')
        current = base.buttons[b - 1]
        if text.startswith('unknown:'):
            if model.action_to_str(current) != text:
                raise ValueError(f'button {b}: unknown actions can only be kept as they are')
            continue
        action = model.parse_action(text)
        if b == 14 and action != current:
            raise ValueError('button 14 is the profile switch under the mouse; VCFG never changes it')
        p.buttons[b - 1] = action
    return p


def macros_from_dict(d):
    out = {}
    for key, value in d.items():
        slot = model._int(str(key), 1, 255, 'macro slot') - 1
        loops = model._int(str(value.get('loops', 1)), 1, model.MACRO_MAX_LOOPS, 'loops')
        out[slot] = model.Macro(model.parse_steps(value['steps']), loops)
    return out
