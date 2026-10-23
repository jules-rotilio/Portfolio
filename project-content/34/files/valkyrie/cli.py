"""Command-line interface: valkyrie COMMAND [options]."""
import argparse
import json
import sys

from . import device, events, host, keys, model, ops, paths, pfd, store, utf8_stdio

ACTIONS_HELP = """\
Button actions (for --button B=ACTION):
  left, right, middle, back, forward   mouse buttons
  dpi-up, dpi-down, dpi-cycle          DPI switching
  rate-up, rate-down                   report rate switching
  profile-switch                       next profile
  disable                              do nothing
  key:NAME                             one key, e.g. key:Q, key:F5, key:Enter
  shortcut:MODS+NAME[+NAME]            e.g. shortcut:Ctrl+C, shortcut:Alt+Tab, shortcut:Ctrl+K+C
  media:NAME                           {media}
  fire:TARGET,TIMES,DELAY_MS           repeated clicks or key presses, e.g. fire:left,3,10 or fire:K,5,50
  macro:SLOT[,repeat]                  run macro SLOT; ',repeat' repeats while held

Key names follow the US layout (HID positions): {keys}
"""


def actions_text():
    media = ', '.join(sorted(keys.media_slug(u) for u in keys.CONSUMER))
    names = ', '.join(keys.HID_KEYS[c] for c in sorted(keys.HID_KEYS))
    return ACTIONS_HELP.format(media=media, keys=names)


def warn_conflicts():
    found = device.conflicting_programs()
    if found:
        print(f'warning: {device.conflict_text(found)} and also talks to the mouse; close it if results '
              'look wrong', file=sys.stderr)
    return found


def format_dpi(p):
    parts = []
    for i, lv in enumerate(p.dpi_levels):
        value = str(store.dpi_to_dict(lv))
        if lv.enabled and not lv.exact:
            value += f' (mouse {lv.x})'
        mark = ' (selected)' if i == p.dpi_selected else ''
        parts.append(f'{i + 1}: {value}{mark}')
    return '   '.join(parts)


def format_windows(w):
    return (f'pointer speed {w.pointer_speed}, acceleration {w.acceleration}, '
            f'scroll {w.scroll_lines} lines, double-click {w.double_click_ms} ms')


def format_profile(n, p, active, macros):
    light = p.light
    lines = [
        f"Profile {n + 1}{' (active)' if n == active else ''}",
        f'  Polling rate   {p.polling_hz} Hz' if p.polling_hz else f'  Polling rate   unknown (raw {p.polling})',
        f'  DPI            {format_dpi(p)}',
        '  Light          #{:02X}{:02X}{:02X}, brightness {}, breathing {}'.format(
            *light.rgb, model.BRIGHTNESS.get(light.brightness, light.brightness),
            model.BREATHING.get(light.breathing, light.breathing)),
        '  Buttons',
    ]
    lines += [f'    {b + 1:2d}  {model.describe_action(a)}' for b, a in enumerate(p.buttons)]
    if p.windows is not None:
        where = 'applied by the window and valkyrie-monitor' if paths.WINDOWS else 'applied by VCFG on Windows'
        lines.append(f'  Windows only   {format_windows(p.windows)} ({where})')
    used = p.macro_slots()
    if used:
        lines.append('  Macros')
        for slot in used:
            m = macros.get(slot)
            steps = ', '.join(model.step_to_str(s) for s in m.steps) if m else '(not read)'
            loops = f'runs {m.loops}x' if m else ''
            lines.append(f'    {slot + 1:2d}  {loops}: {steps}')
    return '\n'.join(lines)


def cmd_show(args):
    warn_conflicts()
    mouse = device.open_mouse(args.device)
    state = ops.read_state(mouse)
    if args.all:
        shown = range(device.PROFILES)
    elif args.profile:
        shown = [args.profile - 1]
    else:
        shown = [state.active]
    readable = [n for n in shown if n in state.profiles]
    if args.json:
        data = store.export_dict(state, readable)
        if state.errors:
            data['errors'] = {str(k + 1) if isinstance(k, int) else k: v for k, v in state.errors.items()}
        print(json.dumps(data, indent=2))
        return 0
    print(f'Active profile: {state.active + 1}\n')
    if any(not lv.exact for p in state.profiles.values() for lv in p.dpi_levels if lv.enabled):
        if paths.WINDOWS:
            print('DPI values off the mouse\'s steps of 250 are rounded to the nearest step by the mouse '
                  '(exact DPI needs valkyrie-monitor, Linux only for now).\n')
        else:
            print('DPI values off the mouse\'s steps of 250 are exact while valkyrie-monitor runs '
                  'with exact_dpi = true.\n')
    parts = []
    for n in shown:
        if n in state.profiles:
            parts.append(format_profile(n, state.profiles[n], state.active, state.macros))
        else:
            parts.append(f'Profile {n + 1}\n  could not decode: {state.errors[n]}')
    print('\n\n'.join(parts))
    for key, why in state.errors.items():
        if not isinstance(key, int):
            print(f'warning: {key}: {why}', file=sys.stderr)
    return 0


def cmd_dump_memory(args):
    warn_conflicts()
    mouse = device.open_mouse(args.device)
    data = mouse.dump(args.start, args.length)
    with open(args.file, 'wb') as f:
        f.write(data)
    print(f'saved 0x{args.start:04x}-0x{args.start + len(data) - 1:04x} ({len(data)} bytes) to {args.file}')
    # Summary: which 16-byte rows are all 0xff (probably unused).
    rows = [data[i:i + 16] for i in range(0, len(data), 16)]
    start = None
    for i, row in enumerate(rows + [None]):
        blank = row is not None and row == b'\xff' * len(row)
        if blank and start is None:
            start = i
        if not blank and start is not None:
            print(f'  all 0xff: 0x{args.start + start * 16:04x}-0x{args.start + i * 16 - 1:04x}')
            start = None
    return 0


def cmd_actions(args):
    print(actions_text(), end='')
    return 0


# --- Writing -------------------------------------------------------------------

def open_for_writing(args):
    found = device.conflicting_programs()
    if found and not args.force:
        raise device.DeviceError(f'{device.conflict_text(found)} and also talks to the mouse. '
                                 'Close it first (or use --force).')
    return device.open_mouse(args.device)


decoded_profile = ops.decoded_profile
macros_for = ops.macros_for
plan_changes = ops.plan_changes


def write_profiles(args, mouse, state, changes):
    """changes: {n: (profile, macros)}. Dry run, or backup + write + verify."""
    for n, (profile, _) in sorted(changes.items()):
        off = [lv for lv in profile.dpi_levels if lv.enabled and not lv.exact]
        if off:
            print(f'  note: profile {n + 1}: DPI ' + ', '.join(str(store.dpi_to_dict(lv)) for lv in off) +
                  ' are not on the mouse\'s steps of 250; it uses ' + ', '.join(str(lv.x) for lv in off) +
                  ('' if paths.WINDOWS else ' (exact while valkyrie-monitor runs with exact_dpi)'))
    if args.dry_run:
        fake = device.fake_from_state(state)
        sim = device.Mouse(fake, pace=False)
        for n, (profile, macros) in sorted(changes.items()):
            if ops.unchanged_on_mouse(state, n, profile, macros):
                print(f'  profile {n + 1}: the mouse already holds it; only the PC side would change')
                continue
            sim.apply_profile(n, profile, macros)
        print('dry run, nothing sent. Frames that would be sent:')
        for kind, frame in fake.frames:
            print('  ' + device.describe_frame(kind, frame))
        return 0
    ops.write_changes(mouse, state, changes)
    return 0


def parse_dpi_spec(spec):
    """'3=1600' or '3=1600x800' -> (level index, x, y) asked for"""
    level, sep, value = spec.partition('=')
    if not sep:
        raise ValueError(f'use LEVEL=DPI, e.g. --dpi 3=1600 (got {spec!r})')
    index = model._int(level, 1, model.DPI_LEVELS, 'DPI level') - 1
    x, _, y = value.lower().partition('x')
    x = model.dpi_value(x)
    return index, x, model.dpi_value(y) if y else x


def cmd_set(args):
    mouse = open_for_writing(args)
    state = ops.read_state(mouse)
    n = args.profile - 1 if args.profile else state.active
    p = decoded_profile(state, n)
    before = store.profile_to_dict(p)

    if args.polling:
        p.polling = model.polling_value(args.polling)
    for spec in args.dpi:
        index, x, y = parse_dpi_spec(spec)
        lv = p.dpi_levels[index]
        if (x, y) != lv.wanted or not lv.enabled:
            p.dpi_levels[index] = lv = model.DpiLevel(True, 0, 0, lv.extra)
            lv.set(x, y)
    for level in args.dpi_on:
        lv = p.dpi_levels[level - 1]
        if not all(lv.wanted):
            raise ValueError(f'DPI level {level} has no value yet; use --dpi {level}=VALUE')
        if not lv.enabled:
            lv.enabled = True
            lv.set(*lv.wanted)
    if args.dpi_default:
        if not p.dpi_levels[args.dpi_default - 1].enabled:
            raise ValueError(f'DPI level {args.dpi_default} is off')
        p.dpi_selected = args.dpi_default - 1
    for level in args.dpi_off:
        if level - 1 == p.dpi_selected:
            raise ValueError(f'DPI level {level} is the selected level; pick another with --dpi-default first')
        p.dpi_levels[level - 1].enabled = False
    if not any(lv.enabled for lv in p.dpi_levels):
        raise ValueError('at least one DPI level must stay on')

    light = p.light
    if args.color:
        light = model.Light(model.light_color(args.color), light.brightness, light.breathing, light.extra)
    if args.brightness:
        light.brightness = model.named_value(model.BRIGHTNESS, args.brightness, 'brightness')
    if args.breathing:
        light.breathing = model.named_value(model.BREATHING, args.breathing, 'breathing')
    p.light = light

    for spec in args.button:
        button, sep, text = spec.partition('=')
        if not sep:
            raise ValueError(f'use BUTTON=ACTION, e.g. --button 10=key:Q (got {spec!r})')
        b = model._int(button, 1, model.BUTTONS, 'button')
        if b == 14:
            raise ValueError('button 14 is the profile switch under the mouse; VCFG never changes it')
        action = model.parse_action(text)
        if action.kind == 'macro' and action.code >= device.MACRO_SLOTS:
            raise ValueError(f'macro slots are 1-{device.MACRO_SLOTS}')
        p.buttons[b - 1] = action

    after = store.profile_to_dict(p)
    if after == before:
        raise ValueError('nothing to change (see valkyrie set --help)')
    print_changes(n, before, after)
    return write_profiles(args, mouse, state, {n: (p, macros_for(p, state))})


def print_changes(n, before, after):
    if before == after:
        print(f'  profile {n + 1}: already matches (rewritten unchanged)')
        return

    def walk(a, b, path):
        if isinstance(a, dict):
            for key in a:
                walk(a[key], b[key], path + [key])
        elif isinstance(a, list):
            for i, (x, y) in enumerate(zip(a, b)):
                walk(x, y, path + [str(i + 1)])
        elif a != b:
            print(f'  profile {n + 1} {".".join(path)}: {a} -> {b}')
    walk(before, after, [])


def cmd_profile(args):
    mouse = open_for_writing(args)
    n = args.number - 1
    if args.dry_run:
        fake = device.FakeMouse()
        device.Mouse(fake, pace=False).switch_profile(n)
        print('dry run, nothing sent. Frames that would be sent:')
        for kind, frame in fake.frames:
            print('  ' + device.describe_frame(kind, frame))
        return 0
    mouse.switch_profile(n)
    with mouse.session():
        active = mouse.read_active()
    if active != n:
        raise device.DeviceError(f'the mouse reports profile {active + 1} as active')
    host.record({}, active)
    print(f'profile {n + 1} is now active')
    return 0


def cmd_macro(args):
    if not 1 <= args.slot <= device.MACRO_SLOTS:
        raise ValueError(f'macro slots are 1-{device.MACRO_SLOTS}')
    slot = args.slot - 1
    macro = model.Macro(model.parse_steps(args.steps), model._int(str(args.loops), 1, 255, 'loops'))
    model.encode_macro(macro)                       # checks the size limit early
    mouse = open_for_writing(args)
    state = ops.read_state(mouse)
    target = args.profile - 1 if args.profile else state.active
    profiles = {}
    if args.button:
        if args.button == 14:
            raise ValueError('button 14 is the profile switch under the mouse; VCFG never changes it')
        p = decoded_profile(state, target)
        p.buttons[args.button - 1] = model.Action('macro', code=slot, repeat=args.repeat)
        profiles[target] = p
    elif not any(slot in p.macro_slots() for p in state.profiles.values()):
        raise ValueError(f'no button uses macro {args.slot}; add --button B to assign it '
                         '(the mouse saves macros together with a profile)')
    print(f'  macro {args.slot} = {", ".join(model.step_to_str(s) for s in macro.steps)}'
          + (f' (runs {macro.loops}x)' if macro.loops > 1 else ''))
    if args.button:
        print(f'  profile {target + 1} button {args.button} -> macro:{args.slot}' + (',repeat' if args.repeat else ''))
    return write_profiles(args, mouse, state, plan_changes(state, profiles, {slot: macro}))


def target_profiles(state, numbers):
    for n in numbers:
        decoded_profile(state, n)           # raises if it cannot be decoded
    return numbers


def cmd_export(args):
    warn_conflicts()
    state = ops.read_state(device.open_mouse(args.device))
    numbers = [args.profile - 1] if args.profile else sorted(state.profiles)
    data = store.export_dict(state, target_profiles(state, numbers))
    with open(args.file, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(data, f, indent=2)
        f.write('\n')
    print(f'saved profile(s) {", ".join(str(n + 1) for n in numbers)} to {args.file}')
    return 0


def cmd_apply(args):
    with open(args.file, encoding='utf-8') as f:
        data = json.load(f)
    if data.get('format') != store.PROFILES_FORMAT:
        raise ValueError(f'{args.file} was not written by "valkyrie export"')
    chosen = {int(k) - 1: v for k, v in data['profiles'].items()}
    if args.profile:
        if args.profile - 1 not in chosen:
            raise ValueError(f'{args.file} has no profile {args.profile}')
        chosen = {args.profile - 1: chosen[args.profile - 1]}
    if args.to:
        if len(chosen) != 1:
            raise ValueError('--to needs --profile when the file holds several profiles')
        chosen = {args.to - 1: next(iter(chosen.values()))}
    new_macros = store.macros_from_dict(data.get('macros', {}))
    mouse = open_for_writing(args)
    state = ops.read_state(mouse)
    profiles = {}
    for n, d in sorted(chosen.items()):
        base = decoded_profile(state, n)
        profiles[n] = store.profile_from_dict(d, base)
        print_changes(n, store.profile_to_dict(base), store.profile_to_dict(profiles[n]))
    used = {s for p in profiles.values() for s in p.macro_slots()}
    return write_profiles(args, mouse, state,
                          plan_changes(state, profiles, {s: m for s, m in new_macros.items() if s in used}))


def cmd_import_pfd(args):
    profile, macros = pfd.to_profile(args.file)
    for slot in macros:
        if slot >= device.MACRO_SLOTS:
            raise ValueError(f'the file uses macro {slot + 1}; this mouse has slots 1-{device.MACRO_SLOTS}')
    mouse = open_for_writing(args)
    state = ops.read_state(mouse)
    n = args.profile - 1 if args.profile else state.active
    base = decoded_profile(state, n)
    profile.dpi_count = base.dpi_count
    for new, old in zip(profile.dpi_levels, base.dpi_levels):
        new.extra = old.extra
    print_changes(n, store.profile_to_dict(base), store.profile_to_dict(profile))
    return write_profiles(args, mouse, state, plan_changes(state, {n: profile}, macros))


def cmd_export_pfd(args):
    warn_conflicts()
    state = ops.read_state(device.open_mouse(args.device))
    n = args.profile - 1 if args.profile else state.active
    profile = decoded_profile(state, n)
    data = pfd.from_profile(profile, macros_for(profile, state))
    with open(args.file, 'wb') as f:
        f.write(data)
    print(f'saved profile {n + 1} to {args.file} (open it in VCFG with LOAD FILE)')
    return 0


def cmd_factory_reset(args):
    mouse = open_for_writing(args)
    state = ops.read_state(mouse)
    numbers = [args.profile - 1] if args.profile else list(range(device.PROFILES))
    profiles = {}
    for n in numbers:
        base = decoded_profile(state, n)
        profiles[n] = ops.factory_profile(n, base)
        print_changes(n, store.profile_to_dict(base), store.profile_to_dict(profiles[n]))
    return write_profiles(args, mouse, state, plan_changes(state, profiles))


def cmd_monitor(args):
    """Print what the mouse reports when its own buttons change a setting."""
    listener = events.Listener(args.device)
    print(f'listening on {listener.path}; press the profile, DPI or report-rate buttons '
          '(Ctrl+C to stop)', flush=True)
    try:
        while True:
            # A short timeout, so Ctrl+C is seen promptly on Windows too.
            for event in listener.read(timeout=0.5):
                print(f'{event.raw.hex(" ")}  {event.describe()}', flush=True)
    except KeyboardInterrupt:
        return 0
    finally:
        listener.close()


def cmd_backup(args):
    warn_conflicts()
    state = device.open_mouse(args.device).read_state()
    print(f'backup saved: {store.save_backup(state, args.file)}')
    return 0


def cmd_restore(args):
    active, plan = ops.restore_plan(args.file, args.profile - 1 if args.profile else None)
    mouse = open_for_writing(args)
    if args.dry_run:
        fake = device.FakeMouse()
        sim = device.Mouse(fake, pace=False)
        for n, (blocks, data) in plan.items():
            sim.apply_blocks(n, blocks, data, active=active)
        print('dry run, nothing sent. Frames that would be sent:')
        for kind, frame in fake.frames:
            print('  ' + device.describe_frame(kind, frame))
        return 0
    ops.write_restore(mouse, active, plan)
    return 0


def number(text):
    return int(text, 0)


def build_parser():
    ap = argparse.ArgumentParser(prog='valkyrie', description='Configure the Konix Drakkar Valkyrie mouse.')
    ap.add_argument('--device', help=('HID device path' if paths.WINDOWS else 'hidraw node') +
                    ' (default: found automatically)')
    sub = ap.add_subparsers(dest='command', required=True)

    p = sub.add_parser('show', help='show the settings stored in the mouse')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='profile 1-5 (default: active)')
    group.add_argument('--all', action='store_true', help='show all 5 profiles')
    p.add_argument('--json', action='store_true', help='print JSON')
    p.set_defaults(func=cmd_show)

    p = sub.add_parser('dump-memory', help='save a raw copy of the mouse memory (read-only)')
    p.add_argument('file')
    p.add_argument('--start', type=number, default=0)
    p.add_argument('--length', type=number, default=0x1000)
    p.set_defaults(func=cmd_dump_memory)

    p = sub.add_parser('actions', help='list the button actions and key names')
    p.set_defaults(func=cmd_actions)

    p = sub.add_parser('monitor', help='show what the mouse reports when its buttons change a setting')
    p.set_defaults(func=cmd_monitor)

    def writer(name, **kw):
        p = sub.add_parser(name, **kw)
        p.add_argument('--dry-run', action='store_true', help='print the frames instead of sending them')
        p.add_argument('--force', action='store_true', help='write even if VCFG/VMON is running')
        return p

    levels = range(1, model.DPI_LEVELS + 1)
    p = writer('set', help='change settings of a profile',
               epilog='Example: valkyrie set --dpi 3=1600 --color "#00aaff" --button 10=key:Q')
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='profile 1-5 (default: active)')
    p.add_argument('--polling', type=int, choices=(125, 250, 500, 1000), metavar='HZ', help='125, 250, 500 or 1000')
    p.add_argument('--dpi', action='append', default=[], metavar='L=DPI',
                   help='set DPI level L (1-5) to 250-4000 in steps of 50, e.g. 3=1600 or 3=1600x800; '
                        'the mouse uses the nearest step of 250 for both axes (exact with valkyrie-monitor)')
    p.add_argument('--dpi-on', action='append', default=[], type=int, choices=levels, metavar='L')
    p.add_argument('--dpi-off', action='append', default=[], type=int, choices=levels, metavar='L')
    p.add_argument('--dpi-default', type=int, choices=levels, metavar='L', help='selected DPI level')
    p.add_argument('--color', metavar='#RRGGBB')
    p.add_argument('--brightness', metavar='LEVEL', help=', '.join(model.BRIGHTNESS.values()))
    p.add_argument('--breathing', metavar='SPEED', help=', '.join(model.BREATHING.values()))
    p.add_argument('--button', action='append', default=[], metavar='B=ACTION',
                   help='e.g. 10=key:Q (see valkyrie actions)')
    p.set_defaults(func=cmd_set)

    p = writer('profile', help='switch the active profile')
    p.add_argument('number', type=int, choices=range(1, 6), metavar='N')
    p.set_defaults(func=cmd_profile)

    p = writer('macro', help='define a macro',
               epilog='Example: valkyrie macro 1 "A down, wait 50, A up, mouse:left down, mouse:left up" --button 9')
    p.add_argument('slot', type=int, metavar='SLOT', help=f'1-{device.MACRO_SLOTS}')
    p.add_argument('steps', help='"KEY down", "KEY up", "mouse:left down", "wait MS", separated by commas')
    p.add_argument('--loops', type=int, default=1, help='1-255')
    p.add_argument('--button', type=int, choices=range(1, 14), metavar='B', help='assign it to button B')
    p.add_argument('--repeat', action='store_true', help='with --button: repeat while held')
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='profile for --button (default: active)')
    p.set_defaults(func=cmd_macro)

    p = sub.add_parser('export', help='save profiles as an editable JSON file')
    p.add_argument('file')
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='only profile N (default: all)')
    p.set_defaults(func=cmd_export)

    p = writer('apply', help='write profiles from a JSON file made by "export"')
    p.add_argument('file')
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='only profile N of the file')
    p.add_argument('--to', type=int, choices=range(1, 6), metavar='M', help='write it into profile M instead')
    p.set_defaults(func=cmd_apply)

    p = writer('import-pfd', help='write a VCFG .pfd profile file into the mouse')
    p.add_argument('file')
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='target profile (default: active)')
    p.set_defaults(func=cmd_import_pfd)

    p = sub.add_parser('export-pfd', help='save a profile as a VCFG .pfd file')
    p.add_argument('file')
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='profile 1-5 (default: active)')
    p.set_defaults(func=cmd_export_pfd)

    p = writer('factory-reset', help="write VCFG's factory settings (all profiles, or --profile N)")
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='only profile N')
    p.set_defaults(func=cmd_factory_reset)

    p = sub.add_parser('backup', help='save a raw copy of all profiles and macros')
    p.add_argument('file', nargs='?', help=f'default: {store.BACKUP_DIR}/<time>.json')
    p.set_defaults(func=cmd_backup)

    p = writer('restore', help='write a backup back to the mouse')
    p.add_argument('file')
    p.add_argument('--profile', type=int, choices=range(1, 6), metavar='N', help='restore only profile N')
    p.set_defaults(func=cmd_restore)
    return ap


def main(argv=None):
    utf8_stdio()
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (device.DeviceError, ValueError, OSError) as e:
        print(f'error: {e}', file=sys.stderr)
        return 1
