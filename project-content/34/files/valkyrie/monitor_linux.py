"""valkyrie-monitor on Linux.

Notifications go through notify-send. With exact_dpi on, the daemon grabs the
mouse's pointer node and sends the movement through a virtual copy of the mouse
(same name and USB IDs, so the desktop applies the same mouse settings). The mouse
is only grabbed while the DPI level in use needs scaling. Windows pointer settings
(pointer speed, scroll lines...) are not applied: the desktop's own mouse settings
do that. Reload is SIGHUP.
"""
import errno
import fcntl
import glob
import os
import queue
import selectors
import shutil
import signal
import struct
import subprocess
import threading
import time

from . import device
from .autoclick import log
from .linux_input import (BUS_USB, EV_KEY, EV_MSC, EV_REL, EV_SYN, EVENT, REL_X, REL_Y, SYN_REPORT,
                          UI_DEV_CREATE, UI_DEV_DESTROY, UI_DEV_SETUP, UI_SET_EVBIT, UI_SET_KEYBIT,
                          UI_SET_MSCBIT, UI_SET_RELBIT, _bits, grab, sysfs)
from .monitor import BaseDaemon


class Notifier:
    """Desktop notifications through notify-send, replacing the previous one so quick
    presses do not pile up. Runs in a thread: pointer movement never waits for it."""

    def __init__(self):
        self.queue = queue.Queue()
        self.last_id = None
        self.available = shutil.which('notify-send') is not None
        if not self.available:
            log('notify-send not found; notifications are off')
        threading.Thread(target=self._worker, name='notify', daemon=True).start()

    def show(self, title, body=''):
        if self.available:
            self.queue.put((title, body))

    def close(self):
        self.queue.put(None)

    def _worker(self):
        while (item := self.queue.get()) is not None:
            while not self.queue.empty():          # only the latest one matters
                nxt = self.queue.get()
                if nxt is None:
                    return
                item = nxt
            title, body = item
            cmd = ['notify-send', '-a', 'Drakkar Valkyrie', '-i', 'input-mouse', '-t', '2000',
                   '-h', 'boolean:transient:true', '-p']
            if self.last_id:
                cmd += ['-r', self.last_id]
            try:
                out = subprocess.run(cmd + [title, body], capture_output=True, text=True, encoding='utf-8',
                                     timeout=5)
                self.last_id = out.stdout.strip() or None
            except (OSError, subprocess.SubprocessError) as e:
                log(f'notification failed: {e}')


# --- The pointer proxy ------------------------------------------------------------------

def find_pointer():
    """The mouse's pointer event node: (path, name, (bus, vendor, product, version), caps)."""
    for node in sorted(glob.glob('/sys/class/input/event*')):
        if '/virtual/' in os.path.realpath(f'{node}/device'):
            continue                          # our own copy, or another virtual device
        try:
            ids = tuple(int(sysfs(node, f'id/{k}'), 16) for k in ('bustype', 'vendor', 'product', 'version'))
            if ids[1:3] != (device.VENDOR_ID, device.PRODUCT_ID):
                continue
            caps = {k: _bits(sysfs(node, f'capabilities/{k}')) for k in ('ev', 'key', 'rel', 'msc')}
            name = sysfs(node, 'name')
        except (OSError, ValueError):
            continue
        if caps['rel'] >> REL_X & 1 and caps['rel'] >> REL_Y & 1:
            return '/dev/input/' + os.path.basename(node), name, ids, caps
    return None


class Proxy:
    """Reads the mouse's pointer node; while scaling is needed it grabs the node and
    sends the scaled movement (and everything else unchanged) through a copy."""

    def __init__(self, found, scaler):
        self.path, name, ids, caps = found
        self.scaler = scaler
        self.fd = os.open(self.path, os.O_RDONLY | os.O_NONBLOCK)
        self.grabbed = False
        self.held = set()                     # buttons down on the real mouse
        self.batch = []
        try:
            self.out = os.open('/dev/uinput', os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            os.close(self.fd)
            raise
        try:
            for bit in (EV_KEY, EV_REL, EV_MSC):
                if caps['ev'] >> bit & 1:
                    fcntl.ioctl(self.out, UI_SET_EVBIT, bit)
            for ioc, bits, top in ((UI_SET_KEYBIT, caps['key'], 0x300), (UI_SET_RELBIT, caps['rel'], 16),
                                   (UI_SET_MSCBIT, caps['msc'], 8)):
                for code in range(top):
                    if bits >> code & 1:
                        fcntl.ioctl(self.out, ioc, code)
            bus, vendor, product, version = ids
            setup = struct.pack('<4H80sI', BUS_USB, vendor, product, version, name.encode()[:79], 0)
            fcntl.ioctl(self.out, UI_DEV_SETUP, setup)
            fcntl.ioctl(self.out, UI_DEV_CREATE)
        except OSError:
            os.close(self.out)
            os.close(self.fd)
            raise

    def fileno(self):
        return self.fd

    def update_grab(self):
        """Grab while scaling is needed; only switch while no button is held, so no
        press and release end up on different devices."""
        if self.held or self.scaler.needed == self.grabbed:
            return
        try:
            self.set_grab(self.scaler.needed)
            self.grabbed = self.scaler.needed
            log('scaling the movement' if self.grabbed else 'movement passed through unchanged')
        except OSError as e:
            log(f'{self.path}: could not {"grab" if self.scaler.needed else "release"} ({e})')

    def set_grab(self, on):
        grab(self.fd, on)

    def read(self):
        data = os.read(self.fd, EVENT.size * 64)
        for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _, _, etype, code, value = EVENT.unpack_from(data, i)
            if etype == EV_KEY:
                (self.held.add if value else self.held.discard)(code)
            if etype == EV_SYN:
                if code == SYN_REPORT:
                    if self.grabbed and self.batch:
                        self.send(self.batch)
                    self.batch = []
                    self.update_grab()
                continue
            if not self.grabbed:
                continue
            if etype == EV_REL and code in (REL_X, REL_Y):
                value = self.scaler.scale(code, value)
                if value == 0:
                    continue
            self.batch.append((etype, code, value))

    def send(self, items):
        data = b''.join(EVENT.pack(0, 0, t, c, v) for t, c, v in items)
        os.write(self.out, data + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))

    def close(self):
        if self.grabbed:
            try:
                self.set_grab(False)
            except OSError:
                pass
        os.close(self.fd)
        try:
            fcntl.ioctl(self.out, UI_DEV_DESTROY)
        finally:
            os.close(self.out)


# --- Daemon -------------------------------------------------------------------------

class Daemon(BaseDaemon):
    def __init__(self, path):
        self.selector = selectors.DefaultSelector()
        self.proxy = None
        super().__init__(path)

    def make_notifier(self):
        return Notifier()

    def exact_dpi_available(self):
        return True

    def scaling_changed(self):
        if self.proxy is not None:
            self.proxy.update_grab()

    def on_profile(self):
        pass                                   # the desktop applies its own mouse settings

    def open_listener(self):
        opened = super().open_listener()
        if opened:
            self.selector.register(self.listener.fileno(), selectors.EVENT_READ, 'listener')
        return opened

    def close_listener(self):
        if self.listener is not None:
            self.selector.unregister(self.listener.fileno())
        super().close_listener()

    def open_devices(self):
        if self.listener is None:
            self.open_listener()
        if self.config.exact_dpi and self.proxy is None:
            found = find_pointer()
            if found is None:
                return
            try:
                self.proxy = Proxy(found, self.scaler)
            except PermissionError:
                log(f'no permission to read {found[0]} or write /dev/uinput (see README); exact DPI is off')
                self.config.exact_dpi = False
                return
            except OSError as e:
                log(f'cannot copy the mouse: {e}')
                return
            self.selector.register(self.proxy.fd, selectors.EVENT_READ, 'proxy')
            log(f'following {found[0]} for exact DPI')
            self.proxy.update_grab()

    def close_proxy(self):
        if self.proxy is not None:
            self.selector.unregister(self.proxy.fd)
            self.proxy.close()
            self.proxy = None

    def on_listener(self):
        try:
            got = self.listener.read()
        except device.DeviceError:
            self.mouse_gone()
            return
        self.on_events(got)

    def on_pointer(self):
        try:
            self.proxy.read()
        except OSError as e:
            if e.errno in (errno.ENODEV, errno.EIO):
                self.close_proxy()
                return
            raise

    def run(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: self.stop())
        wake_r, wake_w = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        signal.set_wakeup_fd(wake_w)
        self.selector.register(wake_r, selectors.EVENT_READ, 'wake')
        self.reload()
        self.host_changed()
        self.load_host()                    # until the mouse is read
        try:
            while not self.stopping:
                if self.reload_wanted:
                    self.reload()
                self.periodic()
                try:
                    ready = self.selector.select(max(0.0, self.next_scan - time.monotonic()))
                except InterruptedError:
                    continue
                for key, _ in ready:
                    if key.data == 'wake':
                        while True:
                            try:
                                os.read(wake_r, 64)
                            except BlockingIOError:
                                break
                    elif key.data == 'listener' and self.listener is not None:
                        self.on_listener()
                    elif key.data == 'proxy' and self.proxy is not None:
                        self.on_pointer()
        finally:
            self.close_proxy()
            self.close_listener()
            self.notifier.close()
            signal.set_wakeup_fd(-1)
            self.selector.unregister(wake_r)
            os.close(wake_r)
            os.close(wake_w)
