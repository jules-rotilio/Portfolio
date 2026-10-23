"""valkyrie-autoclick on Windows.

A low-level keyboard hook (WH_KEYBOARD_LL) sees the keys the mouse sends and hides
the trigger keys from other programs; clicks are sent with SendInput, and sounds
played with winsound. Keys are matched by scan code, the physical key position
(like evdev codes on Linux), so key names mean the same keys on any layout.

The hook cannot tell which keyboard sent a key: a trigger key that a keyboard also
has (not F13-F24) is hidden from every keyboard. Windows also blocks clicks into
programs running as administrator unless this runs as administrator too.

Reload: `valkyrie-autoclick reload`, the tray menu, or the reload key. The tray icon
(PyQt6) also shows the notifications.
"""
import ctypes
import queue
import threading
import time
import winsound
from ctypes import wintypes

from . import winui
from .autoclick import BUTTONS, BaseDaemon, chime_pcm, log, tones, wav

WH_KEYBOARD_LL, HC_ACTION = 13, 0
WM_KEYDOWN, WM_SYSKEYDOWN, WM_QUIT = 0x0100, 0x0104, 0x0012
LLKHF_EXTENDED, LLKHF_INJECTED = 0x01, 0x10
INPUT_MOUSE = 0
# BUTTONS id -> (MOUSEEVENTF_*DOWN, MOUSEEVENTF_*UP)
MOUSE_FLAGS = {BUTTONS['left']: (0x0002, 0x0004), BUTTONS['right']: (0x0008, 0x0010),
               BUTTONS['middle']: (0x0020, 0x0040)}

LRESULT = ctypes.c_ssize_t
HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [('vkCode', wintypes.DWORD), ('scanCode', wintypes.DWORD), ('flags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [('dx', wintypes.LONG), ('dy', wintypes.LONG), ('mouseData', wintypes.DWORD),
                ('dwFlags', wintypes.DWORD), ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [('wVk', wintypes.WORD), ('wScan', wintypes.WORD), ('dwFlags', wintypes.DWORD),
                ('time', wintypes.DWORD), ('dwExtraInfo', ctypes.c_size_t)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [('uMsg', wintypes.DWORD), ('wParamL', wintypes.WORD), ('wParamH', wintypes.WORD)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [('mi', MOUSEINPUT), ('ki', KEYBDINPUT), ('hi', HARDWAREINPUT)]
    _anonymous_ = ('u',)
    _fields_ = [('type', wintypes.DWORD), ('u', _U)]


_user32 = ctypes.WinDLL('user32', use_last_error=True)
_k32 = ctypes.WinDLL('kernel32', use_last_error=True)
_user32.SetWindowsHookExW.restype = wintypes.HHOOK
_user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD]
_user32.CallNextHookEx.restype = LRESULT
_user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
_user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
_user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
_user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
_k32.GetModuleHandleW.restype = wintypes.HMODULE
_k32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


def send_buttons(events):
    """[(button id, 1 pressed | 0 released)] -> one SendInput call."""
    if not events:
        return
    inputs = (INPUT * len(events))()
    for item, (button, value) in zip(inputs, events):
        item.type = INPUT_MOUSE
        item.mi.dwFlags = MOUSE_FLAGS[button][0 if value else 1]
    if _user32.SendInput(len(events), inputs, ctypes.sizeof(INPUT)) != len(events):
        log(f'SendInput failed (error {ctypes.get_last_error()}); is the window in front run as administrator?')


class KeyboardHook:
    """Watches the keys in `keys` (scan code | 0x100 for extended keys): puts
    (code, value) in `events` (value 1 pressed, 2 repeat, 0 released) and,
    with swallow, hides them from other programs. Runs its own thread, since a
    low-level hook needs a message loop."""

    def __init__(self, events):
        self.events = events
        self.keys = frozenset()
        self.swallow = True
        self.down = set()
        self.proc = HOOKPROC(self._proc)          # kept: Windows calls it until unhooked
        self.thread_id = None
        self.failed = None
        started = threading.Event()
        self.thread = threading.Thread(target=self._run, args=(started,), name='keyboard hook', daemon=True)
        self.thread.start()
        started.wait()
        if self.failed:
            raise OSError(self.failed)

    def _run(self, started):
        self.thread_id = _k32.GetCurrentThreadId()
        hook = _user32.SetWindowsHookExW(WH_KEYBOARD_LL, self.proc, _k32.GetModuleHandleW(None), 0)
        if not hook:
            self.failed = f'cannot install the keyboard hook (error {ctypes.get_last_error()})'
            started.set()
            return
        started.set()
        msg = wintypes.MSG()
        try:
            while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                pass
        finally:
            _user32.UnhookWindowsHookEx(hook)

    def _proc(self, n_code, w_param, l_param):
        if n_code == HC_ACTION:
            kb = KBDLLHOOKSTRUCT.from_address(l_param)
            code = kb.scanCode | (0x100 if kb.flags & LLKHF_EXTENDED else 0)
            if code in self.keys and not kb.flags & LLKHF_INJECTED:
                if w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
                    value = 2 if code in self.down else 1
                    self.down.add(code)
                else:
                    value = 0
                    self.down.discard(code)
                self.events.put((code, value))
                if self.swallow:
                    return 1
        return _user32.CallNextHookEx(None, n_code, w_param, l_param)

    def close(self):
        if self.thread_id:
            _user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0)
            self.thread.join(1.0)


class Sounds:
    """The chimes and beeps, played one after another by a worker thread so the
    click loop never waits (SND_MEMORY cannot be combined with SND_ASYNC)."""

    def __init__(self, volume):
        self.volume = volume
        self.wavs = {name: wav(pcm) for name, pcm in chime_pcm(volume).items()}
        self.queue = queue.Queue()
        threading.Thread(target=self._worker, name='sounds', daemon=True).start()

    def play(self, name):
        self.queue.put(self.wavs[name])

    def beep(self, freq):
        """Short beep; dropped if sounds are still waiting (e.g. while a key repeats)."""
        if self.queue.empty():
            self.queue.put(wav(tones((freq,), self.volume, tone=0.05)))

    def close(self):
        self.queue.put(None)

    def _worker(self):
        while (data := self.queue.get()) is not None:
            try:
                winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            except Exception as e:                  # a sound must never stop the clicker
                log(f'could not play a sound: {e}')


class Daemon(BaseDaemon):
    def __init__(self, path):
        super().__init__(path)
        self.events = queue.Queue()                # (code, value) from the hook, or None to wake up
        self.hook = None
        self.notifier = winui.Notifier(log)

    def request_reload(self):
        super().request_reload()
        self.events.put(None)

    def stop(self):
        super().stop()
        self.events.put(None)

    def send_buttons(self, events):
        send_buttons(events)

    def make_sounds(self, volume):
        return Sounds(volume)

    def show_notification(self, text, urgent):
        self.notifier.show('Auto-click', text)

    def reopen(self):
        if self.config.device != 'auto':
            log('the "device" setting is only used on Linux; keys are read from every keyboard')
        if self.hook is not None:
            self.hook.down.clear()
            self.hook.keys, self.hook.swallow = frozenset(self.config.keys), self.config.swallow

    def loop(self):
        winmm = ctypes.WinDLL('winmm')
        winmm.timeBeginPeriod(1)                   # 1 ms timer: steady clicks, not 15.6 ms steps
        try:
            self.hook = KeyboardHook(self.events)
            self.reopen()
            while not self.stopping:
                if self.reload_wanted:
                    self.reload()
                timeout = self.click_due(time.monotonic())
                try:
                    item = self.events.get(timeout=timeout)
                except queue.Empty:
                    continue
                while item is not None:
                    self.key_event(*item, time.monotonic())
                    try:
                        item = self.events.get_nowait()
                    except queue.Empty:
                        break
        finally:
            self.release_all()
            if self.hook is not None:
                self.hook.close()
            if self.sounds is not None:
                self.sounds.close()
            winmm.timeEndPeriod(1)

    def run(self):
        self.reload()                  # here, so a broken settings file stops the program with its error
        winui.run('valkyrie autoclick', self.loop, self.stop, self.request_reload, self.notifier)
