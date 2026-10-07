"""Tests covering ffprobe metadata parsing and missing dependency failures.
"""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from media_toolkit.media.media_info import probe_media


class MediaInfoTests(unittest.TestCase):
    """Exercises media metadata shaping for video and audio streams."""
    def test_formats_video_and_audio_metadata(self) -> None:
        payload = {
            "format": {
                "format_long_name": "QuickTime / MOV",
                "duration": "65.2",
                "bit_rate": "1200000",
            },
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "avg_frame_rate": "30/1",
                },
                {
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "channels": 2,
                    "channel_layout": "stereo",
                    "sample_rate": "48000",
                },
            ],
        }
        completed = SimpleNamespace(
            returncode=0, stdout=json.dumps(payload), stderr=""
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "video.mp4"
            path.write_bytes(b"video")
            with (
                patch("media_toolkit.media.ffmpeg_tools.shutil.which", return_value="/usr/bin/ffprobe"),
                patch("media_toolkit.media.ffmpeg_tools.subprocess.run", return_value=completed),
            ):
                details = probe_media(path)

        self.assertIn("Duration: 00:01:05", details)
        self.assertIn("Video: h264, 1920 x 1080, 30 fps", details)
        self.assertIn("Audio: aac, stereo, 48000 Hz", details)
        self.assertIn("Bit rate: 1200 kb/s", details)

    def test_reports_missing_ffprobe(self) -> None:
        with patch("media_toolkit.media.ffmpeg_tools.shutil.which", return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, "install FFmpeg"):
                probe_media(Path("missing.mp4"))


if __name__ == "__main__":
    unittest.main()
