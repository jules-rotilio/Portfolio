"""Tests for delivering background-call results on the Qt thread."""

import os
import threading
import time
import unittest
from collections.abc import Callable

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, QThreadPool
from PySide6.QtWidgets import QApplication, QWidget

from media_toolkit.ui.background import BackgroundCalls


def wait_until(condition: Callable[[], bool], timeout: float = 5) -> None:
    """Process Qt events until condition holds or fail after timeout."""
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("Timed out waiting for background result")
        QApplication.processEvents()
        time.sleep(0.01)


def dispose(widget: QWidget) -> None:
    """Close and destroy a window now, so its signals cannot fire in later tests."""
    widget.close()
    widget.deleteLater()
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class BackgroundCallsTests(unittest.TestCase):
    """Verify ordering, superseding, and error delivery."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.calls = BackgroundCalls()

    def tearDown(self) -> None:
        QThreadPool.globalInstance().waitForDone()
        QApplication.processEvents()

    def test_delivers_result_on_the_owning_thread(self) -> None:
        results: list[tuple[str, int]] = []
        worker_threads: list[int] = []

        def work() -> str:
            worker_threads.append(threading.get_ident())
            return "done"

        self.calls.submit(
            "key", work, lambda result: results.append((result, threading.get_ident()))
        )
        wait_until(lambda: bool(results))

        self.assertEqual(results, [("done", threading.get_ident())])
        self.assertNotEqual(worker_threads, [threading.get_ident()])

    def test_drops_superseded_result(self) -> None:
        results: list[str] = []

        def slow() -> str:
            time.sleep(0.2)
            return "old"

        self.calls.submit("key", slow, results.append)
        self.calls.submit("key", lambda: "new", results.append)
        wait_until(lambda: bool(results))
        QThreadPool.globalInstance().waitForDone()
        QApplication.processEvents()

        self.assertEqual(results, ["new"])

    def test_skips_superseded_work_that_has_not_started(self) -> None:
        pool = QThreadPool.globalInstance()
        previous_max = pool.maxThreadCount()
        pool.setMaxThreadCount(1)
        try:
            release = threading.Event()
            ran: list[str] = []
            results: list[str] = []
            self.calls.submit("blocker", lambda: release.wait(5), lambda _: None)
            self.calls.submit("key", lambda: ran.append("stale"), results.append)
            self.calls.submit("key", lambda: "fresh", results.append)
            release.set()
            wait_until(lambda: bool(results))
        finally:
            pool.waitForDone()
            pool.setMaxThreadCount(previous_max)

        self.assertEqual(ran, [])
        self.assertEqual(results, ["fresh"])

    def test_delivers_errors_and_honours_cancel(self) -> None:
        errors: list[Exception] = []
        cancelled: list[str] = []

        def fail() -> None:
            raise RuntimeError("probe failed")

        self.calls.submit("error", fail, lambda _: None, errors.append)
        self.calls.submit("cancelled", lambda: "late", cancelled.append)
        self.calls.cancel("cancelled")
        wait_until(lambda: bool(errors))
        QThreadPool.globalInstance().waitForDone()
        QApplication.processEvents()

        self.assertEqual([str(error) for error in errors], ["probe failed"])
        self.assertEqual(cancelled, [])


if __name__ == "__main__":
    unittest.main()
