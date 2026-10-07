"""Tests for non-blocking duplicate-group snapshot generation."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from media_toolkit.ui.main_window import MainWindow
from media_toolkit.ui.duplicates_tab import DuplicateGroupsWorker
from test_background import dispose
from media_toolkit.core.database import MediaDatabase, MediaRecord


class DuplicateGroupsWorkerTests(unittest.TestCase):
    """Verify worker refreshes build one database-wide snapshot."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def test_loads_groups_and_display_records_after_one_match_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            database = MediaDatabase(root / "catalog.sqlite3")
            self.addCleanup(database.close)
            first = root / "first.mp4"
            second = root / "second.mp4"
            database.save_records(
                [
                    MediaRecord(
                        path=str(first),
                        root=str(root),
                        size=11,
                        mtime_ns=1,
                        sha256="same-sha",
                        perceptual_hash=None,
                        media_type="video",
                        metadata={},
                    ),
                    MediaRecord(
                        path=str(second),
                        root=str(root),
                        size=12,
                        mtime_ns=1,
                        sha256="same-sha",
                        perceptual_hash=None,
                        media_type="video",
                        metadata={},
                    ),
                ]
            )
            with (
                patch("media_toolkit.ui.duplicates_tab.MediaDatabase", return_value=database),
                patch.object(
                    database,
                    "duplicate_groups",
                    wraps=database.duplicate_groups,
                ) as duplicate_groups,
                patch.object(
                    database,
                    "cached_records",
                    wraps=database.cached_records,
                ) as cached_records,
            ):
                worker = DuplicateGroupsWorker(database.database_path)
                emitted: list[tuple[object, ...]] = []
                worker.completed.connect(lambda *values: emitted.append(values))
                worker.run()

            duplicate_groups.assert_called_once_with(
            include_dismissed=True, distance=8, min_frames=4
        )
            cached_records.assert_called_once_with([first, second])
            self.assertEqual(len(emitted), 1)
            groups, dismissed, records, result = emitted[0]

        self.assertEqual(len(groups), 1)
        self.assertEqual(dismissed, set())
        self.assertEqual(set(records), {str(first), str(second)})
        self.assertEqual(result, (None, ""))

    def test_main_window_does_not_scan_duplicate_groups_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            database = MediaDatabase(Path(temporary_directory) / "catalog.sqlite3")
            self.addCleanup(database.close)
            with (
                patch.object(database, "duplicate_groups") as duplicate_groups,
                patch.object(MainWindow, "_load_startup_directory"),
            ):
                window = MainWindow(database)

            duplicate_groups.assert_not_called()
            self.assertEqual(window.duplicates_tab.duplicate_paths, set())
            self.assertEqual(window.duplicates_tab.tree.topLevelItemCount(), 0)
            dispose(window)


if __name__ == "__main__":
    unittest.main()
