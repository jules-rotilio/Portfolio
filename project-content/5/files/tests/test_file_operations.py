"""Tests for file creation, move, copy, rename, and trash helpers.
"""

import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from media_toolkit.core.file_operations import (
    copy_random_media,
    create_folder,
    move_to_trash,
    paste_path,
    rename_files_with_guids,
    rename_path,
)


class FileOperationTests(unittest.TestCase):
    """Verifies safe file and folder operations used by the app."""
    def test_creates_and_renames_items(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            parent = Path(temporary_directory)
            folder = create_folder(parent, "New folder")
            source = folder / "old.txt"
            source.write_text("content")

            renamed = rename_path(source, "new.txt")

            self.assertEqual(renamed.read_text(), "content")
            self.assertTrue(folder.is_dir())

    def test_copies_file_and_folder_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.txt"
            source.write_text("content")
            destination = root / "destination"
            destination.mkdir()

            copied = paste_path(source, destination, move=False)
            self.assertEqual(copied.read_text(), "content")
            with self.assertRaises(FileExistsError):
                paste_path(source, destination, move=False)
            self.assertTrue(source.exists())

            source_folder = root / "folder"
            source_folder.mkdir()
            (source_folder / "inside.txt").write_text("inside")
            copied_folder = paste_path(source_folder, destination, move=False)
            self.assertEqual(
                (copied_folder / "inside.txt").read_text(),
                "inside",
            )

    def test_moves_file_and_prevents_moving_folder_into_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            destination = root / "destination"
            destination.mkdir()
            source = root / "source.txt"
            source.write_text("content")

            moved = paste_path(source, destination, move=True)
            self.assertTrue(moved.exists())
            self.assertFalse(source.exists())

            folder = root / "folder"
            child = folder / "child"
            child.mkdir(parents=True)
            with self.assertRaises(ValueError):
                paste_path(folder, child, move=False)

    def test_rejects_invalid_new_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            with self.assertRaises(ValueError):
                create_folder(root, "../outside")

    def test_copies_random_matching_media_into_new_tmp_folder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            nested = root / "nested"
            nested.mkdir()
            (root / "top.mp4").write_text("video")
            (nested / "photo.JPG").write_text("image")
            (nested / "document.txt").write_text("text")
            destination_name = f"media-toolkit-test-{uuid.uuid4()}"

            destination, copied = copy_random_media(
                root,
                10,
                {".mp4", ".jpg"},
                destination_name,
            )
            try:
                self.assertEqual(destination, Path(tempfile.gettempdir()) / destination_name)
                self.assertEqual(len(copied), 2)
                self.assertEqual(
                    {path.suffix.lower() for path in copied},
                    {".mp4", ".jpg"},
                )
                self.assertTrue(all(path.is_file() for path in copied))
                self.assertTrue((root / "top.mp4").exists())
            finally:
                for path in copied:
                    path.unlink()
                destination.rmdir()

    def test_copy_random_media_rejects_existing_tmp_destination(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "video.mp4").write_text("video")
            destination_name = f"media-toolkit-test-{uuid.uuid4()}"
            destination = Path(tempfile.gettempdir()) / destination_name
            destination.mkdir()
            try:
                with self.assertRaises(FileExistsError):
                    copy_random_media(root, 1, {".mp4"}, destination_name)
            finally:
                destination.rmdir()

    def test_renames_immediate_files_to_guids_and_preserves_extensions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            (root / "first file.mp4").write_text("one")
            (root / "second.JPG").write_text("two")
            (root / "child").mkdir()
            (root / "child" / "nested.txt").write_text("nested")

            renamed = rename_files_with_guids(root)

            self.assertEqual(len(renamed), 2)
            self.assertEqual(
                {destination.suffix for _, destination in renamed},
                {".mp4", ".JPG"},
            )
            self.assertTrue(all(destination.exists() for _, destination in renamed))
            self.assertTrue(all(not source.exists() for source, _ in renamed))
            self.assertTrue((root / "child" / "nested.txt").exists())

    def test_trash_operation_uses_system_trash(self) -> None:
        path = Path("/tmp/example.txt")
        with patch("media_toolkit.core.file_operations.send2trash") as trash:
            move_to_trash(path)
        trash.assert_called_once_with(str(path))


if __name__ == "__main__":
    unittest.main()
