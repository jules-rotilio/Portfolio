"""Tests for stopping indexing and processing, and closing the window cleanly."""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QMessageBox

from media_toolkit.ui.main_window import MainWindow
from media_toolkit.core.database import MediaDatabase, MediaRecord
from media_toolkit.media.ffmpeg_tools import ProcessingCancelled, run_cancellable
from media_toolkit.ui.index_worker import IndexWorker
from test_background import dispose
from media_toolkit.processing.workflow import run_workflow


def slow_index(path: Path, root: Path, _cached: MediaRecord | None) -> MediaRecord:
    """Return a minimal record after a short delay, like a real file would take."""
    time.sleep(0.05)
    return MediaRecord(str(path), str(root), 1, 1, path.name, None, "image", {})


class _WaitForInterruption(QThread):
    """Stand-in for a processing worker that runs until asked to stop."""

    completed = Signal(str)

    def run(self) -> None:
        while not self.isInterruptionRequested():
            time.sleep(0.01)


class ShutdownAndCancelTests(unittest.TestCase):
    """Background work stops promptly and keeps what it already finished."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.media = self.root / "media"
        self.media.mkdir()
        for number in range(80):
            (self.media / f"image-{number:02d}.png").touch()
        self.database_path = self.root / "catalog.sqlite3"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_interrupted_indexing_stops_early_and_keeps_saved_records(self) -> None:
        worker = IndexWorker(self.media, self.database_path)
        with patch("media_toolkit.ui.index_worker.index_media_file", side_effect=slow_index):
            worker.start()
            time.sleep(0.15)
            worker.requestInterruption()
            self.assertTrue(worker.wait(5000))

        with MediaDatabase(self.database_path) as database:
            saved = database.cached_records(sorted(self.media.iterdir()))
        self.assertGreater(len(saved), 0)
        self.assertLess(len(saved), 80)

    def open_window(self) -> MainWindow:
        """Create a main window on a catalog that is closed after the test."""
        database = MediaDatabase(self.database_path)
        self.addCleanup(database.close)
        with patch.object(MainWindow, "_load_startup_directory"):
            window = MainWindow(database)
        self.addCleanup(dispose, window)
        return window

    def test_closing_window_stops_indexing_without_asking(self) -> None:
        window = self.open_window()
        window.explorer_tab.load_folder(self.media)
        with (
            patch("media_toolkit.ui.index_worker.index_media_file", side_effect=slow_index),
            patch("media_toolkit.ui.main_window.QMessageBox.question") as question,
        ):
            window.explorer_tab.start_indexing()
            time.sleep(0.1)
            started = time.monotonic()
            self.assertTrue(window.close())
            question.assert_not_called()
        self.assertFalse(window.explorer_tab.is_indexing())
        self.assertLess(time.monotonic() - started, 2)

    def test_closing_during_processing_asks_and_can_be_declined(self) -> None:
        window = self.open_window()
        worker = _WaitForInterruption()
        worker.completed.connect(lambda _message: None)
        window.quick_process_widget.worker = worker  # type: ignore[assignment]
        worker.start()
        try:
            no = QMessageBox.StandardButton.No
            with patch("media_toolkit.ui.main_window.QMessageBox.question", return_value=no):
                self.assertFalse(window.close())
            self.assertTrue(worker.isRunning())

            yes = QMessageBox.StandardButton.Yes
            with patch("media_toolkit.ui.main_window.QMessageBox.question", return_value=yes):
                self.assertTrue(window.close())
            self.assertFalse(worker.isRunning())
        finally:
            worker.requestInterruption()
            worker.wait()

    def test_cancelled_workflow_skips_remaining_inputs(self) -> None:
        inputs = [self.root / "a.mp4", self.root / "b.mp4"]
        for path in inputs:
            path.touch()
        steps = [{"operation": "Trim", "start": "0", "duration": "1"}]
        with patch("media_toolkit.processing.workflow.find_tool", return_value="ffmpeg"):
            outcomes = run_workflow(inputs, self.root / "out", steps, should_cancel=lambda: True)
        self.assertEqual(outcomes, ["Cancelled before a.mp4"])

    def test_run_cancellable_kills_on_cancel_and_on_timeout(self) -> None:
        started = time.monotonic()
        with self.assertRaises(ProcessingCancelled):
            run_cancellable(
                ["sleep", "30"],
                timeout=60,
                should_cancel=lambda: time.monotonic() - started > 0.2,
            )
        with self.assertRaises(subprocess.TimeoutExpired):
            run_cancellable(["sleep", "30"], timeout=0.3, should_cancel=lambda: False)
        self.assertLess(time.monotonic() - started, 3)
        result = run_cancellable(
            ["sh", "-c", "echo out; echo err >&2; exit 3"],
            timeout=5,
            should_cancel=lambda: False,
        )
        self.assertEqual((result.returncode, result.stdout, result.stderr), (3, "out\n", "err\n"))


if __name__ == "__main__":
    unittest.main()
