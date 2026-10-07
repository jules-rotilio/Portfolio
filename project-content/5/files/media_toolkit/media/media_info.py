"""Extract and format concise technical media details with ffprobe."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from media_toolkit.media.ffmpeg_tools import run_ffprobe
from media_toolkit.core.filesystem import format_size


def _format_duration(value: Any) -> str | None:
    """Format a numeric duration in whole seconds as HH:MM:SS."""
    if value in (None, ""):
        return None
    try:
        total_seconds = int(float(value))
    except (TypeError, ValueError):
        return None
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}"


def _format_bitrate(value: Any) -> str | None:
    """Format a positive bitrate in bits/s as rounded decimal kb/s."""
    try:
        bitrate = int(float(value))
    except (TypeError, ValueError):
        return None
    return f"{bitrate / 1000:.0f} kb/s" if bitrate > 0 else None


# Format and stream fields read by ffprobe for the media details panel.
_MEDIA_INFO_ENTRIES = (
    "format=format_name,format_long_name,duration,bit_rate:"
    "stream=codec_type,codec_name,profile,width,height,avg_frame_rate,"
    "sample_rate,channels,channel_layout,bit_rate"
)


def read_media_info(path: Path) -> dict[str, Any]:
    """Return ffprobe's raw format and stream data for path (runs ffprobe)."""
    return run_ffprobe(path, "-show_entries", _MEDIA_INFO_ENTRIES)


def media_duration(data: dict[str, Any]) -> float | None:
    """Return the container duration in seconds from read_media_info data."""
    try:
        duration = float(data.get("format", {}).get("duration"))
    except (TypeError, ValueError):
        return None
    return duration if math.isfinite(duration) and duration > 0 else None


def probe_media(path: Path) -> list[str]:
    """Return concise technical media details using ffprobe."""
    return format_media_details(path, read_media_info(path))


def format_media_details(path: Path, data: dict[str, Any]) -> list[str]:
    """Format read_media_info data as short "Label: value" lines."""
    lines = [f"File size: {format_size(path.stat().st_size)}"]
    format_info = data.get("format", {})
    format_name = format_info.get("format_long_name") or format_info.get("format_name")
    if format_name:
        lines.append(f"Format: {format_name}")

    duration = _format_duration(format_info.get("duration"))
    if duration is not None:
        lines.append(f"Duration: {duration}")

    for stream in data.get("streams", []):
        codec = stream.get("codec_name", "unknown codec")
        kind = stream.get("codec_type")
        if kind == "video":
            resolution = ""
            if stream.get("width") and stream.get("height"):
                resolution = f", {stream['width']} x {stream['height']}"
            profile = stream.get("profile")
            profile_text = f" ({profile})" if profile else ""
            frame_rate = stream.get("avg_frame_rate")
            fps = ""
            if frame_rate and frame_rate != "0/0":
                try:
                    numerator, denominator = frame_rate.split("/", 1)
                    frame_rate_value = float(numerator) / float(denominator)
                    fps_value = f"{frame_rate_value:.2f}".rstrip("0").rstrip(".")
                    fps = f", {fps_value} fps"
                except (ValueError, ZeroDivisionError):
                    pass
            lines.append(f"Video: {codec}{profile_text}{resolution}{fps}")
        elif kind == "audio":
            channel_count = stream.get("channels")
            channel_layout = stream.get("channel_layout")
            channels = channel_layout or (
                f"{channel_count} channels" if channel_count else ""
            )
            sample_rate = stream.get("sample_rate")
            sample = f", {sample_rate} Hz" if sample_rate else ""
            suffix = f", {channels}" if channels else ""
            lines.append(f"Audio: {codec}{suffix}{sample}")

    bitrate = _format_bitrate(format_info.get("bit_rate"))
    if bitrate:
        lines.append(f"Bit rate: {bitrate}")
    return lines
