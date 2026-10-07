"""Tests for quick-processing command generation and media extraction.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image

from media_toolkit.processing.quick import (
    format_part_length,
    split_time_ranges,
    build_quick_command,
    convert_animated_webp_to_gif,
    extract_first_frame,
    probe_media_duration,
    quick_output_path,
)
from media_toolkit.ui.quick_process_tab import _ProcessWorker


class QuickProcessTests(unittest.TestCase):
    """Covers command generation, trimming, and first-frame extraction."""
    def test_splits_selected_duration_into_equal_parts(self) -> None:
        ranges = split_time_ranges(8, 24, 4)
        self.assertEqual(ranges, [(8, 12), (12, 16), (16, 20), (20, 24)])
        self.assertEqual(format_part_length((24 - 8) / 4), "00:00:04.000")

    def test_probes_animated_webp_duration_for_split_calculation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            source = Path(temporary_directory) / "animation.webp"
            frames = [Image.new("RGB", (16, 12), color) for color in ("red", "blue")]
            frames[0].save(
                source,
                save_all=True,
                append_images=frames[1:],
                duration=[150, 250],
                loop=0,
            )
            self.assertAlmostEqual(probe_media_duration(source), 0.4)

    def test_extracts_first_frame_of_gif_and_animated_webp_as_png(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            for suffix in (".gif", ".webp"):
                with self.subTest(suffix=suffix):
                    source = folder / f"animation{suffix}"
                    destination = folder / f"first{suffix}.png"
                    frames = [
                        Image.new("RGB", (16, 12), color)
                        for color in ("red", "blue")
                    ]
                    frames[0].save(
                        source,
                        save_all=True,
                        append_images=frames[1:],
                        duration=100,
                        loop=0,
                    )

                    extract_first_frame(source, destination)

                    with Image.open(destination) as result:
                        self.assertEqual(result.format, "PNG")
                        self.assertEqual(result.size, (16, 12))
                        first_pixel = result.convert("RGB").getpixel((0, 0))
                        self.assertLess(abs(first_pixel[0] - 255), 5)
                        self.assertLess(abs(first_pixel[1]), 5)
                        self.assertLess(abs(first_pixel[2]), 5)

    def test_builds_gif_conversion_with_color_limit_and_max_length(self) -> None:
        command = build_quick_command(
            Path("clip.mp4"),
            None,
            Path("clip.gif"),
            {
                "operation": "Convert video to GIF",
                "max_colors": "64",
                "max_length": "8",
            },
            "ffmpeg",
        )

        self.assertEqual(command[command.index("-t") + 1], "8.0")
        self.assertIn("palettegen=max_colors=64", " ".join(command))
        self.assertEqual(command[-1], "clip.gif")

    def test_uses_animated_webp_encoder(self) -> None:
        command = build_quick_command(
            Path("clip.mp4"),
            None,
            Path("clip.webp"),
            {
                "operation": "Convert video to animated WebP",
                "max_length": "0",
            },
            "ffmpeg",
        )
        self.assertEqual(command[command.index("-c:v") + 1], "libwebp_anim")
        self.assertEqual(command[command.index("-quality") + 1], "80")

    def test_uses_selected_animated_webp_quality(self) -> None:
        for operation, source in (
            ("Convert video to animated WebP", Path("clip.mp4")),
            ("Convert GIF to animated WebP", Path("clip.gif")),
        ):
            with self.subTest(operation=operation):
                command = build_quick_command(
                    source,
                    None,
                    Path("clip.webp"),
                    {
                        "operation": operation,
                        "webp_quality": "93",
                    },
                    "ffmpeg",
                )
                self.assertEqual(command[command.index("-quality") + 1], "93")

    def test_rejects_out_of_range_animated_webp_quality(self) -> None:
        with self.assertRaisesRegex(ValueError, "between 0 and 100"):
            build_quick_command(
                Path("clip.mp4"),
                None,
                Path("clip.webp"),
                {
                    "operation": "Convert video to animated WebP",
                    "webp_quality": "101",
                },
                "ffmpeg",
            )

    def test_video_conversion_uses_selected_fps_and_dimensions(self) -> None:
        command = build_quick_command(
            Path("clip.mp4"),
            None,
            Path("clip.webp"),
            {
                "operation": "Convert video to animated WebP",
                "fps": "23.976",
                "width": "640",
                "height": "360",
                "from_start": "1",
                "to_end": "1",
            },
            "ffmpeg",
        )
        video_filter = command[command.index("-vf") + 1]
        self.assertIn("fps=23.976", video_filter)
        self.assertIn("scale=640:360:force_original_aspect_ratio=decrease", video_filter)
        self.assertNotIn("-ss", command)
        self.assertNotIn("-t", command)

    def test_trim_time_checkboxes_create_partial_and_full_ranges(self) -> None:
        path = Path("clip.mp4")
        trim = {"operation": "Trim video", "start": "8", "end": "24",
                "from_start": "0", "to_end": "0"}
        command = build_quick_command(path, None, Path("out.mp4"), trim, "ffmpeg")
        self.assertEqual(command[command.index("-ss") + 1], "8.0")
        self.assertEqual(command[command.index("-t") + 1], "16.0")

        to_end = dict(trim, to_end="1")
        command = build_quick_command(path, None, Path("out.mp4"), to_end, "ffmpeg")
        self.assertEqual(command[command.index("-ss") + 1], "8.0")
        self.assertNotIn("-t", command)

        whole_length = dict(trim, from_start="1", to_end="1")
        command = build_quick_command(
            path, None, Path("out.mp4"), whole_length, "ffmpeg"
        )
        self.assertNotIn("-ss", command)
        self.assertNotIn("-t", command)

    def test_builds_audio_conversion_with_compression_and_sample_rate(self) -> None:
        command = build_quick_command(
            Path("source.flac"),
            None,
            Path("source_processed.mp3"),
            {
                "operation": "Convert audio",
                "format": "MP3",
                "quality": "High",
                "sample_rate": "48000",
            },
            "ffmpeg",
        )

        self.assertEqual(command[command.index("-q:a") + 1], "0")
        self.assertEqual(command[command.index("-ar") + 1], "48000")
        self.assertEqual(command[-1], "source_processed.mp3")

    def test_builds_mux_and_append_commands(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            video = folder / "video.mp4"
            audio = folder / "audio.flac"
            other_audio = folder / "other.wav"
            video.touch()
            audio.touch()
            other_audio.touch()
            mux = build_quick_command(
                video,
                audio,
                folder / "joined.mp4",
                {"operation": "Join audio to video"},
                "ffmpeg",
            )
            self.assertEqual(mux[mux.index("-map") + 1], "0:v:0")
            self.assertEqual(
                mux[mux.index("-map", mux.index("-map") + 1) + 1], "1:a:0"
            )

            append = build_quick_command(
                audio,
                other_audio,
                folder / "joined.flac",
                {"operation": "Append audio", "quality": "Standard"},
                "ffmpeg",
            )
            self.assertIn("concat=n=2:v=0:a=1", " ".join(append))

    def test_rejects_missing_or_wrong_companion_media(self) -> None:
        with self.assertRaisesRegex(ValueError, "Choose an existing"):
            build_quick_command(
                Path("video.mp4"),
                None,
                Path("out.mp4"),
                {"operation": "Join audio to video"},
                "ffmpeg",
            )
        with tempfile.TemporaryDirectory() as temporary_directory:
            wrong_companion = Path(temporary_directory) / "another.mp4"
            wrong_companion.touch()
            with self.assertRaisesRegex(ValueError, "second file must be audio"):
                build_quick_command(
                    Path("video.mp4"),
                    wrong_companion,
                    Path("out.mp4"),
                    {"operation": "Join audio to video"},
                    "ffmpeg",
                )

    def test_rejects_appending_videos_with_mismatched_audio_streams(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            silent = folder / "silent.mp4"
            with_audio = folder / "with-audio.mp4"
            silent.touch()
            with_audio.touch()
            from unittest.mock import patch

            with patch(
                "media_toolkit.processing.quick._has_audio_stream",
                side_effect=[False, True],
            ):
                with self.assertRaisesRegex(ValueError, "Both videos must"):
                    build_quick_command(
                        silent,
                        with_audio,
                        folder / "joined.mp4",
                        {"operation": "Append video"},
                        "ffmpeg",
                    )

    def test_uses_unique_output_names(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = Path("clip.mp4")
            (folder / "clip_processed.gif").touch()
            self.assertEqual(
                quick_output_path(source, folder, ".gif"),
                folder / "clip_processed_1.gif",
            )

    def test_converts_animated_webp_to_gif_with_color_and_length_limits(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            source = folder / "animation.webp"
            destination = folder / "animation.gif"
            frames = [
                Image.new("RGBA", (32, 24), color)
                for color in (
                    (255, 0, 0, 255),
                    (0, 255, 0, 0),
                    (0, 0, 255, 255),
                )
            ]
            frames[0].save(
                source,
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
                lossless=True,
            )

            convert_animated_webp_to_gif(
                source,
                destination,
                {"max_colors": "32", "max_length": "0.2"},
            )

            with Image.open(destination) as result:
                self.assertEqual(result.n_frames, 2)
                self.assertEqual(result.info["loop"], 0)
                self.assertEqual(result.info["transparency"], 255)

    def run_split_conversion(self, folder: Path, returncode: int) -> list[str]:
        """Run a two-part GIF conversion with a fake ffmpeg writing each output."""
        source = folder / "clip.mp4"
        source.write_bytes(b"source")
        destination = quick_output_path(source, folder, ".gif")
        options = {
            "operation": "Convert video to GIF",
            "from_start": "1",
            "to_end": "0",
            "start": "0",
            "end": "4",
            "split_count": "2",
        }

        def fake_ffmpeg(command: list[str], **_kwargs) -> subprocess.CompletedProcess:
            Path(command[-1]).write_bytes(b"gif")
            return subprocess.CompletedProcess(command, returncode, "", "boom")

        messages: list[str] = []
        worker = _ProcessWorker(source, None, destination, options)
        worker.completed.connect(messages.append)
        with (
            mock.patch("media_toolkit.media.ffmpeg_tools.shutil.which", return_value="ffmpeg"),
            mock.patch("media_toolkit.ui.quick_process_tab.run_cancellable", side_effect=fake_ffmpeg),
        ):
            worker.run()
        return messages

    def test_split_conversion_replaces_placeholder_with_part_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            (folder / "clip_processed_part_01_of_02.gif").write_bytes(b"keep me")

            messages = self.run_split_conversion(folder, returncode=0)

            self.assertEqual(messages, [f"Created 2 parts in {folder}"])
            self.assertEqual(
                sorted(path.name for path in folder.glob("*.gif")),
                [
                    "clip_processed_part_01_of_02.gif",
                    "clip_processed_part_01_of_02_1.gif",
                    "clip_processed_part_02_of_02.gif",
                ],
            )
            self.assertEqual(
                (folder / "clip_processed_part_01_of_02.gif").read_bytes(), b"keep me"
            )

    def test_failed_split_conversion_removes_only_its_own_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            folder = Path(temporary_directory)
            (folder / "clip_processed_part_01_of_02.gif").write_bytes(b"keep me")

            messages = self.run_split_conversion(folder, returncode=1)

            self.assertEqual(messages, ["Failed: boom"])
            self.assertEqual(
                [path.name for path in folder.glob("*.gif")],
                ["clip_processed_part_01_of_02.gif"],
            )


if __name__ == "__main__":
    unittest.main()
