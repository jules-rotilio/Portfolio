"""Regression tests for the application database path migration logic.
"""

import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_toolkit.app import APP_ICON_PATH, _application_database_path


class ApplicationDataTests(unittest.TestCase):
    """Ensures legacy app data locations migrate to the current app name."""
    def test_migrates_database_from_main_py_directory(self) -> None:
        app = _FakeApplication()
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            old_directory = root / "main.py"
            new_directory = root / "MediaToolkit"
            old_directory.mkdir()
            legacy_database = old_directory / "media-toolkit.sqlite3"
            with closing(sqlite3.connect(legacy_database)) as connection, connection:
                connection.execute("CREATE TABLE preserved (value TEXT)")
                connection.execute("INSERT INTO preserved VALUES ('catalog')")

            def writable_location(_standard_location: object) -> str:
                directory = (
                    old_directory
                    if app.applicationName() == "main.py"
                    else new_directory
                )
                return str(directory)

            with (
                patch("media_toolkit.app.QApplication.instance", return_value=app),
                patch(
                    "media_toolkit.app.QStandardPaths.writableLocation",
                    side_effect=writable_location,
                ),
            ):
                database_path = _application_database_path()

            self.assertEqual(
                database_path, new_directory / "media-toolkit.sqlite3"
            )
            with closing(sqlite3.connect(database_path)) as connection, connection:
                self.assertEqual(
                    connection.execute("SELECT value FROM preserved").fetchone(),
                    ("catalog",),
                )


class _FakeApplication:
    """Minimal application stub for testing writable path selection."""
    def __init__(self) -> None:
        self._application_name = "main.py"

    def applicationName(self) -> str:
        return self._application_name

    def setApplicationName(self, name: str) -> None:
        self._application_name = name


class AppIconTests(unittest.TestCase):
    """The bundled app icon loads at the sizes desktops ask for."""

    def test_app_icon_is_a_square_image_with_transparency(self) -> None:
        from PySide6.QtGui import QImage

        image = QImage(str(APP_ICON_PATH))
        self.assertFalse(image.isNull())
        self.assertEqual(image.width(), image.height())
        self.assertGreaterEqual(image.width(), 256)
        self.assertTrue(image.hasAlphaChannel())


if __name__ == "__main__":
    unittest.main()
