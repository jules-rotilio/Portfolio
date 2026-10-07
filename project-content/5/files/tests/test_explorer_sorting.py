"""Tests that Explorer sorts sizes and dates by value, not by their display text."""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication

from media_toolkit.core.database import MediaDatabase
from media_toolkit.ui.filter_model import natural_key
from media_toolkit.ui.main_window import MainWindow
from test_background import dispose, wait_until

NAME, SIZE, DATE = 0, 1, 3


class ExplorerSortingTests(unittest.TestCase):
    """Size, date, and name columns sort like a file manager."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        root = Path(temporary_directory.name)
        self.folder = root / "media"
        self.folder.mkdir()
        # Sizes whose display texts sort the wrong way round as strings:
        # "989,77 KiB" > "9,93 MiB" alphabetically.
        files = {
            "small.jpg": (1_013_524, datetime(2026, 8, 31, 12, 0)),
            "large.jpg": (10_412_360, datetime(2026, 9, 1, 12, 0)),
            "file10.jpg": (5_000, datetime(2026, 1, 5, 12, 0)),
            "File2.jpg": (6_000, datetime(2025, 12, 30, 12, 0)),
        }
        for name, (size, modified) in files.items():
            path = self.folder / name
            with path.open("wb") as handle:
                handle.truncate(size)
            os.utime(path, (modified.timestamp(), modified.timestamp()))
        (self.folder / "Albums").mkdir()
        database = MediaDatabase(root / "catalog.sqlite3")
        self.addCleanup(database.close)
        settings = QSettings(str(root / "settings.ini"), QSettings.Format.IniFormat)
        with patch.object(MainWindow, "_load_startup_directory"):
            window = MainWindow(database, settings)
        self.addCleanup(dispose, window)
        self.explorer = window.explorer_tab
        self.explorer.load_folder(self.folder)
        wait_until(lambda: len(self.names()) == 5)

    def names(self) -> list[str]:
        """Return the file list's names in their displayed order."""
        model = self.explorer.filter_model
        root = self.explorer.file_view.rootIndex()
        return [model.index(row, NAME, root).data() for row in range(model.rowCount(root))]

    def sort(self, column: int, order: Qt.SortOrder) -> list[str]:
        """Sort the list as a header click would and return the names."""
        self.explorer.file_view.sortByColumn(column, order)
        return self.names()

    def test_sorts_sizes_by_bytes(self) -> None:
        self.assertEqual(
            self.sort(SIZE, Qt.SortOrder.AscendingOrder),
            ["Albums", "file10.jpg", "File2.jpg", "small.jpg", "large.jpg"],
        )
        self.assertEqual(
            self.sort(SIZE, Qt.SortOrder.DescendingOrder),
            ["Albums", "large.jpg", "small.jpg", "File2.jpg", "file10.jpg"],
        )

    def test_sorts_dates_chronologically(self) -> None:
        self.assertEqual(
            self.sort(DATE, Qt.SortOrder.AscendingOrder),
            ["Albums", "File2.jpg", "file10.jpg", "small.jpg", "large.jpg"],
        )
        self.assertEqual(
            self.sort(DATE, Qt.SortOrder.DescendingOrder),
            ["Albums", "large.jpg", "small.jpg", "file10.jpg", "File2.jpg"],
        )

    def test_sorts_names_naturally_and_ignores_case(self) -> None:
        self.assertEqual(
            self.sort(NAME, Qt.SortOrder.AscendingOrder),
            ["Albums", "File2.jpg", "file10.jpg", "large.jpg", "small.jpg"],
        )
        self.assertEqual(
            self.sort(NAME, Qt.SortOrder.DescendingOrder),
            ["Albums", "small.jpg", "large.jpg", "file10.jpg", "File2.jpg"],
        )


class NaturalKeyTests(unittest.TestCase):
    """Names order by numbers and letters, ignoring case and accents."""

    def test_orders_numbers_case_and_accents_like_a_file_manager(self) -> None:
        names = ["file10.jpg", "zebra.jpg", "École.jpg", "File2.jpg", "ecole.jpg", "img_1.jpg", "img_01.jpg"]
        self.assertEqual(
            sorted(names, key=natural_key),
            ["ecole.jpg", "École.jpg", "File2.jpg", "file10.jpg", "img_01.jpg", "img_1.jpg", "zebra.jpg"],
        )


if __name__ == "__main__":
    unittest.main()
