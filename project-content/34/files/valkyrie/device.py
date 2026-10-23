"""Talking to the Drakkar Valkyrie.

The mouse is configured with HID feature reports on its vendor interface.
Every command is the same frame: report id, command, 16-bit address, 16-bit
length, fa fa, payload, zero padding up to the report's full size. This
module reproduces VCFG.exe's frames and command sequences byte for byte, and
refuses any write outside the memory ranges VCFG itself writes.

The frames go through the system's transport: hidraw on Linux (hid_linux.py),
the HID class driver on Windows (hid_windows.py).
"""
import contextlib
import time

from . import model, paths

VENDOR_ID, PRODUCT_ID = 0x04D9, 0xFC06
REPORT_SIZES = {2: 16, 3: 64, 4: 1024, 5: 2048, 6: 4096}

READ, WRITE, COMMIT, PREVIEW, SESSION = 0x03, 0x02, 0x01, 0x04, 0x06

# Memory map
ACTIVE_PROFILE = 0x43
POLLING = 0x48                  # + profile
PROFILES = 5
MACRO_BASE = 0x500
# VCFG's encoder has 30 macro slots (Enc_Macros: 0x500 + slot * 200, up to 0x1c6f);
# its limit of 5 is only a rule of its window, counting buttons that use a macro.
MACRO_SLOTS = 30


def dpi_addr(n):
    return n * 0x100 + 0x4F


def buttons_addr(n):
    return n * 0x100 + 0x90


def light_addr(n):
    return n * 0x100 + 0xF1


def macro_addr(slot):
    return MACRO_BASE + slot * model.MACRO_SIZE


def writable_ranges():
    yield ACTIVE_PROFILE, 1
    for n in range(PROFILES):
        yield POLLING + n, 1
        yield dpi_addr(n), 42
        yield buttons_addr(n), 57
        yield light_addr(n), 6
    for slot in range(MACRO_SLOTS):
        yield macro_addr(slot), model.MACRO_SIZE


def check_writable(addr, length):
    for start, size in writable_ranges():
        if start <= addr and addr + length <= start + size:
            return
    raise ValueError(f'refusing to write {length} bytes at 0x{addr:04x}: '
                     'outside the ranges VCFG writes')


class DeviceError(Exception):
    pass


# --- Frames ------------------------------------------------------------------

def report_for(length):
    """Smallest report whose payload (size - 8) holds `length` bytes, like VCFG."""
    for rid, size in REPORT_SIZES.items():
        if size - 8 >= length:
            return rid
    raise ValueError(f'{length} bytes do not fit in one report')


def data_frame(cmd, addr, length, payload=b''):
    rid = report_for(length if cmd == WRITE else 0)
    frame = bytes([rid, cmd, addr & 0xFF, addr >> 8, length & 0xFF, length >> 8, 0xFA, 0xFA])
    frame += payload
    return frame + bytes(REPORT_SIZES[rid] - len(frame))


def command_frame(cmd, *args):
    frame = bytes([2, cmd, *args])
    return frame + bytes(REPORT_SIZES[2] - len(frame))


# --- Transports --------------------------------------------------------------

def transport():
    """The system's transport module: Device (feature reports), Listener (input
    reports), find_device() and conflicting_programs()."""
    if paths.WINDOWS:
        from . import hid_windows
        return hid_windows
    from . import hid_linux
    return hid_linux


def find_device():
    """The mouse's vendor interface: a hidraw node on Linux, a HID path on Windows."""
    return transport().find_device()


class FakeMouse:
    """In-memory stand-in for the mouse: answers reads from a memory image and
    records every frame. Used for --dry-run and for tests."""

    SIZE = 0x2000                   # the real mouse answers reads up to 0x1fff at least

    def __init__(self, memory=None):
        self.memory = bytearray(memory if memory is not None else b'')
        self.memory += b'\xff' * (self.SIZE - len(self.memory))
        self.frames = []            # ('set' | 'get', bytes)
        self._pending = None

    def set_feature(self, frame):
        frame = bytes(frame)
        self.frames.append(('set', frame))
        cmd, addr, length = frame[1], frame[2] | frame[3] << 8, frame[4] | frame[5] << 8
        if cmd == READ:
            self._pending = (addr, length)
        elif cmd == WRITE:
            self.memory[addr:addr + length] = frame[8:8 + length]

    def get_feature(self, rid):
        addr, length = self._pending
        size = REPORT_SIZES[rid]
        reply = bytes([rid, READ, addr & 0xFF, addr >> 8, length & 0xFF, length >> 8, 0, 0])
        reply += bytes(self.memory[addr:addr + size - 8])
        self.frames.append(('get', reply))
        return reply + bytes(size - len(reply))

    def close(self):
        pass


def conflicting_programs():
    """VCFG's programs that talk to the mouse at the same time: under Wine/Proton on
    Linux; VCFG.exe itself on Windows."""
    return transport().conflicting_programs()


def conflict_text(found):
    """'vcfg.exe is running under Wine/Proton' (Linux) or 'vcfg.exe is running' (Windows)."""
    return ', '.join(found) + ' is running' + transport().CONFLICT_WHERE


# --- Protocol ------------------------------------------------------------------

class Mouse:
    """Commands of the mouse, in VCFG's order and timing."""

    def __init__(self, io, pace=True):
        self.io = io
        self.pace = pace

    def _sleep(self, seconds):
        if self.pace:
            time.sleep(seconds)

    def _set(self, frame):
        self.io.set_feature(frame)
        self._sleep(0.1 if len(frame) >= REPORT_SIZES[4] else 0.02)

    def command(self, cmd, *args):
        self._set(command_frame(cmd, *args))

    @contextlib.contextmanager
    def session(self, opens=1):
        for _ in range(opens):
            self.command(SESSION, 0)
        try:
            yield
        finally:
            self.command(SESSION, 1)

    # The mouse answers reads through the 1024-byte report 4 ten times slower than
    # through the 64-byte report 3 (0.9 s against 0.07 s), so longer reads are split.
    READ_CHUNK = REPORT_SIZES[3] - 8

    def read(self, addr, length):
        if length > self.READ_CHUNK:
            return b''.join(self.read(a, min(self.READ_CHUNK, addr + length - a))
                            for a in range(addr, addr + length, self.READ_CHUNK))
        rid = report_for(length)
        expected = bytes([rid, READ, addr & 0xFF, addr >> 8, length & 0xFF, length >> 8])
        for _ in range(3):
            self.io.set_feature(data_frame(READ, addr, length))
            self._sleep(0.01)
            reply = self.io.get_feature(rid)
            if reply[:6] == expected:
                return reply[8:8 + length]
            self._sleep(0.05)
        raise DeviceError(f'the mouse answered a different request while reading 0x{addr:04x}. '
                          f'Is VCFG running{transport().CONFLICT_WHERE}?')

    def write(self, addr, data):
        check_writable(addr, len(data))
        self._set(data_frame(WRITE, addr, len(data), data))

    # High-level reads (call inside a session)

    def read_active(self):
        return self.read(ACTIVE_PROFILE, 1)[0]

    def read_profile_blocks(self, n):
        return {
            'dpi': self.read(dpi_addr(n), 42),
            'buttons': self.read(buttons_addr(n), 57),
            'light': self.read(light_addr(n), 6),
            'polling': self.read(POLLING + n, 1),
        }

    def read_macro(self, slot, length):
        if not 0 < length <= model.MACRO_SIZE:
            raise DeviceError(f'macro {slot + 1}: implausible length {length}')
        return self.read(macro_addr(slot), length)

    def read_macro_slot(self, slot):
        """Content of a slot no button uses (its length is unknown): Macro or None.
        Call inside a session."""
        data = self.read(macro_addr(slot), 6)          # a quick look first (report 2)
        if data[0] == 0xFF:
            return None             # never written
        while not any(data[j] == 0x07 for j in range(0, len(data) - 2, 3)) and len(data) < model.MACRO_SIZE:
            data += self.read(macro_addr(slot) + len(data), min(self.READ_CHUNK, model.MACRO_SIZE - len(data)))
        try:
            m = model.decode_macro(data)
        except ValueError:
            return None             # not a macro
        return None if any(s.kind == 'unknown' for s in m.steps) else m

    def read_state(self, profiles=range(PROFILES)):
        """Active profile, decoded profiles and the macros they use."""
        with self.session():
            active = self.read_active()
            blocks = {n: self.read_profile_blocks(n) for n in profiles}
            decoded, errors = {}, {}
            for n, b in blocks.items():
                try:
                    decoded[n] = model.decode_profile(**b)
                except ValueError as e:
                    errors[n] = str(e)
            lengths = {}
            for p in decoded.values():
                for a in p.buttons:
                    if a.kind == 'macro':
                        lengths[a.code] = a.raw[2] | a.raw[3] << 8
            macros = {}
            for slot, n in sorted(lengths.items()):
                try:
                    macros[slot] = model.decode_macro(self.read_macro(slot, n))
                except (ValueError, DeviceError) as e:
                    errors[f'macro {slot + 1}'] = str(e)
        return State(active, decoded, macros, blocks, errors)

    def dump(self, start, length, chunk=56):
        out = bytearray()
        with self.session():
            for addr in range(start, start + length, chunk):
                out += self.read(addr, min(chunk, start + length - addr))
        return bytes(out)

    # Writes, in VCFG's exact order

    def apply_blocks(self, n, blocks, macros=None, active=None, keep_stage=False):
        """Write profile n like VCFG's Apply button; returns the blocks written.

        blocks: the 'dpi', 'buttons', 'light' and 'polling' bytes of the profile;
        macros: {slot: bytes} for the macros it uses; active: profile to leave
        active (default: unchanged). VCFG first reads the active profile's DPI
        block back; with keep_stage, if profile n is the active one, the DPI level
        selected on the mouse (with its DPI button) is kept, as VCFG does.
        """
        for slot, data in (macros or {}).items():
            check_writable(macro_addr(slot), len(data))
        self.command(SESSION, 0)
        self.command(SESSION, 0)
        try:
            current = self.read_active()
            live = self.read(dpi_addr(current if current < PROFILES else n), 42)
        finally:
            self.command(SESSION, 1)
        stage = live[1]
        dpi = blocks['dpi']
        if keep_stage and n == current and stage < model.DPI_LEVELS and dpi[2 + 8 * stage] and stage != dpi[1]:
            blocks = dict(blocks, dpi=dpi[:1] + bytes([stage]) + dpi[2:])
        try:
            self.write(buttons_addr(n), blocks['buttons'])
            self.write(light_addr(n), blocks['light'])
            self.write(dpi_addr(n), blocks['dpi'])
            self.write(POLLING + n, blocks['polling'])
            for slot, data in sorted((macros or {}).items()):
                self.write(macro_addr(slot), data)
            self.write(ACTIVE_PROFILE, bytes([current if active is None else active]))
        finally:
            self.command(SESSION, 1)
        self.command(COMMIT, 1, 0)
        return blocks

    def apply_profile(self, n, profile, macros=None, active=None, keep_stage=False):
        """Encode and write profile n. macros: {slot: model.Macro} used by the profile.
        -> (blocks written, {slot: macro bytes})"""
        data = {slot: model.encode_macro(m) for slot, m in (macros or {}).items()}
        missing = set(profile.macro_slots()) - set(data)
        if missing:
            raise ValueError('macro content missing for slot(s) ' + ', '.join(str(s + 1) for s in sorted(missing)))
        blocks = model.encode_profile(profile, {slot: len(b) for slot, b in data.items()})
        blocks = self.apply_blocks(n, blocks, data, active, keep_stage)
        return blocks, data

    def switch_profile(self, n):
        """Make profile n (0-4) active, like clicking PROFILE1-5 in VCFG."""
        if not 0 <= n < PROFILES:
            raise ValueError('profile must be 1-5')
        self.write(ACTIVE_PROFILE, bytes([n]))
        self.command(COMMIT, 1, n)

    def preview_light(self, light):
        """Show a light setting without saving it (VCFG sends the preview twice)."""
        payload = model.encode_light(light)
        self.command(PREVIEW, *payload)
        self.command(PREVIEW, *payload)

    def verify(self, n, blocks, macros=None):
        """Read profile n back and return the names of blocks that differ."""
        with self.session():
            got = self.read_profile_blocks(n)
            got_macros = {slot: self.read(macro_addr(slot), len(data))
                          for slot, data in (macros or {}).items()}
        bad = [name for name in ('dpi', 'buttons', 'light', 'polling') if got[name] != blocks[name]]
        bad += [f'macro {slot + 1}' for slot, data in (macros or {}).items() if got_macros[slot] != data]
        return bad


def fake_from_state(state):
    """A FakeMouse holding what `state` read from the real mouse (for --dry-run)."""
    fake = FakeMouse()
    fake.memory[ACTIVE_PROFILE] = state.active
    for n, b in state.blocks.items():
        fake.memory[POLLING + n] = b['polling'][0]
        for name, addr in (('dpi', dpi_addr(n)), ('buttons', buttons_addr(n)), ('light', light_addr(n))):
            fake.memory[addr:addr + len(b[name])] = b[name]
    for slot, m in state.macros.items():
        data = model.encode_macro(m)
        fake.memory[macro_addr(slot):macro_addr(slot) + len(data)] = data
    return fake


def describe_frame(kind, frame):
    """One line for --dry-run output."""
    body = frame[:8] + frame[8:].rstrip(b'\0')
    padding = len(frame) - len(body)
    text = body.hex(' ')
    if padding:
        text += f'  (+{padding} zero bytes)'
    return f'{kind.upper()} report {frame[0]}: {text}'


class State:
    def __init__(self, active, profiles, macros, blocks, errors=None):
        self.active = active          # 0-based
        self.profiles = profiles      # {n: model.Profile}, profiles that decoded
        self.macros = macros          # {slot: model.Macro}
        self.blocks = blocks          # {n: raw byte blocks as read}
        self.errors = errors or {}    # {n or 'macro N': why it could not be decoded}


def open_mouse(path=None):
    return Mouse(transport().Device(path))
