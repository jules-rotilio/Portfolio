"""Record USB control traffic to/from the Drakkar Valkyrie via the usbmon binary API
(Linux only; on Windows, record with USBPcap + Wireshark instead).

Usage: usbcap.py BUS DEV OUT, or usbcap.py auto auto OUT to look up the mouse's
current bus and device number (they change when it is replugged).

Waits until /dev/usbmonN is readable, then appends records to OUT (binary) and
prints a readable line per event. Only keeps control transfers for the mouse and
interrupt-IN on endpoint 0x84 (vendor/consumer interface). Skips 0x81 (movement)
and 0x82 (keyboard interface) so no motion or keystrokes are recorded.
"""
import ctypes, fcntl, glob, os, struct, sys, time


def find_mouse():
    for d in glob.glob('/sys/bus/usb/devices/*'):
        try:
            ids = [open(f'{d}/{n}', encoding='utf-8').read().strip() for n in ('idVendor', 'idProduct', 'busnum', 'devnum')]
        except OSError:
            continue
        if ids[:2] == ['04d9', 'fc06']:
            return int(ids[2]), int(ids[3])
    sys.exit('mouse 04d9:fc06 not found')


if sys.argv[1] == 'auto':
    BUS, DEV = find_mouse()
else:
    BUS, DEV = int(sys.argv[1]), int(sys.argv[2])
OUT = sys.argv[3]
PATH = f'/dev/usbmon{BUS}'

class Hdr(ctypes.Structure):
    _fields_ = [('id', ctypes.c_uint64), ('type', ctypes.c_ubyte), ('xfer_type', ctypes.c_ubyte),
                ('epnum', ctypes.c_ubyte), ('devnum', ctypes.c_ubyte), ('busnum', ctypes.c_ushort),
                ('flag_setup', ctypes.c_char), ('flag_data', ctypes.c_char),
                ('ts_sec', ctypes.c_int64), ('ts_usec', ctypes.c_int32), ('status', ctypes.c_int32),
                ('length', ctypes.c_uint32), ('len_cap', ctypes.c_uint32), ('setup', ctypes.c_ubyte * 8),
                ('interval', ctypes.c_int32), ('start_frame', ctypes.c_int32),
                ('xfer_flags', ctypes.c_uint32), ('ndesc', ctypes.c_uint32)]

class Get(ctypes.Structure):
    _fields_ = [('hdr', ctypes.c_void_p), ('data', ctypes.c_void_p), ('alloc', ctypes.c_size_t)]

MON_IOCX_GETX = (1 << 30) | (ctypes.sizeof(Get) << 16) | (0x92 << 8) | 10
MON_IOCT_RING_SIZE = (0x92 << 8) | 4

while True:
    try:
        fd = os.open(PATH, os.O_RDONLY)
        break
    except OSError:
        time.sleep(1)
try:
    fcntl.ioctl(fd, MON_IOCT_RING_SIZE, 1200 * 1024)
except OSError:
    pass
print(f'recording {PATH} dev {DEV}', flush=True)

hdr = Hdr()
data = ctypes.create_string_buffer(65536)
arg = Get(ctypes.addressof(hdr), ctypes.addressof(data), len(data))
with open(OUT, 'ab') as out:
    while True:
        fcntl.ioctl(fd, MON_IOCX_GETX, arg)
        if hdr.devnum != DEV:
            continue
        if hdr.xfer_type == 1 and hdr.epnum != 0x84:
            continue
        if hdr.xfer_type not in (1, 2):
            continue
        payload = data.raw[:hdr.len_cap]
        out.write(bytes(hdr) + payload)
        out.flush()
        setup = bytes(hdr.setup).hex(' ') if hdr.flag_setup == b'\0' else '-'
        ts = hdr.ts_sec + hdr.ts_usec / 1e6
        print(f'{ts:.6f} {chr(hdr.type)} ep{hdr.epnum:02x} st={hdr.status} len={hdr.length} '
              f'setup={setup} data={payload[:24].hex(" ")}', flush=True)
