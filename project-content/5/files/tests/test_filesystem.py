"""Tests for recursive media discovery and size-formatting helpers.
"""

import os
import tempfile
import unittest
from pathlib import Path

from media_toolkit.core.filesystem import (
    ScanCancelled,
    build_disk_usage_tree,
    format_size,
    list_media_files,
)


class FilesystemTests(unittest.TestCase):
    """Verifies recursive media discovery and disk-usage formatting."""
    def test_lists_media_recursively_and_case_insensitively(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            nested = folder / "nested"
            nested.mkdir()
            (folder / "cover.JPG").write_bytes(b"image")
            (nested / "clip.MP4").write_bytes(b"video")
            (nested / "notes.txt").write_text("not media")

            self.assertEqual(
                list_media_files(folder),
                [folder / "cover.JPG", nested / "clip.MP4"],
            )

    def test_builds_recursive_disk_usage_totals(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            nested = folder / "nested"
            nested.mkdir()
            (folder / "one.bin").write_bytes(b"123")
            (nested / "two.bin").write_bytes(b"45678")

            tree = build_disk_usage_tree(folder)

            self.assertEqual(tree.size, 8)
            self.assertEqual(tree.files, 2)
            self.assertEqual(tree.directories, 1)
            self.assertEqual(tree.children[0].path, nested)

    def test_rejects_non_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            file_path = Path(temporary_directory) / "file"
            file_path.write_text("content")

            with self.assertRaises(NotADirectoryError):
                list_media_files(file_path)
            with self.assertRaises(NotADirectoryError):
                build_disk_usage_tree(file_path)

    def test_formats_sizes(self) -> None:
        self.assertEqual(format_size(100), "100.0 B")
        self.assertEqual(format_size(1024), "1.0 KB")

    def test_disk_usage_skips_unreadable_folders_and_can_be_cancelled(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            (folder / "readable").mkdir()
            (folder / "readable" / "a.bin").write_bytes(b"12345")
            locked = folder / "locked"
            locked.mkdir()
            (locked / "secret.bin").write_bytes(b"123")
            locked.chmod(0)
            try:
                if os.access(locked, os.R_OK):
                    self.skipTest("running with permissions that ignore chmod")
                tree = build_disk_usage_tree(folder)
            finally:
                locked.chmod(0o755)

            self.assertEqual((tree.size, tree.files, tree.unreadable), (5, 1, 1))
            kinds = {child.path.name: child.kind for child in tree.children}
            self.assertEqual(kinds["locked"], "Unreadable folder")
            with self.assertRaises(ScanCancelled):
                build_disk_usage_tree(folder, should_cancel=lambda: True)


if __name__ == "__main__":
    unittest.main()
