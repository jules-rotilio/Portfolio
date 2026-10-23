"""Settings kept on the PC beside what the mouse stores, like VCFG's allsettings.pfd.

The mouse only holds DPI values on its 250 grid. For each profile this file keeps:

- the DPI asked for where it differs (1900 while the mouse uses 2000), which
  valkyrie-monitor makes exact by scaling the movement, as VMON's driver does;
- the Windows pointer settings (from .pfd files), kept for exports to VCFG;
- a copy of the DPI levels, selected level and polling rate valkyrie last read or
  wrote, so valkyrie-monitor can describe a profile without reading the mouse.

A value asked for only counts while the mouse still holds the value it was
written with: if another program changed that level, it is forgotten.
"""
import json
import os
import tempfile

from . import model, paths

CONFIG_DIR = paths.config_dir()
FORMAT = 'valkyrie-host-1'


def path():
    return os.path.join(CONFIG_DIR, 'host.json')


def empty():
    return {'format': FORMAT, 'active_profile': None, 'profiles': {}}


def load():
    """The file's contents; an empty record if it is missing or unreadable."""
    try:
        with open(path(), encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return empty()
    if not isinstance(data, dict) or data.get('format') != FORMAT or not isinstance(data.get('profiles'), dict):
        return empty()
    return data


def save(data):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=CONFIG_DIR, prefix='.host-', suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(data, f, indent=2)
            f.write('\n')
        os.replace(tmp, path())
    except BaseException:
        os.unlink(tmp)
        raise


def _level(lv):
    """What the mouse holds for a level (zeros when it is off), and the DPI asked for."""
    x, y = (lv.x, lv.y) if lv.enabled else (0, 0)
    rec = {'on': lv.enabled, 'x': x, 'y': y}
    if lv.wanted != (x, y) and all(lv.wanted):
        rec['want'] = list(lv.wanted)
    return rec


def record(profiles, active=None, keep_wanted=False):
    """Remember profiles {n: model.Profile} as the mouse now holds them.

    keep_wanted: for profiles that carry no DPI asked for (e.g. restored from a
    raw backup), keep what was known for levels whose mouse value is unchanged.
    """
    data = load()
    for n, p in profiles.items():
        old = data['profiles'].get(str(n + 1), {})
        levels = [_level(lv) for lv in p.dpi_levels]
        if keep_wanted:
            for rec, before in zip(levels, old.get('levels', [])):
                if 'want' not in rec and 'want' in before and (rec['x'], rec['y']) == (before['x'], before['y']):
                    rec['want'] = before['want']
        entry = {'polling': p.polling, 'selected': p.dpi_selected, 'levels': levels}
        if p.windows is not None:
            entry['windows'] = dict(vars(p.windows))
        elif 'windows' in old:
            entry['windows'] = old['windows']
        data['profiles'][str(n + 1)] = entry
    if active is not None:
        data['active_profile'] = active + 1
    save(data)


def windows_for(entry):
    try:
        return model.WindowsSettings(**entry['windows']).check()
    except (KeyError, TypeError, ValueError):
        return None


def attach(state, data=None):
    """Add what the PC knows to the profiles in a device.State read from the mouse."""
    data = data or load()
    for n, p in state.profiles.items():
        entry = data['profiles'].get(str(n + 1))
        if not entry:
            continue
        for lv, rec in zip(p.dpi_levels, entry.get('levels', [])):
            held = (lv.x, lv.y) if lv.enabled else (0, 0)
            want = rec.get('want')
            if not want or held != (rec.get('x'), rec.get('y')):
                continue
            try:
                wx, wy = (model.dpi_value(v) for v in want)
            except (TypeError, ValueError):
                continue
            if not lv.enabled or (lv.x == lv.y == model.snap_dpi(max(wx, wy))):
                lv.req_x, lv.req_y = wx, wy
        p.windows = windows_for(entry) or p.windows
    return state


def profile_view(entry):
    """A host entry as (polling, selected, [(on, (x, y), (want_x, want_y))]) for the monitor."""
    levels = []
    for rec in entry.get('levels', []):
        held = (rec.get('x', 0), rec.get('y', 0))
        levels.append((bool(rec.get('on')), held, tuple(rec.get('want') or held)))
    return entry.get('polling'), entry.get('selected', 0), levels
