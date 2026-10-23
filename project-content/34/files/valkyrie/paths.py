"""Where valkyrie keeps its files, on Linux and on Windows.

            Linux                               Windows
config      ~/.config/valkyrie                  %APPDATA%\\valkyrie
backups     ~/.local/share/valkyrie/backups     %LOCALAPPDATA%\\valkyrie\\backups
run files   $XDG_RUNTIME_DIR (or /tmp)          %TEMP%

VALKYRIE_CONFIG_DIR overrides the config folder on both (the tests use it).
"""
import os
import sys
import tempfile

WINDOWS = sys.platform == 'win32'
LINUX = sys.platform.startswith('linux')


def _windows_dir(var, fallback):
    return os.environ.get(var) or os.path.join(os.path.expanduser('~'), fallback)


def config_dir():
    if os.environ.get('VALKYRIE_CONFIG_DIR'):
        return os.environ['VALKYRIE_CONFIG_DIR']
    if WINDOWS:
        return os.path.join(_windows_dir('APPDATA', r'AppData\Roaming'), 'valkyrie')
    return os.path.expanduser('~/.config/valkyrie')


def backup_dir():
    if WINDOWS:
        return os.path.join(_windows_dir('LOCALAPPDATA', r'AppData\Local'), 'valkyrie', 'backups')
    return os.path.expanduser('~/.local/share/valkyrie/backups')


def run_dir():
    if WINDOWS:
        return tempfile.gettempdir()
    return os.environ.get('XDG_RUNTIME_DIR', '/tmp')
