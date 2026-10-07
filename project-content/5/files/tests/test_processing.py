"""Tests for ffmpeg command generation and processed-output naming.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from media_toolkit.processing.workflow import (
    build_ffmpeg_command,
    processed_output_path,
    reserve_output_path,
    run_workflow,
)


class ProcessingTests(unittest.TestCase):
    """Verifies processing steps are converted into valid ffmpeg commands."""
    def test_builds_trim_resize_and_webp_command_as_argument_list(self) -> None:
        steps = [
            {"operation": "Trim", "start": "1.5", "duration": "4"},
            {"operation": "Resize", "width": "640", "height": "360"},
            {"operation": "Convert format", "format": "Animated WebP"},
        ]
        command = build_ffmpeg_command(
            Path("source file.mp4"),
            Path("out/source_processed.webp"),
            steps,
            "/usr/bin/ffmpeg",
        )
        self.assertEqual(command[0], "/usr/bin/ffmpeg")
        self.assertIn("source file.mp4", command)
        self.assertEqual(command[command.index("-ss") + 1], "1.5")
        self.assertEqual(command[command.index("-t") + 1], "4.0")
        self.assertEqual(command[command.index("-c:v") + 1], "libwebp_anim")
        self.assertEqual(
            command[command.index("-vf") + 1],
            "scale=640:360:force_original_aspect_ratio=decrease:force_divisible_by=2",
        )
        self.assertEqual(command[-1], "out/source_processed.webp")

    def test_preserves_resize_filter_when_creating_gif(self) -> None:
        steps = [
            {"operation": "Resize", "width": "480", "height": "360"},
            {"operation": "Convert format", "format": "GIF"},
        ]
        command = build_ffmpeg_command(
            Path("source.mp4"), Path("output.gif"), steps, "ffmpeg"
        )
        self.assertEqual(
            command[command.index("-vf") + 1],
            "fps=15,scale=480:360:force_original_aspect_ratio=decrease:force_divisible_by=2",
        )

    def test_rejects_invalid_block_order_and_duration(self) -> None:
        with self.assertRaisesRegex(ValueError, "Order blocks"):
            build_ffmpeg_command(
                Path("input.mp4"),
                Path("output.mp4"),
                [
                    {"operation": "Resize", "width": "640", "height": "480"},
                    {"operation": "Trim", "start": "0", "duration": "2"},
                ],
                "ffmpeg",
            )
        with self.assertRaisesRegex(ValueError, "duration positive"):
            build_ffmpeg_command(
                Path("input.mp4"),
                Path("output.mp4"),
                [{"operation": "Trim", "start": "0", "duration": "0"}],
                "ffmpeg",
            )

    def test_uses_unique_processed_output_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            source = root / "source.mp4"
            (root / "source_processed.mp4").touch()
            steps = [{"operation": "Trim", "start": "0", "duration": "2"}]
            self.assertEqual(
                processed_output_path(source, root, steps),
                root / "source_processed_1.mp4",
            )

    def test_reserves_output_name_by_creating_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            (folder / "out.mp4").write_bytes(b"existing")
            (folder / "out_1.mp4").symlink_to(folder / "dangling-target")

            reserved = reserve_output_path(folder, "out", ".mp4")

            self.assertEqual(reserved, folder / "out_2.mp4")
            self.assertEqual(reserved.read_bytes(), b"")
            self.assertEqual((folder / "out.mp4").read_bytes(), b"existing")
            self.assertFalse((folder / "dangling-target").exists())

    def run_workflow_with_ffmpeg(self, folder: Path, returncode: int) -> list[str]:
        """Run a trim workflow with a fake ffmpeg that writes its output file."""
        source = folder / "clip.mp4"
        source.write_bytes(b"source")

        def fake_ffmpeg(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
            Path(command[-1]).write_bytes(b"partial" if returncode else b"output")
            return subprocess.CompletedProcess(command, returncode, "", "boom")

        steps = [{"operation": "Trim", "start": "0", "duration": "2"}]
        with (
            mock.patch("media_toolkit.media.ffmpeg_tools.shutil.which", return_value="ffmpeg"),
            mock.patch("media_toolkit.processing.workflow.run_cancellable", side_effect=fake_ffmpeg),
        ):
            return run_workflow([source], folder, steps)

    def test_workflow_writes_next_free_name_and_keeps_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            (folder / "clip_processed.mp4").write_bytes(b"keep me")

            outcomes = self.run_workflow_with_ffmpeg(folder, returncode=0)

            self.assertEqual(outcomes, [f"Created {folder / 'clip_processed_1.mp4'}"])
            self.assertEqual((folder / "clip_processed.mp4").read_bytes(), b"keep me")
            self.assertEqual((folder / "clip_processed_1.mp4").read_bytes(), b"output")

    def test_failed_workflow_removes_only_its_own_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            (folder / "clip_processed.mp4").write_bytes(b"keep me")

            outcomes = self.run_workflow_with_ffmpeg(folder, returncode=1)

            self.assertEqual(outcomes, ["Failed clip.mp4: boom"])
            self.assertEqual((folder / "clip_processed.mp4").read_bytes(), b"keep me")
            self.assertFalse((folder / "clip_processed_1.mp4").exists())


if __name__ == "__main__":
    unittest.main()
