"""What notify-send and the terminal give the daemons on Linux, on Windows: a tray
icon with Reload and Quit, and its pop-up notifications.

run() runs the daemon's loop in a thread and the tray in the main thread (Qt needs
it there). Without PyQt6 the loop runs alone and notifications are only logged.
"""
import signal
import sys
import threading


class Notifier:
    """show(title, body) from any thread; replaced by the tray's while it runs."""

    def __init__(self, log):
        self.log = log
        self.target = None

    def show(self, title, body=''):
        if self.target is not None:
            self.target(title, body)

    def close(self):
        pass


def run(title, loop, stop, reload, notifier):
    """loop(): the daemon, returns when stop() was called. reload(): from the menu."""
    try:
        from PyQt6.QtCore import QObject, QTimer, pyqtSignal
        from PyQt6.QtGui import QAction
        from PyQt6.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon
    except ImportError:
        notifier.log('PyQt6 not found: no tray icon or notifications')
        signal.signal(signal.SIGINT, lambda *_: stop())
        loop()
        return

    class Bridge(QObject):
        message = pyqtSignal(str, str)
        ended = pyqtSignal()

    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    tray = QSystemTrayIcon(app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))
    tray.setToolTip(title)
    menu = QMenu()
    for text, fn in (('Reload settings', reload), ('Quit', stop)):
        action = QAction(text, menu)
        action.triggered.connect(fn)
        menu.addAction(action)
    tray.setContextMenu(menu)
    tray.show()

    bridge = Bridge()
    bridge.message.connect(lambda t, b: tray.showMessage(t, b, QSystemTrayIcon.MessageIcon.Information, 2000))
    bridge.ended.connect(app.quit)
    notifier.target = bridge.message.emit

    def worker():
        try:
            loop()
        finally:
            bridge.ended.emit()

    thread = threading.Thread(target=worker, name='daemon')
    signal.signal(signal.SIGINT, lambda *_: stop())
    ticker = QTimer()                     # lets Python run the Ctrl+C handler while Qt waits
    ticker.timeout.connect(lambda: None)
    ticker.start(200)
    thread.start()
    app.exec()
    stop()
    thread.join()
    tray.hide()
    notifier.target = None
