"""Application startup: logging, the app-data catalog, and the main window."""

from __future__ import annotations

import logging
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import NamedTemporaryFile
from types import TracebackType

from PySide6.QtCore import QStandardPaths
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from media_toolkit.app_settings import load_settings, open_settings
from media_toolkit.core.database import MediaDatabase
from media_toolkit.logging_setup import (
    configure_session_logging,
    install_qt_message_handler,
    shutdown_session_logging,
)
from media_toolkit.ui.main_window import MainWindow


APPLICATION_NAME = "MediaToolkit"
APP_ID = "media-toolkit"
APP_ICON_PATH = Path(__file__).resolve().parent / "ui" / "icons" / "app-icon.png"
LOGGER = logging.getLogger(__name__)


def _application_database_path(
    previous_data_directory: Path | None = None,
) -> Path:
    """Set the Qt app identity and preserve any database from the old app name."""
    app = QApplication.instance()
    if app is None:
        raise RuntimeError(
            "A QApplication must exist before opening the media database."
        )

    if previous_data_directory is None:
        previous_data_directory = Path(
            QStandardPaths.writableLocation(
                QStandardPaths.StandardLocation.AppDataLocation
            )
        )
    app.setApplicationName(APPLICATION_NAME)
    data_directory = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    )
    database_path = data_directory / "media-toolkit.sqlite3"
    legacy_database_path = previous_data_directory / "media-toolkit.sqlite3"
    if (
        previous_data_directory.name == "main.py"
        and previous_data_directory != data_directory
        and legacy_database_path.is_file()
        and not database_path.exists()
    ):
        LOGGER.info(
            "Migrating application database from %s to %s",
            legacy_database_path,
            database_path,
        )
        data_directory.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            dir=data_directory,
            prefix=".media-toolkit-",
            suffix=".sqlite3",
            delete=False,
        ) as temporary_database:
            migration_path = Path(temporary_database.name)
        try:
            with (
                closing(sqlite3.connect(legacy_database_path, timeout=15)) as source,
                closing(sqlite3.connect(migration_path, timeout=15)) as destination,
            ):
                source.backup(destination)
            if not database_path.exists():
                migration_path.replace(database_path)
        finally:
            migration_path.unlink(missing_ok=True)
    return database_path


def run() -> int:
    """Create the Qt application and enter its event loop."""
    app = QApplication(sys.argv)
    # The icon is used for the title bar and taskbar of every window. On
    # Wayland, the desktop file name becomes the app ID that the taskbar
    # groups windows by; without it Plasma sees "python3".
    app.setWindowIcon(QIcon(str(APP_ICON_PATH)))
    app.setDesktopFileName(APP_ID)
    previous_data_directory = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    )
    app.setApplicationName(APPLICATION_NAME)
    data_directory = Path(
        QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    )
    preferences = load_settings(open_settings())
    log_path = configure_session_logging(
        data_directory, max_log_files=preferences.log_files_kept
    )
    install_qt_message_handler()
    LOGGER.info("MediaToolkit startup; log file: %s", log_path)
    LOGGER.info("Application data directory: %s", data_directory)
    previous_excepthook = sys.excepthook

    def log_uncaught_exception(
        exception_type: type[BaseException],
        exception: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        """Record uncaught main-thread errors before delegating to Python."""
        LOGGER.critical(
            "Uncaught exception",
            exc_info=(exception_type, exception, traceback),
        )
        previous_excepthook(exception_type, exception, traceback)

    sys.excepthook = log_uncaught_exception
    try:
        database_path = _application_database_path(previous_data_directory)
        with MediaDatabase(database_path) as database:
            window = MainWindow(database)
            LOGGER.info("Main window initialized")
            window.show()
            LOGGER.info("Main window shown")
            exit_code = app.exec()
    except Exception:
        LOGGER.exception("Unhandled application failure")
        raise
    finally:
        sys.excepthook = previous_excepthook
        LOGGER.info("MediaToolkit shutdown")
        shutdown_session_logging()
    return exit_code
