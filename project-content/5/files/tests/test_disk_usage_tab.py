"""Tests that the Disk Usage tab scans in the background and builds rows lazily."""

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import QApplication

from media_toolkit.ui.disk_usage_tab import DiskUsageTab
from media_toolkit.core.filesystem import build_disk_usage_tree
from test_background import wait_until


class DiskUsageTabTests(unittest.TestCase):
    """The scan runs off the UI thread and a newer scan replaces an older one."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.folder = Path(self.temporary_directory.name)
        for index in range(3):
            nested = self.folder / f"dir{index}" / "deeper"
            nested.mkdir(parents=True)
            (nested / "file.bin").write_bytes(b"x" * (index + 1))
        self.tab = DiskUsageTab()
        self.messages: list[str] = []
        self.tab.status_message.connect(self.messages.append)

    def tearDown(self) -> None:
        self.tab.stop_background_work()
        QThreadPool.globalInstance().waitForDone()
        QApplication.processEvents()
        self.tab.close()
        self.temporary_directory.cleanup()

    def test_scans_in_background_and_adds_rows_on_expansion(self) -> None:
        release = threading.Event()

        def slow_scan(folder, should_cancel):
            release.wait(5)
            return build_disk_usage_tree(folder, should_cancel)

        self.tab.set_folder(self.folder)
        with patch("media_toolkit.ui.disk_usage_tab.build_disk_usage_tree", side_effect=slow_scan):
            started = time.monotonic()
            self.tab.refresh()
            self.assertLess(time.monotonic() - started, 0.2)
            self.assertTrue(self.tab.is_scanning())
            self.assertTrue(self.tab.tree.topLevelItem(0).text(0).startswith("Scanning"))
            release.set()
            wait_until(lambda: not self.tab.is_scanning())

        root = self.tab.tree.topLevelItem(0)
        self.assertEqual(root.childCount(), 3)
        first_level = root.child(0)
        self.assertTrue(first_level.isExpanded())
        deeper = first_level.child(0)
        # Rows below the expanded levels are created only when expanded.
        self.assertEqual(deeper.childCount(), 0)
        deeper.setExpanded(True)
        self.assertEqual(deeper.childCount(), 1)
        self.assertIn("6 B used by 3 files", self.messages[-1].replace(".0", ""))

    def test_new_scan_cancels_the_previous_one(self) -> None:
        first_cancelled = threading.Event()
        calls: list[Path] = []

        def scan(folder, should_cancel):
            calls.append(folder)
            if len(calls) == 1:
                while not should_cancel():
                    time.sleep(0.01)
                first_cancelled.set()
                raise RuntimeError("stale scan should be dropped")
            return build_disk_usage_tree(folder, should_cancel)

        self.tab.set_folder(self.folder / "dir0")
        with patch("media_toolkit.ui.disk_usage_tab.build_disk_usage_tree", side_effect=scan):
            self.tab.refresh()
            wait_until(lambda: len(calls) == 1)
            self.tab.set_folder(self.folder / "dir1")
            self.tab.refresh()
            wait_until(lambda: not self.tab.is_scanning())
        self.assertTrue(first_cancelled.wait(5))
        self.assertEqual(self.tab.tree.topLevelItem(0).text(0), "dir1")


if __name__ == "__main__":
    unittest.main()
