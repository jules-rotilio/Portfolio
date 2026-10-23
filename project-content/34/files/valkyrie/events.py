"""What the mouse reports by itself when its own buttons change a setting.

The vendor interface (the one device.py uses) also sends input reports,
which VCFG's tray program VMON.exe listens to (TVMONMAIN_uiHIDData1Data):

  report 8  [08, 01, n]  profile n (0-4) is now active (seen on the mouse)
            [08, 02, n]  DPI level n (0-4) of the active profile is now in use
            [08, 06, v]  polling interval byte v (1, 2, 4, 8 = 1000-125 Hz)
  report 7  [07, b0, b1, b2]  a 24-bit "virtual key" bitmap (bit i = button i).
            VMON only acts on it for its Mute function, which this VCFG has no
            menu entry for; it was never seen on this mouse.

The mouse keeps the new profile, DPI level and polling rate in its memory, so
these reports only tell the PC what changed.
"""
from dataclasses import dataclass

from . import device, model

REPORT_STATUS, REPORT_KEYS = 8, 7
STATUS_KINDS = {0x01: 'profile', 0x02: 'dpi', 0x06: 'rate'}


@dataclass(frozen=True)
class Event:
    kind: str           # 'profile', 'dpi', 'rate', 'keys' or 'unknown'
    value: int          # profile 0-4, DPI level 0-4, polling byte, key bitmap or raw bytes
    raw: bytes = b''

    def describe(self):
        if self.kind == 'profile':
            return f'profile {self.value + 1}'
        if self.kind == 'dpi':
            return f'DPI level {self.value + 1}'
        if self.kind == 'rate':
            hz = model.POLLING_HZ.get(self.value)
            return f'report rate {hz} Hz' if hz else f'report rate (raw {self.value})'
        if self.kind == 'keys':
            pressed = [str(i + 1) for i in range(24) if self.value >> i & 1]
            return 'virtual keys ' + (', '.join(pressed) if pressed else 'released')
        return 'report ' + self.raw.hex(' ')


def decode(report):
    """One input report (report ID first) -> Event, or None for reports that are
    not about settings (the consumer-control report 1, for example)."""
    report = bytes(report)
    if not report:
        return None
    if report[0] == REPORT_STATUS and len(report) >= 3:
        kind = STATUS_KINDS.get(report[1])
        if kind is None:
            return Event('unknown', report[1], report)
        return Event(kind, report[2], report)
    if report[0] == REPORT_KEYS and len(report) >= 4:
        return Event('keys', report[1] | report[2] << 8 | report[3] << 16, report)
    return None


class Listener:
    """Reads the input reports of the mouse's vendor interface (hidraw on Linux, the
    HID class driver on Windows). Several programs can listen at once; each gets
    every report."""

    def __init__(self, path=None):
        self.raw = device.transport().Listener(path)
        self.path = self.raw.path

    def fileno(self):
        """The hidraw node's descriptor, for select() (Linux only)."""
        return self.raw.fileno()

    def read(self, timeout=0):
        """-> list of Events, waiting up to `timeout` seconds (None: until one comes)
        for the first report. Raises DeviceError if the mouse is gone."""
        return [e for e in map(decode, self.raw.read(timeout)) if e is not None]

    def close(self):
        self.raw.close()
