"""Tests for background indexing results and log volume."""

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from media_toolkit.core.database import MediaDatabase, MediaRecord
from media_toolkit.ui.index_worker import IndexWorker


def fake_index(path: Path, root: Path, _cached: MediaRecord | None) -> MediaRecord:
    """Return a minimal record without hashing or probing the file."""
    if path.name == "broken.png":
        raise OSError("unreadable")
    return MediaRecord(
        path=str(path),
        root=str(root),
        size=1,
        mtime_ns=1,
        sha256=path.name,
        perceptual_hash=None,
        media_type="image",
        metadata={},
    )


class IndexWorkerTests(unittest.TestCase):
    """Run the worker synchronously and inspect its results and logs."""

    def test_saves_records_reports_issues_and_logs_progress_milestones(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory) / "media"
            root.mkdir()
            for number in range(24):
                (root / f"image-{number:02d}.png").touch()
            (root / "broken.png").touch()
            database_path = Path(temporary_directory) / "catalog.sqlite3"
            worker = IndexWorker(root, database_path)
            completed: list[tuple[list[MediaRecord], list[str]]] = []
            worker.completed.connect(lambda records, errors: completed.append((records, errors)))

            with (
                patch("media_toolkit.ui.index_worker.index_media_file", side_effect=fake_index),
                self.assertLogs("media_toolkit", logging.INFO) as logs,
            ):
                worker.run()

            records, errors = completed[0]
            self.assertEqual(len(records), 24)
            self.assertEqual(errors, [f"{root / 'broken.png'}: unreadable"])
            with MediaDatabase(database_path) as database:
                saved = database.cached_records(sorted(root.iterdir()))
            self.assertEqual(len(saved), 24)
            progress = [line for line in logs.output if "Progress (" in line]
            self.assertEqual(len(progress), 10)
            self.assertIn("Progress (100%)", progress[-1])
            # The failure is logged once where it happens, not again in a summary.
            self.assertEqual(
                sum(
                    line.startswith("ERROR") and "broken.png" in line
                    for line in logs.output
                ),
                1,
            )


if __name__ == "__main__":
    unittest.main()
