"""Tests for listing, paging, and filtering database browser tables.
"""

import os
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from media_toolkit.core.database import MediaDatabase
from media_toolkit.ui.database_browser import DatabaseBrowser


class DatabaseBrowserTests(unittest.TestCase):
    """Covers the database browser UI and table pagination helpers."""
    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "catalog.sqlite3"
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.execute(
                'CREATE TABLE "media""records" (id INTEGER, name TEXT, payload BLOB)'
            )
            connection.executemany(
                'INSERT INTO "media""records" VALUES (?, ?, ?)',
                [(index, f"item-{index}", b"payload") for index in range(105)],
            )
        self.browser = DatabaseBrowser(self.database_path)

    def tearDown(self) -> None:
        self.browser.close()
        self.temporary_directory.cleanup()

    def test_lists_and_reads_tables_with_pagination(self) -> None:
        self.assertEqual(self.browser.table_selector.currentText(), 'media"records')
        self.assertEqual(self.browser.table.rowCount(), 100)
        self.assertEqual(self.browser.table.columnCount(), 3)
        self.assertTrue(self.browser.next_button.isEnabled())
        self.assertEqual(self.browser.table.item(0, 2).text(), "[BLOB: 7 bytes]")

        self.browser._next_page()

        self.assertEqual(self.browser.table.rowCount(), 5)
        self.assertEqual(self.browser.table.item(0, 0).text(), "100")
        self.assertFalse(self.browser.next_button.isEnabled())
        self.assertTrue(self.browser.previous_button.isEnabled())

    def test_filters_rows_and_does_not_modify_database(self) -> None:
        before = self.database_path.read_bytes()
        self.browser.search_input.setText("item-104")
        self.browser._apply_search()

        self.assertEqual(self.browser.table.rowCount(), 1)
        self.assertEqual(self.browser.table.item(0, 1).text(), "item-104")
        self.assertIn("1 of 1 rows", self.browser.status_label.text())
        self.assertEqual(self.database_path.read_bytes(), before)

    def test_reads_write_ahead_logged_catalog_after_writers_close(self) -> None:
        catalog_path = Path(self.temporary_directory.name) / "wal-catalog.sqlite3"
        catalog = MediaDatabase(catalog_path)
        catalog.save_workflow("Short clip", [{"operation": "Trim"}])
        catalog.close()
        self.assertFalse(catalog_path.with_name(catalog_path.name + "-wal").exists())

        browser = DatabaseBrowser(catalog_path)
        try:
            browser.table_selector.setCurrentText("workflows")
            self.assertEqual(browser.table.rowCount(), 1)
            self.assertEqual(browser.table.item(0, 0).text(), "Short clip")
        finally:
            browser.close()


if __name__ == "__main__":
    unittest.main()
