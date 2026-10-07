"""Tests that previews and Quick Process probe media without blocking the UI."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from media_toolkit.ui.main_window import MainWindow
from media_toolkit.core.database import MediaDatabase
from media_toolkit.ui.preview import MediaPreviewWidget
from media_toolkit.ui.quick_process_tab import QuickProcessWidget
from test_background import dispose, wait_until


def slow(result: object, delay: float = 0.5):
    """Return a fake probe that sleeps before returning result."""

    def probe(*_args: object) -> object:
        time.sleep(delay)
        return result

    return probe


class NonBlockingPreviewTests(unittest.TestCase):
    """Slow ffprobe/FFmpeg work must not run on the UI thread."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        QThreadPool.globalInstance().waitForDone()
        QApplication.processEvents()

    def test_preview_shows_unindexed_details_and_poster_asynchronously(self) -> None:
        preview = MediaPreviewWidget()
        with (
            patch("media_toolkit.ui.preview.probe_media", side_effect=slow(["Format: test"])),
            patch(
                "media_toolkit.ui.preview.extract_video_poster",
                side_effect=RuntimeError("Video thumbnail is not available"),
            ),
        ):
            started = time.monotonic()
            preview.show_file(Path("/nonexistent/clip.mp4"))
            self.assertLess(time.monotonic() - started, 0.3)
            self.assertEqual(preview.details.text(), "Reading media details…")

            # The fake path also yields a "Playback error" line after the details.
            wait_until(lambda: preview.details.text().startswith("Format: test"))
            self.assertEqual(
                preview.video_poster.text(), "Video thumbnail is not available"
            )
        preview.close()

    def test_preview_ignores_details_of_a_previous_selection(self) -> None:
        preview = MediaPreviewWidget()

        def probe(path: Path) -> list[str]:
            if path.name == "first.mp3":
                time.sleep(0.3)
            return [f"Details for {path.name}"]

        with patch("media_toolkit.ui.preview.probe_media", side_effect=probe):
            preview.show_file(Path("/nonexistent/first.mp3"))
            preview.show_file(Path("/nonexistent/second.mp3"))
            wait_until(lambda: preview.details.text().startswith("Details for second.mp3"))
            QThreadPool.globalInstance().waitForDone()
            QApplication.processEvents()

        self.assertEqual(
            preview.details.text().splitlines()[0], "Details for second.mp3"
        )
        preview.close()

    def test_quick_process_enables_run_only_after_source_probe(self) -> None:
        widget = QuickProcessWidget()
        with (
            patch(
                "media_toolkit.ui.quick_process_tab.probe_source",
                side_effect=slow((12.0, (25.0, 640, 360), None)),
            ),
            patch("media_toolkit.ui.preview.extract_video_poster", return_value=b""),
        ):
            started = time.monotonic()
            widget.set_source(Path("/nonexistent/clip.mp4"), {"details": ["Video"]})
            self.assertLess(time.monotonic() - started, 0.3)
            self.assertFalse(widget.run_button.isEnabled())

            wait_until(widget.run_button.isEnabled)
        self.assertEqual(
            (widget.fps.text(), widget.width.text(), widget.height.text()),
            ("25", "640", "360"),
        )
        self.assertEqual(widget._source_duration, 12.0)
        widget.close()

    def test_hidden_quick_process_tab_loads_selection_when_shown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = MediaDatabase(Path(temporary_directory) / "catalog.sqlite3")
            self.addCleanup(database.close)
            with patch.object(MainWindow, "_load_startup_directory"):
                window = MainWindow(database)
            clip = Path(temporary_directory) / "clip.mp4"
            with patch.object(window.quick_process_widget, "set_source") as set_source:
                window._set_quick_process_source(clip, {"details": []})
                set_source.assert_called_once_with(None)

                set_source.reset_mock()
                window.tabs.setCurrentWidget(window.quick_process_widget)
                set_source.assert_called_once_with(clip, {"details": []})

                set_source.reset_mock()
                other = Path(temporary_directory) / "other.mp4"
                window._set_quick_process_source(other)
                set_source.assert_called_once_with(other, None)
            dispose(window)


if __name__ == "__main__":
    unittest.main()
