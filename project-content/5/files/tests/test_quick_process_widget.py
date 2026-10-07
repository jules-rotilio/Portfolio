"""Tests for which Quick Process settings are shown and used."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from media_toolkit.ui.quick_process_tab import QuickProcessWidget
from test_background import wait_until

FPS_ROW = 5
COLORS_ROW = 7


class QuickProcessFormTests(unittest.TestCase):
    """Rows appear only for operations that use them."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.widget = QuickProcessWidget()
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name)

    def tearDown(self) -> None:
        QThreadPool.globalInstance().waitForDone()
        self.widget.close()
        self.temporary_directory.cleanup()

    def load(self, name: str, duration: float) -> None:
        """Select a source whose background probe reports duration."""
        with (
            patch(
                "media_toolkit.ui.quick_process_tab.probe_source",
                return_value=(duration, (25.0, 640, 360), None),
            ),
            patch("media_toolkit.ui.preview.extract_video_poster", return_value=b""),
        ):
            self.widget.set_source(self.folder / name, {"details": []})
            wait_until(self.widget.run_button.isEnabled)

    def visible_rows(self, operation: str) -> tuple[bool, bool]:
        """Return (frame rate shown, GIF colours shown) for operation."""
        self.widget.operation.setCurrentText(operation)
        self.assertEqual(self.widget.operation.currentText(), operation)
        form = self.widget.form
        return form.isRowVisible(FPS_ROW), form.isRowVisible(COLORS_ROW)

    def test_frame_rate_and_colours_follow_the_operation(self) -> None:
        self.load("clip.mp4", 10.0)
        self.assertEqual(self.visible_rows("Convert video to GIF"), (True, True))
        self.assertEqual(self.visible_rows("Convert video to animated WebP"), (True, False))
        self.assertEqual(self.visible_rows("Resize video"), (True, False))
        self.assertEqual(self.visible_rows("Extract audio"), (False, False))

        self.load("song.mp3", 10.0)
        self.assertEqual(self.visible_rows("Convert audio"), (False, False))

        self.load("animated.gif", 2.0)
        self.assertEqual(self.visible_rows("Resize GIF"), (True, False))
        self.assertEqual(self.visible_rows("Trim GIF"), (False, False))
        self.assertEqual(self.visible_rows("Convert GIF to animated WebP"), (True, False))

        self.load("still.gif", 0.0)
        self.assertEqual(self.visible_rows("Resize GIF"), (False, False))

        self.load("animated.webp", 1.0)
        self.assertEqual(self.visible_rows("Convert animated WebP to GIF"), (True, True))

    def test_hidden_time_range_and_split_settings_are_not_applied(self) -> None:
        self.load("clip.mp4", 10.0)
        self.widget.operation.setCurrentText("Convert video to GIF")
        self.widget.split_count.setValue(3)
        self.widget.from_start.setChecked(False)
        self.widget.start.setText("4")
        self.widget.operation.setCurrentText("Resize video")

        with patch("media_toolkit.ui.quick_process_tab._ProcessWorker") as worker_class:
            self.widget._start_processing()

        options = worker_class.call_args.args[3]
        self.assertEqual(options["operation"], "Resize video")
        self.assertEqual(options["split_count"], "1")
        self.assertEqual((options["from_start"], options["to_end"]), ("1", "1"))


if __name__ == "__main__":
    unittest.main()
