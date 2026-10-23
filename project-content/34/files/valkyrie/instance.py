"""A running daemon (valkyrie-monitor, valkyrie-autoclick): whether it runs, and asking
it to read its settings again.

Linux: a pid file in $XDG_RUNTIME_DIR and SIGHUP, as before.
Windows: a named mutex marks the running copy (and keeps a second one from starting)
and a named event asks it to reload. Windows has no SIGHUP, and os.kill() there ends
the process whatever the signal, so pid files are not used.
"""
import os
import signal
import threading

from . import paths


def pidfile(name):
    return os.path.join(paths.run_dir(), f'{name}.pid')


if paths.WINDOWS:
    import ctypes
    from ctypes import wintypes

    _k32 = ctypes.WinDLL('kernel32', use_last_error=True)
    _k32.CreateMutexW.restype = wintypes.HANDLE
    _k32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.OpenMutexW.restype = wintypes.HANDLE
    _k32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.CreateEventW.restype = wintypes.HANDLE
    _k32.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.OpenEventW.restype = wintypes.HANDLE
    _k32.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _k32.SetEvent.argtypes = [wintypes.HANDLE]
    _k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _k32.WaitForSingleObject.restype = wintypes.DWORD
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    SYNCHRONIZE, EVENT_MODIFY_STATE, ERROR_ALREADY_EXISTS, INFINITE = 0x00100000, 0x0002, 183, 0xFFFFFFFF

    def _names(name):
        return f'Local\\{name}', f'Local\\{name}-reload'


class AlreadyRunning(Exception):
    pass


class Instance:
    """The running copy of daemon `name`. on_reload() is called when a reload is
    asked: from the signal handler on Linux, from a helper thread on Windows."""

    def __init__(self, name, on_reload):
        self.name = name
        self.on_reload = on_reload
        self.handles = []
        self.closing = False
        if paths.WINDOWS:
            mutex_name, event_name = _names(name)
            mutex = _k32.CreateMutexW(None, False, mutex_name)
            if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
                _k32.CloseHandle(mutex)
                raise AlreadyRunning(f'{name} is already running')
            self.event = _k32.CreateEventW(None, False, False, event_name)
            self.handles = [mutex, self.event]
            threading.Thread(target=self._wait_reload, name='reload', daemon=True).start()
        else:
            with open(pidfile(name), 'w', encoding='utf-8') as f:
                f.write(str(os.getpid()))
            signal.signal(signal.SIGHUP, lambda *_: on_reload())

    def _wait_reload(self):
        while _k32.WaitForSingleObject(self.event, INFINITE) == 0 and not self.closing:
            self.on_reload()

    def close(self):
        self.closing = True
        if paths.WINDOWS:
            _k32.SetEvent(self.event)                  # ends the reload thread
            for h in self.handles:
                _k32.CloseHandle(h)
        else:
            try:
                os.remove(pidfile(self.name))
            except OSError:
                pass


def running(name):
    """True if daemon `name` runs (for this user)."""
    if paths.WINDOWS:
        h = _k32.OpenMutexW(SYNCHRONIZE, False, _names(name)[0])
        if h:
            _k32.CloseHandle(h)
        return bool(h)
    try:
        with open(pidfile(name), encoding='utf-8') as f:
            os.kill(int(f.read()), 0)
        return True
    except (OSError, ValueError):
        return False


def request_reload(name):
    """Ask daemon `name` to read its settings again. -> False if it is not running."""
    if paths.WINDOWS:
        h = _k32.OpenEventW(EVENT_MODIFY_STATE, False, _names(name)[1])
        if not h:
            return False
        _k32.SetEvent(h)
        _k32.CloseHandle(h)
        return True
    try:
        with open(pidfile(name), encoding='utf-8') as f:
            os.kill(int(f.read()), signal.SIGHUP)
        return True
    except (OSError, ValueError):
        return False
