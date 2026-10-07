"""Tests for perceptual hashing and indexed media refresh behavior.
"""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image

from media_toolkit.core.database import MediaRecord
from media_toolkit.media.indexer import (
    ANIMATED_IMAGE_PERCEPTUAL_HASH_VERSION,
    VIDEO_HASH_FRAME_COUNT,
    VIDEO_PERCEPTUAL_HASH_VERSION,
    index_media_file,
    video_perceptual_hash,
)


class IndexerTests(unittest.TestCase):
    """Exercises video and animated-image hashing for duplicate detection."""
    def test_video_hash_samples_multiple_frames(self) -> None:
        frame = Image.new("RGB", (64, 64), color=(40, 80, 120)).tobytes()
        probe = SimpleNamespace(
            returncode=0, stdout='{"format": {"duration": "10"}}', stderr=""
        )
        extracted_frames = SimpleNamespace(
            returncode=0, stdout=frame * VIDEO_HASH_FRAME_COUNT, stderr=b""
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "video.mp4"
            path.touch()
            with (
                patch(
                    "media_toolkit.media.ffmpeg_tools.shutil.which",
                    side_effect=["/usr/bin/ffprobe", "/usr/bin/ffmpeg"],
                ),
                patch(
                    "media_toolkit.media.indexer.subprocess.run",
                    side_effect=[probe, extracted_frames],
                ) as run,
            ):
                perceptual_hash = video_perceptual_hash(path)

        self.assertIsNotNone(perceptual_hash)
        assert perceptual_hash is not None
        self.assertEqual(
            len(perceptual_hash.removeprefix("frames-v1:").split(",")),
            VIDEO_HASH_FRAME_COUNT,
        )
        ffmpeg_command = run.call_args_list[1].args[0]
        self.assertIn("-frames:v", ffmpeg_command)
        self.assertIn(str(VIDEO_HASH_FRAME_COUNT), ffmpeg_command)
        filter_expression = ffmpeg_command[ffmpeg_command.index("-vf") + 1]
        self.assertIn(
            f"fps={VIDEO_HASH_FRAME_COUNT / (10 * 0.8):g}", filter_expression
        )

    def test_reindexes_cached_videos_without_a_perceptual_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "video.mp4"
            path.write_bytes(b"video")
            stat = path.stat()
            cached = MediaRecord(
                path=str(path),
                root=str(root),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256="old-sha",
                perceptual_hash=None,
                media_type="video",
                metadata={},
            )
            with (
                patch("media_toolkit.media.indexer.sha256_file", return_value="new-sha"),
                patch(
                    "media_toolkit.media.indexer.video_perceptual_hash",
                    return_value="frames-v1:"
                    + ",".join(["0" * 16] * VIDEO_HASH_FRAME_COUNT),
                ) as hash_video,
                patch(
                    "media_toolkit.media.indexer.read_media_info",
                    return_value={"format": {"duration": "10"}},
                ),
            ):
                record = index_media_file(path, root, cached)

        # The duration comes from the single details probe.
        hash_video.assert_called_once_with(path, 10.0)
        self.assertEqual(record.sha256, "new-sha")
        self.assertTrue(record.perceptual_hash.startswith("frames-v1:"))

    def test_retries_cached_video_without_a_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            path = root / "video.mp4"
            path.write_bytes(b"video")
            stat = path.stat()
            cached = MediaRecord(
                path=str(path),
                root=str(root),
                size=stat.st_size,
                mtime_ns=stat.st_mtime_ns,
                sha256="sha",
                perceptual_hash=None,
                media_type="video",
                metadata={
                    "video_perceptual_hash_version": VIDEO_PERCEPTUAL_HASH_VERSION
                },
            )
            with (
                patch("media_toolkit.media.indexer.sha256_file", return_value="sha"),
                patch(
                    "media_toolkit.media.indexer.video_perceptual_hash",
                    return_value=None,
                ) as hash_video,
                patch(
                    "media_toolkit.media.indexer.read_media_info",
                    return_value={"format": {"duration": "10"}},
                ),
            ):
                record = index_media_file(path, root, cached)

        # The duration comes from the single details probe.
        hash_video.assert_called_once_with(path, 10.0)
        self.assertIsNone(record.perceptual_hash)
        self.assertNotIn("video_perceptual_hash_version", record.metadata)

    def test_hashes_animated_gif_frames_and_leaves_static_gifs_as_stills(self) -> None:
        first = Image.new("RGB", (32, 32), color=(255, 0, 0))
        second = Image.new("RGB", (32, 32), color=(0, 0, 255))
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            animated = root / "animated.gif"
            first.save(
                animated,
                save_all=True,
                append_images=[second],
                duration=100,
                loop=0,
            )
            still = root / "still.gif"
            first.save(still)

            animated_record = index_media_file(animated, root, None)
            still_record = index_media_file(still, root, None)

        assert animated_record.perceptual_hash is not None
        self.assertTrue(animated_record.perceptual_hash.startswith("frames-v1:"))
        self.assertEqual(
            len(animated_record.perceptual_hash.removeprefix("frames-v1:").split(",")),
            VIDEO_HASH_FRAME_COUNT,
        )
        self.assertEqual(
            animated_record.metadata["animated_image_perceptual_hash_version"],
            ANIMATED_IMAGE_PERCEPTUAL_HASH_VERSION,
        )
        assert still_record.perceptual_hash is not None
        self.assertFalse(still_record.perceptual_hash.startswith("frames-v1:"))


if __name__ == "__main__":
    unittest.main()
