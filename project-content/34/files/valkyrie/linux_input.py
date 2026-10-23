"""Linux input devices: evdev nodes (/dev/input/event*) and virtual devices (/dev/uinput).
Used by the Linux sides of valkyrie-autoclick and valkyrie-monitor."""
import fcntl
import os
import struct

EV_SYN, EV_KEY, EV_REL, EV_MSC = 0x00, 0x01, 0x02, 0x04
SYN_REPORT = 0
REL_X, REL_Y = 0x00, 0x01
EVENT = struct.Struct('llHHi')             # struct input_event on 64-bit Linux

UI_SET_EVBIT, UI_SET_KEYBIT, UI_SET_RELBIT, UI_SET_MSCBIT = 0x40045564, 0x40045565, 0x40045566, 0x40045568
UI_DEV_SETUP, UI_DEV_CREATE, UI_DEV_DESTROY = 0x405C5503, 0x5501, 0x5502
EVIOCGRAB = 0x40044590
BUS_USB, BUS_VIRTUAL = 0x03, 0x06


def _bits(text):
    value = 0
    for word in text.split():
        value = value << 64 | int(word, 16)
    return value


def sysfs(node, name):
    """Contents of /sys/class/input/eventN/device/<name>, stripped."""
    with open(f'{node}/device/{name}', encoding='utf-8') as f:
        return f.read().strip()


def grab(fd, on):
    fcntl.ioctl(fd, EVIOCGRAB, 1 if on else 0)


class Uinput:
    """A virtual input device."""

    def __init__(self, name, key_codes, rel=False):
        try:
            self.fd = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        except PermissionError:
            raise SystemExit('no permission to open /dev/uinput (see README: autoclick setup)') from None
        fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_KEY)
        for code in key_codes:
            fcntl.ioctl(self.fd, UI_SET_KEYBIT, code)
        if rel:                          # makes desktops treat it as a mouse
            fcntl.ioctl(self.fd, UI_SET_EVBIT, EV_REL)
            fcntl.ioctl(self.fd, UI_SET_RELBIT, REL_X)
            fcntl.ioctl(self.fd, UI_SET_RELBIT, REL_Y)
        setup = struct.pack('<4H80sI', BUS_VIRTUAL, 0, 0, 1, name.encode(), 0)
        fcntl.ioctl(self.fd, UI_DEV_SETUP, setup)
        fcntl.ioctl(self.fd, UI_DEV_CREATE)

    def send(self, events):
        if not events:
            return
        data = b''.join(EVENT.pack(0, 0, t, c, v) for t, c, v in events)
        os.write(self.fd, data + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))

    def close(self):
        try:
            fcntl.ioctl(self.fd, UI_DEV_DESTROY)
        finally:
            os.close(self.fd)
