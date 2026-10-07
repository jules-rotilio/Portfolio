"""Discover media files and compute cached metadata and perceptual hashes."""

from __future__ import annotations

import hashlib
import logging
import math
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps
import imagehash

from media_toolkit.core.database import MediaRecord
from media_toolkit.media.ffmpeg_tools import FFMPEG_QUIET_ARGS, find_tool
from media_toolkit.core.filesystem import media_kind
from media_toolkit.media.media_info import format_media_details, media_duration, read_media_info

# Number of evenly spaced frames hashed in each video or animated GIF.
VIDEO_HASH_FRAME_COUNT = 10
VIDEO_HASH_SIZE = 64
# Video samples start at 10% and cover 80% of the clip to avoid edge frames.
VIDEO_HASH_SAMPLE_START = 0.1
VIDEO_HASH_SAMPLE_WINDOW = 0.8
# These persisted algorithm versions are cache invalidators, not similarity
# thresholds. Bump the relevant version when its sampling/hash algorithm changes.
VIDEO_PERCEPTUAL_HASH_VERSION = 3
ANIMATED_IMAGE_PERCEPTUAL_HASH_VERSION = 2
LOGGER = logging.getLogger(__name__)


def sha256_file(path: Path) -> str:
    """Return the SHA-256 digest of a file, reading it in bounded chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as media_file:
        for chunk in iter(lambda: media_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def image_perceptual_hash(path: Path) -> str | None:
    """Return a 64-bit pHash, sampling animated GIFs into a frame sequence."""
    try:
        with Image.open(path) as image:
            if image.format == "GIF" and image.n_frames > 1:
                frame_indexes = _sample_frame_indexes(image.n_frames)
                frame_hashes = []
                for frame_index in frame_indexes:
                    image.seek(frame_index)
                    normalized = ImageOps.exif_transpose(image).convert("RGB")
                    frame_hashes.append(str(imagehash.phash(normalized)))
                return "frames-v1:" + ",".join(frame_hashes)
            normalized = ImageOps.exif_transpose(image).convert("RGB")
            return str(imagehash.phash(normalized))
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def _sample_frame_indexes(frame_count: int) -> list[int]:
    """Choose the configured number of evenly spaced animation frame indexes."""
    if frame_count <= 1:
        return [0]
    return [
        round(index * (frame_count - 1) / (VIDEO_HASH_FRAME_COUNT - 1))
        for index in range(VIDEO_HASH_FRAME_COUNT)
    ]


def video_perceptual_hash(path: Path, duration: float | None = None) -> str | None:
    """Hash configured video frames sampled from the central 80% of its duration.

    The 64-bit frame pHashes are stored as a sequence for threshold-based
    matching in database.py. Missing tools, invalid media, or incomplete frame
    extraction produce None rather than failing the overall indexing pass.
    Pass the duration when it is already known to skip probing for it.
    """
    try:
        if duration is None:
            duration = media_duration(read_media_info(path))
        ffmpeg = find_tool("ffmpeg")
    except (OSError, RuntimeError):
        return None
    if duration is None or not math.isfinite(duration) or duration <= 0:
        return None

    try:
        frames = subprocess.run(
            [
                ffmpeg,
                *FFMPEG_QUIET_ARGS,
                "-ss",
                f"{duration * VIDEO_HASH_SAMPLE_START:.6f}",
                "-i",
                str(path),
                "-an",
                "-sn",
                "-dn",
                "-vf",
                (
                    "fps="
                    f"{VIDEO_HASH_FRAME_COUNT / (duration * VIDEO_HASH_SAMPLE_WINDOW):.12g},"
                    f"scale={VIDEO_HASH_SIZE}:{VIDEO_HASH_SIZE}:"
                    "force_original_aspect_ratio=decrease,"
                    f"pad={VIDEO_HASH_SIZE}:{VIDEO_HASH_SIZE}:(ow-iw)/2:(oh-ih)/2"
                ),
                "-frames:v",
                str(VIDEO_HASH_FRAME_COUNT),
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "pipe:1",
            ],
            capture_output=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None

    frame_bytes = VIDEO_HASH_SIZE * VIDEO_HASH_SIZE * 3
    if frames.returncode != 0 or len(frames.stdout) != frame_bytes * VIDEO_HASH_FRAME_COUNT:
        return None
    frame_hashes = [
        str(
            imagehash.phash(
                Image.frombytes(
                    "RGB",
                    (VIDEO_HASH_SIZE, VIDEO_HASH_SIZE),
                    frames.stdout[offset : offset + frame_bytes],
                )
            )
        )
        for offset in range(0, len(frames.stdout), frame_bytes)
    ]
    return "frames-v1:" + ",".join(frame_hashes)


def index_media_file(
    path: Path,
    root: Path,
    cached: MediaRecord | None,
) -> MediaRecord:
    """Reuse a valid stat-matched cache entry or probe and hash the file anew."""
    stat = path.stat()
    # Hash-version metadata forces re-indexing when a hash algorithm changes;
    # size and mtime alone cannot establish that the cached hash is current.
    if (
        cached is not None
        and cached.size == stat.st_size
        and cached.mtime_ns == stat.st_mtime_ns
        and not (
            (
                cached.media_type == "video"
                and (
                    cached.perceptual_hash is None
                    or cached.metadata.get("video_perceptual_hash_version")
                    != VIDEO_PERCEPTUAL_HASH_VERSION
                )
            )
            or (
                path.suffix.lower() == ".gif"
                and cached.metadata.get("animated_image_perceptual_hash_version")
                != ANIMATED_IMAGE_PERCEPTUAL_HASH_VERSION
            )
        )
    ):
        LOGGER.debug("Reusing indexed metadata for %s", path)
        return replace(cached, root=str(root))

    LOGGER.info("Hashing and probing media file %s", path)
    digest = sha256_file(path)
    media_type = media_kind(path) or "other"
    metadata: dict[str, Any] = {}
    # One ffprobe run provides both the details panel and the video duration.
    media_info: dict[str, Any] | None = None
    try:
        media_info = read_media_info(path)
        metadata["details"] = format_media_details(path, media_info)
    except (OSError, RuntimeError) as error:
        metadata["error"] = str(error)
    perceptual_hash = None
    if media_type == "image":
        perceptual_hash = image_perceptual_hash(path)
    elif media_type == "video" and media_info is not None:
        duration = media_duration(media_info)
        if duration is not None:
            perceptual_hash = video_perceptual_hash(path, duration)
    if media_type == "video" and perceptual_hash is not None:
        metadata["video_perceptual_hash_version"] = VIDEO_PERCEPTUAL_HASH_VERSION
    elif path.suffix.lower() == ".gif" and perceptual_hash is not None:
        metadata["animated_image_perceptual_hash_version"] = (
            ANIMATED_IMAGE_PERCEPTUAL_HASH_VERSION
        )
    return MediaRecord(
        path=str(path),
        root=str(root),
        size=stat.st_size,
        mtime_ns=stat.st_mtime_ns,
        sha256=digest,
        perceptual_hash=perceptual_hash,
        media_type=media_type,
        metadata=metadata,
    )
