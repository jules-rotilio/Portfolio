"""Background Qt worker for scanning, indexing, and saving media records."""

from __future__ import annotations

import logging
import os
import sqlite3
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from media_toolkit.core.database import MediaDatabase, MediaRecord
from media_toolkit.core.filesystem import list_media_files
from media_toolkit.media.indexer import index_media_file
from media_toolkit.logging_setup import name_current_thread
from media_toolkit.core.xdg_tags import read_xdg_tags

LOGGER = logging.getLogger(__name__)

# Default files indexed at once (configurable in Settings). Hashing, image
# decoding, and FFmpeg run outside the GIL, so threads scale until the disk or
# CPU is saturated.
INDEX_THREADS = min(8, os.cpu_count() or 1)
# Records saved per database write, so an interrupted scan keeps its progress.
SAVE_BATCH_SIZE = 200


def _index_file(
    path: Path, root: Path, cached: MediaRecord | None
) -> tuple[MediaRecord | None, list[str]]:
    """Index one file and read its XDG tags; return the record and any issues."""
    try:
        record = index_media_file(path, root, cached)
    except (OSError, ValueError) as error:
        LOGGER.exception("Could not index %s", path)
        return None, [f"{path}: {error}"]
    try:
        xdg_tags = read_xdg_tags(path)
    except OSError as error:
        LOGGER.exception("Could not read XDG tags from %s", path)
        return record, [f"Could not read XDG tags from {path}: {error}"]
    if xdg_tags is not None:
        record = replace(record, metadata={**record.metadata, "xdg_tags": sorted(xdg_tags)})
    return record, []


class IndexWorker(QThread):
    """Index a root directory while emitting progress and completion signals.

    Call requestInterruption() to stop early: files not yet started are
    skipped, and every record finished so far is saved.
    """

    progress = Signal(int, str)
    completed = Signal(object, object)

    def __init__(
        self, root: Path, database_path: Path, *, threads: int = INDEX_THREADS
    ) -> None:
        """Configure the scan root, catalog path, and files indexed at once."""
        super().__init__()
        self.root = root
        self.database_path = database_path
        self.threads = max(1, threads)

    def run(self) -> None:
        """Index discovered files in parallel, collect per-file issues, and save."""
        name_current_thread("IndexWorker")
        LOGGER.info("Starting media scan for %s", self.root)
        try:
            paths = list_media_files(self.root)
        except OSError as error:
            LOGGER.exception("Could not scan %s", self.root)
            self.completed.emit([], [f"Could not scan {self.root}: {error}"])
            return
        LOGGER.info("Discovered %d supported media file(s) under %s", len(paths), self.root)
        with MediaDatabase(self.database_path) as database:
            self._index(paths, database)

    def _index(self, paths: list[Path], database: MediaDatabase) -> None:
        """Index paths in parallel, saving records in batches to database."""
        cached = database.cached_records(paths)
        LOGGER.info("Loaded %d cached record(s) for the scan", len(cached))

        records: list[MediaRecord] = []
        unsaved: list[MediaRecord] = []
        errors: list[str] = []
        total = len(paths)
        next_logged_percent = 10
        with ThreadPoolExecutor(
            max_workers=self.threads, thread_name_prefix="IndexFile"
        ) as executor:
            futures: dict[Future[tuple[MediaRecord | None, list[str]]], Path] = {
                executor.submit(_index_file, path, self.root, cached.get(str(path))): path
                for path in paths
            }
            for position, future in enumerate(as_completed(futures), start=1):
                record, file_errors = future.result()
                errors.extend(file_errors)
                if record is not None:
                    records.append(record)
                    unsaved.append(record)
                if len(unsaved) >= SAVE_BATCH_SIZE:
                    self._save(database, unsaved, errors)
                    unsaved = []
                percent = int(position * 100 / total)
                progress_message = f"Indexing {position}/{total}: {futures[future].name}"
                if percent >= next_logged_percent:
                    # Log every 10%; each processed file is logged by the indexer.
                    LOGGER.info("Progress (%d%%): %s", percent, progress_message)
                    next_logged_percent = percent // 10 * 10 + 10
                self.progress.emit(percent, progress_message)
                if self.isInterruptionRequested():
                    # Queued files are dropped; files already being indexed
                    # finish when the pool closes, but are not saved.
                    executor.shutdown(wait=False, cancel_futures=True)
                    LOGGER.info("Media scan stopped after %d of %d file(s)", position, total)
                    break
        self._save(database, unsaved, errors)
        LOGGER.info(
            "Media scan finished: %d record(s) saved, %d issue(s)",
            len(records),
            len(errors),
        )
        self.completed.emit(records, errors)

    @staticmethod
    def _save(
        database: MediaDatabase, records: list[MediaRecord], errors: list[str]
    ) -> None:
        """Write a batch of records, reporting a failure instead of raising."""
        if not records:
            return
        try:
            database.save_records(records)
        except (OSError, sqlite3.Error) as error:
            LOGGER.exception("Could not save indexed media records")
            errors.append(f"Could not save media index: {error}")
