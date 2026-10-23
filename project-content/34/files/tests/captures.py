"""Frames VCFG.exe exchanged with the mouse, loaded from the usbmon captures."""
import os
import struct

CAPTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'captures')
ALL = ['cap.bin', 'cap2.bin', 'cap3.bin', 'cap4.bin', 'cap5.bin', 'cap6.bin', 'cap7.bin', 'cap8.bin']


def transfers(name):
    """[(time, 'set' | 'get', report id, bytes)] for the feature-report transfers, in order.
    For 'set' the bytes are what VCFG sent; for 'get' they are the mouse's reply."""
    with open(os.path.join(CAPTURES, name), 'rb') as f:
        d = f.read()
    i, pending, out = 0, {}, []
    while i + 64 <= len(d):
        uid, typ, xfer = struct.unpack_from('<QBB', d, i)
        sec, usec = struct.unpack_from('<qi', d, i + 16)
        length = struct.unpack_from('<I', d, i + 36)[0]
        setup, data = d[i + 40:i + 48], d[i + 64:i + 64 + length]
        i += 64 + length
        if xfer != 2:
            continue
        if chr(typ) == 'S':
            pending[uid] = (sec + usec / 1e6, setup, data)
        elif uid in pending:
            t, setup, sent = pending.pop(uid)
            rtype, req, value = struct.unpack_from('<BBH', setup)
            if (rtype, req) == (0x21, 0x09):
                out.append((t, 'set', value & 0xFF, sent))
            elif (rtype, req) == (0xA1, 0x01):
                out.append((t, 'get', value & 0xFF, data))
    return out


def bursts(name, gap=3.0):
    """Transfers grouped into bursts separated by `gap` seconds of silence."""
    groups, last = [], None
    for tr in transfers(name):
        if last is None or tr[0] - last > gap:
            groups.append([])
        groups[-1].append(tr)
        last = tr[0]
    return groups


def memory_dump():
    """The mouse's memory 0x000-0xfff, read on 2026-10-14 (valkyrie dump-memory)."""
    with open(os.path.join(CAPTURES, 'memory-0000-0fff.bin'), 'rb') as f:
        return f.read()


def writes(name):
    """[(time, address, payload)] for every write command VCFG sent."""
    out = []
    for t, kind, rid, frame in transfers(name):
        if kind == 'set' and frame[1] == 0x02:
            addr, length = struct.unpack_from('<HH', frame, 2)
            out.append((t, addr, frame[8:8 + length]))
    return out
