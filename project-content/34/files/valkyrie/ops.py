"""Write operations shared by the command line and the window.

Every write goes the same way: plan which profiles must be rewritten, save a
backup of what the mouse holds, write each profile like VCFG's Apply button,
then read it back and compare. What only the PC keeps (DPI asked for off the
250 grid, Windows settings) is saved in host.json afterwards.
"""
import copy
import json
import os

from . import device, host, model, store

FACTORY = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'factory.json')


def read_state(mouse):
    """Read the mouse and add what the PC knows about its profiles."""
    return host.attach(mouse.read_state())


def decoded_profile(state, n):
    if n not in state.profiles:
        raise device.DeviceError(f'profile {n + 1} could not be decoded ({state.errors[n]}); '
                                 'not writing to it')
    return copy.deepcopy(state.profiles[n])


def macros_for(profile, state, new=None):
    """Macro contents a profile needs when written: from the mouse, or new ones."""
    new = new or {}
    out = {}
    for slot in profile.macro_slots():
        if slot in new:
            out[slot] = new[slot]
        elif slot in state.macros:
            out[slot] = state.macros[slot]
        else:
            raise ValueError(f'macro {slot + 1} has no content on the mouse; give it some steps first')
    return out


def plan_changes(state, profiles, new_macros=None, note=print):
    """{n: profile} to write, plus every other profile using a macro whose content
    changes (each profile stores the macro's length) -> {n: (profile, macros)}."""
    new_macros = new_macros or {}
    changes = dict(profiles)
    for slot, macro in new_macros.items():
        old = state.macros.get(slot)
        if old is not None and model.encode_macro(old) == model.encode_macro(macro):
            continue
        for n, p in state.profiles.items():
            if n not in changes and slot in p.macro_slots():
                note(f'  note: profile {n + 1} also uses macro {slot + 1}; it is rewritten too')
                changes[n] = copy.deepcopy(p)
    return {n: (p, macros_for(p, state, new_macros)) for n, p in changes.items()}


def unchanged_on_mouse(state, n, profile, macros):
    """True if writing would send the mouse exactly what it holds."""
    if n not in state.blocks:
        return False
    data = {slot: model.encode_macro(m) for slot, m in macros.items()}
    if any(slot not in state.macros or model.encode_macro(state.macros[slot]) != b for slot, b in data.items()):
        return False
    return model.encode_profile(profile, {slot: len(b) for slot, b in data.items()}) == state.blocks[n]


def write_changes(mouse, state, changes, log=print):
    """changes: {n: (profile, macros)}. Backup, write, verify; returns the backup path.

    If a profile's DPI level is the one it had when the mouse was read, the level
    picked on the mouse since then (with its DPI button) is kept, like VCFG does.
    """
    path = store.save_backup(state)
    log(f'backup saved: {path}')
    written = {}
    try:
        for n, (profile, macros) in sorted(changes.items()):
            if unchanged_on_mouse(state, n, profile, macros):
                written[n] = profile
                log(f'profile {n + 1}: the mouse already holds it (settings kept on the PC updated)')
                continue
            keep = n in state.profiles and profile.dpi_selected == state.profiles[n].dpi_selected
            blocks, data = mouse.apply_profile(n, profile, macros, keep_stage=keep)
            bad = mouse.verify(n, blocks, data)
            if bad:
                raise device.DeviceError(f'profile {n + 1}: read-back differs ({", ".join(bad)}). '
                                         f'To undo: valkyrie restore {path}')
            done = copy.deepcopy(profile)
            done.dpi_selected = blocks['dpi'][1]
            written[n] = done
            if done.dpi_selected != profile.dpi_selected:
                log(f'profile {n + 1}: written and verified (DPI level {done.dpi_selected + 1}, '
                    'picked on the mouse, kept)')
            else:
                log(f'profile {n + 1}: written and verified')
    finally:
        if written:
            host.record(written)
    return path


def factory_profiles():
    """VCFG's factory settings (TDM_uiProfile*RestoreToDefault in VCFG.exe):
    {n: readable profile dict, as store.profile_to_dict writes it}."""
    with open(FACTORY, encoding='utf-8') as f:
        data = json.load(f)
    return {int(k) - 1: v for k, v in data['profiles'].items()}


def factory_profile(n, base):
    """Profile n as it leaves the factory, built on `base` (the profile read from
    the mouse, for the bytes valkyrie keeps as they are)."""
    return store.profile_from_dict(factory_profiles()[n], base)


def restore_plan(path, profile=None):
    """-> (active profile, {n: (blocks, {slot: bytes})}) from a backup file."""
    active, profiles, macros = store.load_backup(path)
    if profile is not None:
        if profile not in profiles:
            raise ValueError(f'the backup has no profile {profile + 1}')
        profiles = {profile: profiles[profile]}
    plan = {}
    for n, blocks in sorted(profiles.items()):
        slots = {a.code for a in model.decode_buttons(blocks['buttons']) if a.kind == 'macro'}
        missing = slots - set(macros)
        if missing:
            raise ValueError(f'backup lacks macro(s) {sorted(s + 1 for s in missing)} used by profile {n + 1}')
        plan[n] = (blocks, {s: macros[s] for s in slots})
    return active, plan


def write_restore(mouse, active, plan, log=print):
    path = store.save_backup(mouse.read_state())
    log(f'backup of the current state saved first: {path}')
    for n, (blocks, data) in plan.items():
        mouse.apply_blocks(n, blocks, data, active=active)
        bad = mouse.verify(n, blocks, data)
        if bad:
            raise device.DeviceError(f'profile {n + 1}: read-back differs ({", ".join(bad)})')
        log(f'profile {n + 1}: restored and verified')
        try:
            host.record({n: model.decode_profile(**blocks)}, active, keep_wanted=True)
        except ValueError:
            pass
