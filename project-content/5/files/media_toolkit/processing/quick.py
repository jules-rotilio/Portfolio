"""Quick Process logic: available operations, FFmpeg commands, and Pillow conversions."""

from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image

from media_toolkit.core.filesystem import IMAGE_EXTENSIONS, VIDEO_EXTENSIONS, media_kind
from media_toolkit.media.ffmpeg_tools import FFMPEG_QUIET_ARGS, find_tool, run_ffprobe
from media_toolkit.processing.workflow import reserve_output_path

LOGGER = logging.getLogger(__name__)


AUDIO_OUTPUT_SUFFIXES = {"FLAC": ".flac", "WAV": ".wav", "MP3": ".mp3", "Opus": ".opus"}
# Conversions to animated output: they take a time range, frame rate, and
# size, and are the only operations that can be split into several parts.
ANIMATED_CONVERSIONS = frozenset({
    "Convert video to GIF",
    "Convert video to animated WebP",
    "Convert GIF to animated WebP",
    "Convert animated WebP to GIF",
})
# Output suffixes that do not depend on the source file or form settings.
FIXED_OUTPUT_SUFFIXES = {
    "Convert video to GIF": ".gif",
    "Convert video to animated WebP": ".webp",
    "Convert GIF to animated WebP": ".webp",
    "Convert animated WebP to GIF": ".gif",
    "Extract first frame": ".png",
    "Trim video": ".mp4",
    "Resize video": ".mp4",
    "Join audio to video": ".mp4",
    "Join video to audio": ".mp4",
    "Append video": ".mp4",
}
H264_AAC_ARGS = ("-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac")


def available_operations(path: Path) -> list[str]:
    """Return the Quick Process operations offered for a source file."""
    suffix = path.suffix.lower()
    if suffix == ".gif":
        return ["Extract first frame", "Resize GIF", "Convert GIF to animated WebP", "Trim GIF"]
    if suffix == ".webp":
        return ["Extract first frame", "Resize image", "Convert animated WebP to GIF"]
    return {
        "video": [
            "Convert video to GIF", "Convert video to animated WebP",
            "Extract first frame", "Trim video", "Resize video", "Extract audio",
            "Join audio to video", "Append video",
        ],
        "audio": ["Convert audio", "Trim audio", "Join video to audio", "Append audio"],
        "image": ["Resize image"],
    }.get(media_kind(path) or "", [])


def quick_output_path(source: Path, folder: Path, suffix: str) -> Path:
    """Reserve a unique output path without overwriting existing files in the target folder."""
    return reserve_output_path(folder, f"{source.stem}_processed", suffix)


def extract_first_frame(source: Path, destination: Path) -> None:
    """Save the first frame of a GIF/WebP/video as a standalone PNG snapshot."""
    if source.suffix.lower() in {".gif", ".webp"}:
        try:
            with Image.open(source) as animation:
                animation.seek(0)
                animation.convert("RGBA").save(destination, format="PNG")
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            raise RuntimeError(f"Could not extract the first frame from {source}: {error}") from error
        return
    if source.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"First-frame extraction is not supported for {source.suffix}.")

    ffmpeg = find_tool("ffmpeg")
    try:
        result = subprocess.run(
            [
                ffmpeg,
                *FFMPEG_QUIET_ARGS,
                "-y",
                "-i",
                str(source),
                "-frames:v",
                "1",
                "-f",
                "image2",
                str(destination),
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"Could not extract the first frame from {source}: {error}") from error
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"Could not extract a frame from {source}.")


def _animation_frame_durations(path: Path, image: Image.Image) -> list[int]:
    """Collect per-frame delays for animated images, including WebP container timing."""
    frame_count = getattr(image, "n_frames", 1)
    if path.suffix.lower() == ".webp":
        durations: list[int] = []
        with path.open("rb") as webp_file:
            riff_header = webp_file.read(12)
            if len(riff_header) != 12 or riff_header[:4] != b"RIFF" or riff_header[8:] != b"WEBP":
                raise RuntimeError(f"Invalid animated WebP container: {path}.")
            riff_end = 8 + int.from_bytes(riff_header[4:8], "little")
            if riff_end < webp_file.tell():
                raise RuntimeError(f"Invalid animated WebP container size: {path}.")
            while webp_file.tell() + 8 <= riff_end:
                chunk_header = webp_file.read(8)
                if len(chunk_header) != 8:
                    raise RuntimeError(f"Invalid WebP chunk header in {path}.")
                chunk_name = chunk_header[:4]
                chunk_size = int.from_bytes(chunk_header[4:], "little")
                if webp_file.tell() + chunk_size + (chunk_size % 2) > riff_end:
                    raise RuntimeError(f"Invalid WebP chunk size in {path}.")
                if chunk_name == b"ANMF":
                    frame_header = webp_file.read(16)
                    if len(frame_header) != 16 or chunk_size < 16:
                        raise RuntimeError(f"Invalid animation frame in {path}.")
                    durations.append(max(10, int.from_bytes(frame_header[12:15], "little")))
                    webp_file.seek(chunk_size - 16, 1)
                else:
                    webp_file.seek(chunk_size, 1)
                if chunk_size % 2:
                    webp_file.seek(1, 1)
        if len(durations) != frame_count:
            raise RuntimeError(f"Could not read all animated WebP frame durations in {path}.")
        return durations

    durations = []
    for frame_index in range(frame_count):
        image.seek(frame_index)
        durations.append(
            max(10, int(image.info.get("duration", 100)))
        )
    return durations


def probe_video_settings(path: Path) -> tuple[float, int, int]:
    """Read the source video's frame rate and dimensions for UI defaults and sizing."""
    width = 1280
    height = 720
    fps = 30.0
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        with Image.open(path) as image:
            width, height = image.size
            if getattr(image, "n_frames", 1) > 1:
                durations = _animation_frame_durations(path, image)
                if durations:
                    fps = len(durations) * 1000 / sum(durations)
        return fps, width, height

    data = run_ffprobe(
        path,
        "-select_streams", "v:0",
        "-show_entries", "stream=avg_frame_rate,r_frame_rate,width,height",
    )
    try:
        streams = data.get("streams", [])
        if streams:
            stream = streams[0]
            width = int(stream.get("width", width))
            height = int(stream.get("height", height))
            rates = [
                stream.get("avg_frame_rate", "0/0"),
                stream.get("r_frame_rate", "30/1"),
            ]
            for rate in rates:
                numerator, denominator = rate.split("/", 1)
                if float(denominator) != 0:
                    candidate = float(numerator) / float(denominator)
                    if candidate > 0:
                        fps = candidate
                        break
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise RuntimeError(f"Could not read frame rate or dimensions for {path}.") from error
    return fps, width, height


def probe_media_duration(path: Path) -> float:
    """Estimate the duration of the source media, including animated image loops."""
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        with Image.open(path) as image:
            if getattr(image, "n_frames", 1) > 1:
                total_ms = sum(_animation_frame_durations(path, image))
                return total_ms / 1000
            return 0.0

    data = run_ffprobe(path, "-show_entries", "format=duration:stream=duration")
    try:
        duration_value = data.get("format", {}).get("duration")
        if duration_value in (None, "N/A"):
            stream_durations = [
                float(stream["duration"])
                for stream in data.get("streams", [])
                if stream.get("duration") not in (None, "N/A")
            ]
            duration = max(stream_durations, default=0.0)
        else:
            duration = float(duration_value)
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Media duration must be a positive number.")
        return duration
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError(f"Could not read media duration for {path}.") from error


def probe_source(
    path: Path,
) -> tuple[float | None, tuple[float, int, int] | None, str | None]:
    """Probe duration and (fps, width, height) for UI defaults; blocking.

    Returns (duration or None, settings or None, settings error message or None)
    so one failed probe does not hide the other's result.
    """
    try:
        duration: float | None = probe_media_duration(path)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        duration = None
    try:
        return duration, probe_video_settings(path), None
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        return duration, None, str(error)


def selected_time_range(options: dict[str, str]) -> tuple[float, float | None]:
    """Resolve a start/end selection into a time range usable by FFmpeg filters."""
    if "from_start" not in options and "to_end" not in options:
        start = float(options.get("start", "0") or 0)
        if "duration" in options:
            return start, start + float(options["duration"])
        max_length = float(options.get("max_length", "0") or 0)
        return 0.0, max_length or None
    from_start = options.get("from_start", "1") == "1"
    to_end = options.get("to_end", "1") == "1"
    start = 0.0 if from_start else float(options.get("start", "0"))
    end_text = options.get("end", "")
    end = None if to_end else float(end_text)
    if not math.isfinite(start) or start < 0:
        raise ValueError("Start time must be a non-negative number.")
    if end is not None and (not math.isfinite(end) or end <= start):
        raise ValueError("End time must be greater than start time.")
    return start, end


def split_time_ranges(start: float, end: float, part_count: int) -> list[tuple[float, float]]:
    """Divide a time range into evenly sized sub-ranges for multi-part output."""
    if part_count < 2:
        raise ValueError("Split part count must be at least 2.")
    if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
        raise ValueError("A valid start and end time are required to split media.")
    part_length = (end - start) / part_count
    return [
        (start + index * part_length, start + (index + 1) * part_length)
        for index in range(part_count)
    ]


def format_part_length(seconds: float) -> str:
    """Format a duration as a short, readable timestamp for the split label."""
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02}.{milliseconds:03}"


def _add_time_range(args: list[str], options: dict[str, str]) -> None:
    """Extend an FFmpeg command with start/end time arguments from the current UI state."""
    start, end = selected_time_range(options)
    if start:
        args.extend(["-ss", str(start)])
    if end is not None:
        args.extend(["-t", str(end - start)])


def _video_filter(options: dict[str, str], *, default_fps: str = "30") -> str:
    """Build the resize/filter expression used for video and animated output."""
    fps = float(options.get("fps", default_fps))
    width = int(options.get("width", "960"))
    height = int(options.get("height", "540"))
    if not math.isfinite(fps) or not 0 < fps <= 120:
        raise ValueError("Frame rate must be greater than 0 and at most 120.")
    if width <= 0 or height <= 0:
        raise ValueError("Resize dimensions must be positive integers.")
    return (
        f"fps={fps:g},scale={width}:{height}:"
        "force_original_aspect_ratio=decrease:force_divisible_by=2:flags=lanczos"
    )


def convert_animated_webp_to_gif(
    source: Path, destination: Path, options: dict[str, str]
) -> None:
    """Convert an animated WebP to GIF while preserving the selected time window."""
    max_colors = int(options.get("max_colors", "100"))
    start, end = selected_time_range(options)
    fps = float(options.get("fps", "30"))
    if not math.isfinite(fps) or not 0 < fps <= 120:
        raise ValueError("Frame rate must be greater than 0 and at most 120.")
    if not 2 <= max_colors <= 256:
        raise ValueError("Maximum colors must be between 2 and 256.")
    width = int(options.get("width", "960"))
    height = int(options.get("height", "960"))
    if width <= 0 or height <= 0:
        raise ValueError("Resize dimensions must be positive integers.")

    frames: list[Image.Image] = []
    durations: list[int] = []
    has_transparency = False
    with Image.open(source) as animation:
        loop = animation.info.get("loop", 0)
        frame_durations = _animation_frame_durations(source, animation)
        source_frames: list[tuple[Image.Image, int, int]] = []
        elapsed_ms = 0
        for frame_index, duration in enumerate(frame_durations):
            animation.seek(frame_index)
            frame_end = elapsed_ms + duration
            if frame_end > start * 1000 and (end is None or elapsed_ms < end * 1000):
                frame = animation.convert("RGBA")
                has_transparency = has_transparency or frame.getchannel("A").getextrema()[0] < 128
                source_frames.append((frame, elapsed_ms, frame_end))
            elapsed_ms = frame_end

        sample_interval_ms = 1000 / fps
        selected_samples: list[tuple[Image.Image, int]] = []
        sample_time = start * 1000
        while sample_time < elapsed_ms and (end is None or sample_time < end * 1000):
            source_frame = next(
                (
                    frame
                    for frame, frame_start, frame_end in source_frames
                    if frame_start <= sample_time < frame_end
                ),
                None,
            )
            if source_frame is not None:
                frame = source_frame.copy()
                frame.thumbnail((width, height), Image.Resampling.LANCZOS)
                remaining = (end * 1000 - sample_time) if end is not None else sample_interval_ms
                frame_duration = max(10, int(min(sample_interval_ms, remaining)))
                selected_samples.append((frame, frame_duration))
            sample_time += sample_interval_ms

        for frame, duration in selected_samples:
            if frame.width > 960 or frame.height > 960:
                frame.thumbnail((960, 960), Image.Resampling.LANCZOS)
            alpha = frame.getchannel("A")
            transparent = alpha.point(lambda value: 255 if value < 128 else 0)
            quantized = frame.convert("RGB").quantize(
                colors=max(2, max_colors - 1 if has_transparency else max_colors),
                method=Image.Quantize.MEDIANCUT,
            )
            if transparent.getbbox() is not None:
                palette = quantized.getpalette() or []
                palette.extend([0] * (768 - len(palette)))
                quantized.putpalette(palette[:768])
                quantized.paste(255, mask=transparent)
                quantized.info["transparency"] = 255
            frames.append(quantized)
            durations.append(duration)

    if not frames:
        raise ValueError("No frames were available in the animated WebP.")
    save_options: dict[str, Any] = {
        "save_all": True,
        "append_images": frames[1:],
        "duration": durations,
        "loop": loop,
        "optimize": False,
        "disposal": 2,
    }
    if has_transparency:
        save_options["transparency"] = 255
    frames[0].save(destination, **save_options)


def build_quick_command(
    source: Path,
    companion: Path | None,
    destination: Path,
    options: dict[str, str],
    ffmpeg_path: str,
) -> list[str]:
    """Construct the FFmpeg command for a selected quick-processing operation."""
    operation = options["operation"]
    kind = media_kind(source)
    if kind is None:
        raise ValueError(f"Unsupported input media: {source.suffix}")

    args = [ffmpeg_path, *FFMPEG_QUIET_ARGS, "-y"]
    quality = options.get("quality", "Standard")

    def require_companion(required_kind: str) -> Path:
        if companion is None or not companion.is_file():
            raise ValueError("Choose an existing second media file.")
        if media_kind(companion) != required_kind:
            raise ValueError(f"The second file must be {required_kind}.")
        return companion

    if operation in {"Trim video", "Trim audio", "Trim GIF"}:
        _add_time_range(args, options)
        args.extend(["-i", str(source)])
        if kind == "video":
            args.extend(H264_AAC_ARGS)
        elif kind == "image":
            args.extend(["-loop", "0"])
        else:
            args.extend(_audio_encoding_options(source.suffix.lower(), quality))
    elif operation in {"Resize image", "Resize GIF", "Resize video"}:
        _add_time_range(args, options)
        args.extend(["-i", str(source)])
        width = int(options.get("width", "1280"))
        height = int(options.get("height", "720"))
        if width <= 0 or height <= 0:
            raise ValueError("Resize width and height must be positive integers.")
        if source.suffix.lower() in {".gif", ".webp"} or kind == "video":
            scale = _video_filter(
                dict(options, width=str(width), height=str(height))
            )
        else:
            scale = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
                "force_divisible_by=2:flags=lanczos"
            )
        args.extend(["-vf", scale])
        if source.suffix.lower() == ".gif":
            args.extend(["-loop", "0"])
        if kind == "video":
            args.extend(H264_AAC_ARGS)
    elif operation == "Convert animated WebP to GIF":
        raise ValueError(
            "Animated WebP to GIF conversion is handled by Pillow for decoder compatibility."
        )
    elif operation in ANIMATED_CONVERSIONS:
        _add_time_range(args, options)
        args.extend(["-i", str(source)])
        video_filter = _video_filter(options)
        if operation.endswith("GIF"):
            colors = int(options.get("max_colors", "100"))
            if not 2 <= colors <= 256:
                raise ValueError("Maximum colors must be between 2 and 256.")
            args.extend([
                "-filter_complex",
                f"[0:v]{video_filter},split[s0][s1];"
                f"[s0]palettegen=max_colors={colors}[p];[s1][p]paletteuse",
                "-loop", "0",
            ])
        else:
            webp_quality = int(options.get("webp_quality", "80"))
            if not 0 <= webp_quality <= 100:
                raise ValueError("Animated WebP quality must be between 0 and 100.")
            args.extend([
                "-vf", video_filter,
                "-c:v", "libwebp_anim", "-quality", str(webp_quality), "-loop", "0",
            ])
    elif operation in {"Convert audio", "Extract audio"}:
        suffix = AUDIO_OUTPUT_SUFFIXES.get(options.get("format", "MP3"))
        if suffix is None:
            raise ValueError("Choose a supported audio output format.")
        args.extend(["-i", str(source), "-vn"])
        args.extend(_audio_encoding_options(suffix, quality))
        sample_rate = options.get("sample_rate", "Original")
        if sample_rate != "Original":
            args.extend(["-ar", sample_rate])
        destination = destination.with_suffix(suffix)
    elif operation in {"Join audio to video", "Join video to audio"}:
        if operation == "Join audio to video":
            video, audio = source, require_companion("audio")
        else:
            video, audio = require_companion("video"), source
        args.extend(["-i", str(video), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-shortest"])
        args.extend(H264_AAC_ARGS)
        destination = destination.with_suffix(".mp4")
    elif operation == "Append video":
        other = require_companion("video")
        args.extend(["-i", str(source), "-i", str(other)])
        has_audio = _has_audio_stream(source)
        if has_audio != _has_audio_stream(other):
            raise ValueError(
                "Both videos must either contain audio or be silent to append."
            )
        # Both clips are normalised to 1280x720 at 30 fps so they can be concatenated.
        graph = [_normalized_video(0), _normalized_video(1)]
        if has_audio:
            graph += [_normalized_audio(0), _normalized_audio(1)]
            graph.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
            args.extend(["-filter_complex", ";".join(graph), "-map", "[v]", "-map", "[a]"])
            args.extend(H264_AAC_ARGS)
        else:
            graph.append("[v0][v1]concat=n=2:v=1:a=0[v]")
            args.extend(["-filter_complex", ";".join(graph), "-map", "[v]"])
            args.extend(H264_AAC_ARGS[:6])
        destination = destination.with_suffix(".mp4")
    elif operation == "Append audio":
        other = require_companion("audio")
        args.extend(["-i", str(source), "-i", str(other)])
        graph = [
            _normalized_audio(0),
            _normalized_audio(1),
            "[a0][a1]concat=n=2:v=0:a=1[a]",
        ]
        args.extend(["-filter_complex", ";".join(graph), "-map", "[a]"])
        args.extend(_audio_encoding_options(source.suffix.lower(), quality))
    else:
        raise ValueError(f"Unsupported operation: {operation}")

    args.append(str(destination))
    return args


def _normalized_video(input_index: int) -> str:
    """Filter-graph step scaling and padding one input's video for concatenation."""
    return (
        f"[{input_index}:v:0]scale=1280:720:force_original_aspect_ratio=decrease,"
        f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{input_index}]"
    )


def _normalized_audio(input_index: int) -> str:
    """Filter-graph step resampling one input's audio to 48 kHz stereo."""
    return (
        f"[{input_index}:a:0]aresample=48000,"
        f"aformat=channel_layouts=stereo[a{input_index}]"
    )


def _audio_encoding_options(suffix: str, quality: str) -> list[str]:
    """Return codec-specific audio arguments for each supported output format."""
    if suffix == ".flac":
        compression = {"Low": "2", "Standard": "5", "High": "8"}[quality]
        return ["-c:a", "flac", "-compression_level", compression]
    if suffix == ".wav":
        codec = "pcm_s24le" if quality == "High" else "pcm_s16le"
        return ["-c:a", codec]
    if suffix == ".mp3":
        qscale = {"Low": "5", "Standard": "2", "High": "0"}[quality]
        return ["-c:a", "libmp3lame", "-q:a", qscale]
    if suffix == ".opus":
        bitrate = {"Low": "64k", "Standard": "128k", "High": "192k"}[quality]
        return ["-c:a", "libopus", "-b:a", bitrate]
    if suffix == ".ogg":
        level = {"Low": "2", "Standard": "5", "High": "8"}[quality]
        return ["-c:a", "libvorbis", "-q:a", level]
    if suffix in {".aac", ".m4a"}:
        bitrate = {"Low": "96k", "Standard": "192k", "High": "256k"}[quality]
        return ["-c:a", "aac", "-b:a", bitrate]
    if suffix == ".aiff":
        codec = "pcm_s24be" if quality == "High" else "pcm_s16be"
        return ["-c:a", codec]
    return ["-c:a", "aac"]


def _has_audio_stream(path: Path) -> bool:
    """Check whether the file has an audio stream, for append compatibility."""
    data = run_ffprobe(path, "-select_streams", "a:0", "-show_entries", "stream=codec_type")
    return bool(data.get("streams"))
