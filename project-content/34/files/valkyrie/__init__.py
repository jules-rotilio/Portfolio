"""Configure the Konix Drakkar Valkyrie mouse (USB 04d9:fc06) on Linux and Windows."""
import sys


def utf8_stdio():
    """Print UTF-8 whatever the locale (Windows consoles default to cp1252/cp850).
    Every file valkyrie reads or writes names encoding='utf-8' itself."""
    for stream in (sys.stdout, sys.stderr):
        encoding = getattr(stream, 'encoding', None)       # None: no stream (pythonw), or a StringIO
        if encoding and encoding.lower().replace('-', '') != 'utf8' and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
