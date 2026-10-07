"""Configure one timestamped application log file per launch."""

from __future__ import annotations

import logging
import os
import re
import sys
import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QMessageLogContext, QtMsgType, qInstallMessageHandler

LOGGER = logging.getLogger(__name__)

LOG_FORMAT = "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
# Newest session logs kept on each launch, including the new one.
DEFAULT_MAX_LOG_FILES = 20
# Set to DEBUG (or WARNING, ...) to change MediaToolkit's own log detail.
LOG_LEVEL_ENVIRONMENT_VARIABLE = "MEDIA_TOOLKIT_LOG_LEVEL"
# Only files with this generated name are ever pruned from the logs directory.
_SESSION_LOG_NAME = re.compile(r"^\d{4}-\d\d-\d\d_\d\d-\d\d-\d\d_\d{6}\.log$")
_QT_LEVELS = {
    QtMsgType.QtDebugMsg: logging.DEBUG,
    QtMsgType.QtInfoMsg: logging.INFO,
    QtMsgType.QtWarningMsg: logging.WARNING,
    QtMsgType.QtCriticalMsg: logging.ERROR,
    QtMsgType.QtFatalMsg: logging.CRITICAL,
}

_session_handler: logging.Handler | None = None


def configure_session_logging(
    data_directory: Path, *, max_log_files: int = DEFAULT_MAX_LOG_FILES
) -> Path:
    """Create a launch-specific log file below the app data directory.

    MediaToolkit records are written at INFO, or at the level named by
    MEDIA_TOOLKIT_LOG_LEVEL; warnings from libraries and Python's warnings
    module are written too. Older session logs beyond max_log_files are removed.
    """
    global _session_handler

    logs_directory = data_directory / "logs"
    logs_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().astimezone().strftime("%Y-%m-%d_%H-%M-%S_%f")
    log_path = logs_directory / f"{timestamp}.log"

    shutdown_session_logging()
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
    # The root handler also receives library warnings (root stays at WARNING).
    logging.getLogger().addHandler(handler)
    _session_handler = handler
    logging.captureWarnings(True)

    application_logger = logging.getLogger("media_toolkit")
    application_logger.propagate = True
    level_name = os.environ.get(LOG_LEVEL_ENVIRONMENT_VARIABLE, "INFO").upper()
    level = logging.getLevelName(level_name)
    application_logger.setLevel(level if isinstance(level, int) else logging.INFO)
    if not isinstance(level, int):
        LOGGER.warning(
            "Ignoring unknown %s=%s; using INFO",
            LOG_LEVEL_ENVIRONMENT_VARIABLE,
            level_name,
        )

    _prune_session_logs(logs_directory, keep=max_log_files, current=log_path)
    return log_path


def shutdown_session_logging() -> None:
    """Detach and close the current session's log file, if any."""
    global _session_handler

    if _session_handler is None:
        return
    logging.getLogger().removeHandler(_session_handler)
    _session_handler.close()
    _session_handler = None


def _prune_session_logs(directory: Path, *, keep: int, current: Path) -> None:
    """Delete the oldest generated session logs so at most keep remain."""
    try:
        session_logs = sorted(
            path
            for path in directory.iterdir()
            if _SESSION_LOG_NAME.match(path.name) and path.is_file()
        )
    except OSError:
        LOGGER.warning("Could not list old log files in %s", directory, exc_info=True)
        return
    # Timestamped names sort chronologically; never delete the new log.
    excess = max(0, len(session_logs) - keep)
    stale = [path for path in session_logs if path != current][:excess]
    removed = 0
    for path in stale:
        try:
            path.unlink()
        except OSError:
            LOGGER.warning("Could not remove old log file %s", path, exc_info=True)
        else:
            removed += 1
    if removed:
        LOGGER.info("Removed %d old log file(s) from %s", removed, directory)


def name_current_thread(name: str) -> None:
    """Label log records from a Qt-created thread, which Python calls Dummy-N.

    The main thread keeps its name, e.g. when a worker's run() is called
    directly instead of through start().
    """
    thread = threading.current_thread()
    if thread is not threading.main_thread():
        thread.name = name


def install_qt_message_handler() -> None:
    """Route Qt's own warnings into the log while still printing them as before."""
    qt_logger = logging.getLogger("qt")
    previous_handler = None

    def handle(
        message_type: QtMsgType, context: QMessageLogContext, message: str
    ) -> None:
        category = context.category
        text = f"{category}: {message}" if category and category != "default" else message
        qt_logger.log(_QT_LEVELS.get(message_type, logging.WARNING), "%s", text)
        if previous_handler is not None:
            previous_handler(message_type, context, message)
        else:
            print(text, file=sys.stderr)

    previous_handler = qInstallMessageHandler(handle)
