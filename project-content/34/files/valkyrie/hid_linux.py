"""The mouse's vendor interface on Linux: a hidraw node.

Feature reports go through the HIDIOCSFEATURE/HIDIOCGFEATURE ioctls; the input
reports the mouse sends by itself are read from the same node.
"""
import errno
import fcntl
import glob
import os
import select

from .device import PRODUCT_ID, REPORT_SIZES, VENDOR_ID, DeviceError

PERMISSION_HINT = 'Install the udev rule from udev/70-drakkar-valkyrie.rules (see README.md).'


def _ioc(nr, size):
    return (3 << 30) | (size << 16) | (ord('H') << 8) | nr     # _IOC(READ|WRITE, 'H', nr, size)


def find_device():
    """Path of the hidraw node for the mouse's vendor interface (usage page 0xFFA0)."""
    hid_id = f'HID_ID=0003:{VENDOR_ID:08X}:{PRODUCT_ID:08X}'
    for node in sorted(glob.glob('/sys/class/hidraw/hidraw*')):
        try:
            with open(f'{node}/device/uevent', encoding='utf-8') as f:
                if hid_id not in f.read().split():
                    continue
            with open(f'{node}/device/report_descriptor', 'rb') as f:
                if b'\x06\xa0\xff' not in f.read():
                    continue
        except OSError:
            continue
        return '/dev/' + os.path.basename(node)
    raise DeviceError('Drakkar Valkyrie not found (is it plugged in?)')


class Device:
    def __init__(self, path=None):
        self.path = path or find_device()
        try:
            self.fd = os.open(self.path, os.O_RDWR)
        except PermissionError:
            raise DeviceError(f'no permission to open {self.path}. {PERMISSION_HINT}') from None

    def set_feature(self, frame):
        n = fcntl.ioctl(self.fd, _ioc(0x06, len(frame)), bytearray(frame), True)
        if n != len(frame):
            raise DeviceError(f'short write: {n} of {len(frame)} bytes')

    def get_feature(self, rid):
        buf = bytearray(REPORT_SIZES[rid])
        buf[0] = rid
        fcntl.ioctl(self.fd, _ioc(0x07, len(buf)), buf, True)
        return bytes(buf)

    def close(self):
        os.close(self.fd)


class Listener:
    """Reads the input reports of the vendor hidraw node. Several programs can listen
    at once; each gets every report."""

    def __init__(self, path=None):
        self.path = path or find_device()
        try:
            self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        except PermissionError:
            raise DeviceError(f'no permission to read {self.path}. {PERMISSION_HINT}') from None

    def fileno(self):
        return self.fd

    def read(self, timeout=0):
        """-> list of raw reports, waiting up to `timeout` seconds (None: until one
        comes) for the first. Raises DeviceError if the mouse is gone."""
        if timeout != 0:
            select.select([self.fd], [], [], timeout)
        reports = []
        while True:
            try:
                report = os.read(self.fd, 64)
            except BlockingIOError:
                return reports
            except OSError as e:
                if e.errno in (errno.ENODEV, errno.EIO):
                    raise DeviceError('the mouse was unplugged') from None
                raise
            if not report:
                return reports
            reports.append(report)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def conflicting_programs():
    """VCFG's programs running under Wine/Proton, which also talk to the mouse."""
    names = ('vcfg.exe', 'vmon.exe', 'etgmsrv.exe')
    found = set()
    for path in glob.glob('/proc/[0-9]*/cmdline'):
        try:
            with open(path, 'rb') as f:
                cmdline = f.read().decode(errors='replace').lower()
        except OSError:
            continue
        found.update(n for n in names if n in cmdline)
    return sorted(found)


CONFLICT_WHERE = ' under Wine/Proton'
