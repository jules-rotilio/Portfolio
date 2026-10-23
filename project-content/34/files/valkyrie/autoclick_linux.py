"""valkyrie-autoclick on Linux.

It reads the mouse's keyboard interface (/dev/input/event*) and clicks through a
virtual mouse (/dev/uinput), so it works on Wayland and X11 alike. The trigger keys
are hidden from other programs: the daemon grabs the interface and forwards every
other key unchanged through a virtual keyboard. Reload is SIGHUP.
"""
import ctypes
import ctypes.util
import errno
import glob
import os
import queue
import selectors
import shutil
import signal
import subprocess
import threading
import time

from . import paths
from .autoclick import BUTTONS, LOW, HIGH, RATE, BaseDaemon, chime, chime_pcm, log, tones
from .linux_input import EV_KEY, EV_SYN, EVENT, BUS_USB, Uinput, _bits, grab, sysfs

PLAYERS = (['pw-play'], ['paplay'], ['aplay', '-q'])


class _SampleSpec(ctypes.Structure):
    _fields_ = [('format', ctypes.c_int), ('rate', ctypes.c_uint32), ('channels', ctypes.c_uint8)]


class Sounds:
    """Plays the start/stop chimes without blocking the click loop and without
    starting a process: a thread inside the daemon plays them through the
    PulseAudio API (served by PipeWire). A stream is only open while a chime
    plays, so the sound card can still go idle. Falls back to pw-play/paplay/aplay
    if libpulse-simple is missing."""

    PA_STREAM_PLAYBACK, PA_SAMPLE_S16LE = 1, 3

    def __init__(self, volume):
        self.volume = volume
        self.pcm = chime_pcm(volume)
        self.queue = queue.Queue()
        self.pulse = None
        name = ctypes.util.find_library('pulse-simple')
        if name:
            try:
                self.pulse = ctypes.CDLL(name)
                self.pulse.pa_simple_new.restype = ctypes.c_void_p
                for fn in ('pa_simple_write', 'pa_simple_drain', 'pa_simple_free'):
                    getattr(self.pulse, fn).argtypes = [ctypes.c_void_p] + (
                        [] if fn == 'pa_simple_free' else
                        [ctypes.c_char_p, ctypes.c_size_t, ctypes.c_void_p] if fn == 'pa_simple_write' else
                        [ctypes.c_void_p])
            except (OSError, AttributeError) as e:
                log(f'libpulse-simple not usable ({e}); using a sound player program')
                self.pulse = None
        if self.pulse is None:
            self._setup_player(volume)
        threading.Thread(target=self._worker, name='sounds', daemon=True).start()

    def _setup_player(self, volume):
        self.player = next((p for p in PLAYERS if shutil.which(p[0])), None)
        self.files = {}
        for name, freqs in (('on', (LOW, HIGH)), ('off', (HIGH, LOW))):
            path = os.path.join(paths.run_dir(), f'valkyrie-autoclick-{name}.wav')
            with open(path, 'wb') as f:
                f.write(chime(freqs, volume))
            self.files[name] = path
        if self.player is None:
            log('no sound player found (pw-play, paplay or aplay); sounds are off')

    def play(self, name):
        self.queue.put((name, self.pcm[name]))

    def beep(self, freq):
        """Short beep; dropped if sounds are still waiting (e.g. while a key repeats)."""
        if self.queue.empty():
            self.queue.put(('beep', tones((freq,), self.volume, tone=0.05)))

    def close(self):
        self.queue.put(None)

    def _worker(self):
        while (item := self.queue.get()) is not None:
            name, pcm = item
            try:
                if self.pulse is not None:
                    self._play_pulse(pcm)
                elif self.player is not None and name in self.files:
                    subprocess.run(self.player + [self.files[name]],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception as e:                  # a sound must never stop the clicker
                log(f'could not play a sound: {e}')

    def _play_pulse(self, pcm):
        spec = _SampleSpec(self.PA_SAMPLE_S16LE, RATE, 1)
        error = ctypes.c_int(0)
        handle = self.pulse.pa_simple_new(None, b'valkyrie autoclick', self.PA_STREAM_PLAYBACK, None,
                                          b'toggle sound', ctypes.byref(spec), None, None,
                                          ctypes.byref(error))
        if not handle:
            raise OSError(f'cannot connect to the sound server (error {error.value})')
        try:
            if self.pulse.pa_simple_write(handle, pcm, len(pcm), ctypes.byref(error)) < 0:
                raise OSError(f'write failed (error {error.value})')
            self.pulse.pa_simple_drain(handle, ctypes.byref(error))
        finally:
            self.pulse.pa_simple_free(handle)


def find_trigger_devices(wanted):
    """Event nodes of the mouse that can send one of the wanted key codes."""
    found = []
    for node in sorted(glob.glob('/sys/class/input/event*')):
        try:
            bus, vendor, product = (int(sysfs(node, f'id/{k}'), 16) for k in ('bustype', 'vendor', 'product'))
            caps = _bits(sysfs(node, 'capabilities/key'))
            ev = int(sysfs(node, 'capabilities/ev'), 16)
        except (OSError, ValueError):
            continue
        if (bus, vendor, product) != (BUS_USB, 0x04D9, 0xFC06):      # not our own virtual devices
            continue
        if any(caps >> code & 1 for code in wanted):
            # Only grab pure keyboard nodes: anything else (wheel, volume knob) would be lost.
            pure = ev & ~((1 << EV_SYN) | (1 << EV_KEY) | (1 << 4) | (1 << 17) | (1 << 20)) == 0
            found.append(('/dev/input/' + os.path.basename(node), caps, pure))
    return found


class Daemon(BaseDaemon):
    def __init__(self, path):
        super().__init__(path)
        self.sources = {}           # fd -> (path, grabbed)
        self.forward_down = set()   # keys forwarded as pressed, released on exit
        self.selector = selectors.DefaultSelector()
        self.next_scan = 0.0
        self.mouse = Uinput('valkyrie autoclick', BUTTONS.values(), rel=True)
        self.keyboard = None

    def send_buttons(self, events):
        self.mouse.send([(EV_KEY, b, v) for b, v in events])

    def make_sounds(self, volume):
        return Sounds(volume)

    def show_notification(self, text, urgent):
        if shutil.which('notify-send'):
            subprocess.Popen(['notify-send', '-a', 'valkyrie autoclick', '-u',
                              'critical' if urgent else 'low', 'Auto-click', text],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def reopen(self):
        self.close_sources()
        self.next_scan = 0.0

    def open_sources(self):
        if self.config.device != 'auto':
            candidates = [(self.config.device, None, True)]
        else:
            candidates = find_trigger_devices(self.config.keys)
        for path, caps, pure in candidates:
            if any(p == path for p, _ in self.sources.values()):
                continue
            try:
                fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
            except PermissionError:
                log(f'no permission to read {path} (install the udev rule, see README)')
                continue
            except OSError:
                continue
            grabbed = False
            if self.config.swallow and pure:
                if self.keyboard is None:
                    codes = [c for c in range(1, 0x300) if caps is None or caps >> c & 1]
                    self.keyboard = Uinput('valkyrie autoclick keys', codes)
                try:
                    grab(fd, True)
                    grabbed = True
                except OSError as e:
                    log(f'{path}: could not grab ({e}); trigger keys stay visible')
            self.sources[fd] = (path, grabbed)
            self.selector.register(fd, selectors.EVENT_READ)
            log(f'listening on {path}' + (' (trigger keys hidden)' if grabbed else ''))

    def close_sources(self):
        for fd in list(self.sources):
            self.close_source(fd)

    def close_source(self, fd):
        path, grabbed = self.sources.pop(fd)
        self.selector.unregister(fd)
        if grabbed:
            try:
                grab(fd, False)
            except OSError:
                pass
        os.close(fd)
        if self.keyboard is not None and self.forward_down:
            self.keyboard.send([(EV_KEY, c, 0) for c in self.forward_down])
            self.forward_down.clear()

    def read_source(self, fd, now):
        path, grabbed = self.sources[fd]
        try:
            data = os.read(fd, EVENT.size * 64)
        except OSError as e:
            if e.errno in (errno.ENODEV, errno.EIO):
                log(f'{path} disappeared; waiting for the mouse to come back')
                self.release_all()
                self.close_source(fd)
                return
            raise
        forward = []
        for i in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _, _, etype, code, value = EVENT.unpack_from(data, i)
            if etype == EV_KEY and self.key_event(code, value, now):
                continue
            if grabbed and etype == EV_KEY:
                forward.append((etype, code, value))
                if value == 1:
                    self.forward_down.add(code)
                elif value == 0:
                    self.forward_down.discard(code)
        if grabbed and forward:
            self.keyboard.send(forward)

    def run(self):
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, lambda *_: self.stop())
        # Python restarts select() after a signal handler, so a signal alone would
        # not end the wait; the wakeup pipe makes every signal wake the loop.
        wake_r, wake_w = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        signal.set_wakeup_fd(wake_w)
        self.selector.register(wake_r, selectors.EVENT_READ)
        try:
            while not self.stopping:
                if self.reload_wanted:
                    self.reload()
                now = time.monotonic()
                if not self.sources and now >= self.next_scan:
                    self.open_sources()
                    self.next_scan = now + 2.0
                    if not self.sources:
                        log('mouse not found; retrying every 2 s')
                timeout = self.click_due(now)
                if not self.sources:
                    timeout = min(timeout if timeout is not None else 2.0, max(0.0, self.next_scan - now))
                try:
                    ready = self.selector.select(timeout)
                except InterruptedError:
                    continue
                for key, _ in ready:
                    if key.fd == wake_r:
                        while True:
                            try:
                                os.read(wake_r, 64)
                            except BlockingIOError:
                                break
                    elif key.fd in self.sources:
                        self.read_source(key.fd, time.monotonic())
        finally:
            self.release_all()
            self.close_sources()
            self.mouse.close()
            if self.keyboard is not None:
                self.keyboard.close()
            signal.set_wakeup_fd(-1)
            self.selector.unregister(wake_r)
            os.close(wake_r)
            os.close(wake_w)
