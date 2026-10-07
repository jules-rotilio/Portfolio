"""Tests for per-launch application log creation, retention, and capture."""

import logging
import os
import tempfile
import unittest
import warnings
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import qInstallMessageHandler, qWarning

from media_toolkit.logging_setup import (
    LOG_LEVEL_ENVIRONMENT_VARIABLE,
    configure_session_logging,
    install_qt_message_handler,
    shutdown_session_logging,
)


class SessionLoggingTests(unittest.TestCase):
    """Verify launch logs are created, pruned, and capture the right records."""

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.data_directory = Path(self.temporary_directory.name)
        self.root_handlers = list(logging.getLogger().handlers)

    def tearDown(self) -> None:
        shutdown_session_logging()
        logging.captureWarnings(False)
        logging.getLogger("media_toolkit").setLevel(logging.NOTSET)
        self.assertEqual(logging.getLogger().handlers, self.root_handlers)
        self.temporary_directory.cleanup()

    def configure(self, **kwargs: object) -> Path:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(LOG_LEVEL_ENVIRONMENT_VARIABLE, None)
            os.environ.update({key: str(value) for key, value in kwargs.items()})
            return configure_session_logging(self.data_directory)

    def test_creates_timestamped_log_and_records_application_events(self) -> None:
        log_path = self.configure()
        logging.getLogger("media_toolkit.test").info("test application event")
        shutdown_session_logging()

        self.assertEqual(log_path.parent, self.data_directory / "logs")
        self.assertRegex(log_path.name, r"^\d{4}-\d\d-\d\d_.*\.log$")
        self.assertRegex(
            log_path.read_text(encoding="utf-8"),
            r"INFO \[MainThread\] media_toolkit\.test: test application event",
        )

    def test_keeps_only_the_newest_session_logs(self) -> None:
        logs_directory = self.data_directory / "logs"
        logs_directory.mkdir()
        old_logs = [
            logs_directory / f"2020-01-{day:02d}_10-00-00_000000.log"
            for day in range(1, 26)
        ]
        for path in old_logs:
            path.write_text("old", encoding="utf-8")
        unrelated = [logs_directory / "notes.log", logs_directory / "keep.txt"]
        for path in unrelated:
            path.write_text("mine", encoding="utf-8")

        log_path = configure_session_logging(self.data_directory, max_log_files=5)

        remaining = sorted(path.name for path in logs_directory.glob("20*.log"))
        self.assertEqual(
            remaining, sorted([path.name for path in old_logs[-4:]] + [log_path.name])
        )
        self.assertTrue(all(path.exists() for path in unrelated))
        shutdown_session_logging()
        self.assertIn("Removed 21 old log file(s)", log_path.read_text(encoding="utf-8"))

    def test_captures_library_and_python_warnings_but_not_library_info(self) -> None:
        log_path = self.configure()
        logging.getLogger("PIL.Example").info("library chatter")
        logging.getLogger("PIL.Example").warning("library warning")
        with warnings.catch_warnings():
            warnings.simplefilter("always")
            warnings.warn("python warning", UserWarning)
        logging.getLogger("media_toolkit.test").debug("debug detail")
        shutdown_session_logging()

        text = log_path.read_text(encoding="utf-8")
        self.assertNotIn("library chatter", text)
        self.assertIn("library warning", text)
        self.assertIn("python warning", text)
        self.assertNotIn("debug detail", text)

    def test_log_level_can_be_raised_to_debug_by_environment(self) -> None:
        log_path = self.configure(**{LOG_LEVEL_ENVIRONMENT_VARIABLE: "debug"})
        logging.getLogger("media_toolkit.test").debug("debug detail")
        shutdown_session_logging()

        self.assertIn("debug detail", log_path.read_text(encoding="utf-8"))

    def test_routes_qt_warnings_into_the_log(self) -> None:
        install_qt_message_handler()
        try:
            with (
                self.assertLogs("qt", logging.WARNING) as captured,
                patch("sys.stderr"),
            ):
                qWarning("qt test warning")
        finally:
            qInstallMessageHandler(None)

        self.assertTrue(any("qt test warning" in line for line in captured.output))


if __name__ == "__main__":
    unittest.main()
