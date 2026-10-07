"""Build FFmpeg commands and execute saved media-processing workflows."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from media_toolkit.media.ffmpeg_tools import (
    FFMPEG_QUIET_ARGS,
    ProcessingCancelled,
    find_tool,
    run_cancellable,
)


OUTPUT_FORMATS = {
    "MP4": ".mp4",
    "WebM": ".webm",
    "MP3": ".mp3",
    "WAV": ".wav",
    "GIF": ".gif",
    "Animated WebP": ".webp",
}


def build_ffmpeg_command(
    source: Path,
    destination: Path,
    steps: list[dict[str, str]],
    ffmpeg_path: str,
) -> list[str]:
    """Validate a workflow and build its FFmpeg argument vector.

    Operations run in the fixed order Trim, Resize, then one output operation;
    conversion settings and output suffixes are selected from OUTPUT_FORMATS.
    """
    trim_steps = [step for step in steps if step["operation"] == "Trim"]
    resize_steps = [step for step in steps if step["operation"] == "Resize"]
    output_steps = [
        step
        for step in steps
        if step["operation"] in {"Convert format", "Extract audio"}
    ]
    if len(trim_steps) > 1 or len(resize_steps) > 1 or len(output_steps) > 1:
        raise ValueError("Use at most one block of each operation type.")
    if not steps:
        raise ValueError("Add at least one processing block.")
    order = {"Trim": 0, "Resize": 1, "Convert format": 2, "Extract audio": 2}
    if any(step["operation"] not in order for step in steps):
        raise ValueError("Workflow contains an unsupported processing block.")
    if [order[step["operation"]] for step in steps] != sorted(
        order[step["operation"]] for step in steps
    ):
        raise ValueError("Order blocks as Trim, Resize, then output format.")

    arguments = [ffmpeg_path, *FFMPEG_QUIET_ARGS, "-y"]
    if trim_steps:
        trim = trim_steps[0]
        start = float(trim["start"])
        duration = float(trim["duration"])
        if start < 0 or duration <= 0:
            raise ValueError("Trim start must be non-negative and duration positive.")
        arguments.extend(["-ss", str(start), "-t", str(duration)])
    arguments.extend(["-i", str(source)])

    filters: list[str] = []
    if resize_steps:
        resize = resize_steps[0]
        width = int(resize["width"])
        height = int(resize["height"])
        if width <= 0 or height <= 0:
            raise ValueError("Resize dimensions must be positive integers.")
        filters.append(
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2"
        )

    output = destination
    output_name = "MP4"
    if output_steps:
        output_step = output_steps[0]
        if output_step["operation"] == "Extract audio":
            output_name = output_step.get("format", "MP3")
            arguments.append("-vn")
        else:
            output_name = output_step["format"]

    format_args: dict[str, list[str]] = {
        "MP4": ["-c:v", "libx264", "-crf", "20", "-preset", "medium", "-c:a", "aac", "-b:a", "192k"],
        "WebM": ["-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-c:a", "libopus"],
        "MP3": ["-vn", "-c:a", "libmp3lame", "-q:a", "2"],
        "WAV": ["-vn", "-c:a", "pcm_s16le"],
        "GIF": ["-loop", "0"],
        "Animated WebP": ["-c:v", "libwebp_anim", "-quality", "80", "-loop", "0"],
    }
    if output_steps:
        if output_name == "GIF":
            filters.insert(0, "fps=15")
            if not resize_steps:
                filters.append("scale=960:-2:flags=lanczos")
        arguments.extend(format_args[output_name])
        output = destination.with_suffix(OUTPUT_FORMATS[output_name])
    if filters:
        arguments.extend(["-vf", ",".join(filters)])
    arguments.append(str(output))
    return arguments


def reserve_output_path(folder: Path, base_name: str, suffix: str) -> Path:
    """Atomically claim an unused output filename by creating it empty.

    Tries ``base_name + suffix``, then ``base_name_1 + suffix`` and so on.
    Exclusive creation means a file that appears after the name is chosen is
    never overwritten: FFmpeg's ``-y`` and Pillow's save only ever replace
    this placeholder, and failure cleanup only deletes files we created.
    """
    candidate = folder / f"{base_name}{suffix}"
    number = 1
    while True:
        try:
            candidate.open("xb").close()
        except FileExistsError:
            candidate = folder / f"{base_name}_{number}{suffix}"
            number += 1
        else:
            return candidate


def processed_output_path(source: Path, output_folder: Path, steps: list[dict[str, str]]) -> Path:
    """Reserve an unused processed filename with the workflow's output suffix."""
    output_step = next(
        (
            step
            for step in steps
            if step["operation"] in {"Convert format", "Extract audio"}
        ),
        None,
    )
    suffix = source.suffix
    if output_step is not None:
        suffix = OUTPUT_FORMATS[output_step.get("format", "MP3")]
    return reserve_output_path(output_folder, f"{source.stem}_processed", suffix)


def run_workflow(
    inputs: list[Path],
    output_folder: Path,
    steps: list[dict[str, str]],
    should_cancel: Callable[[], bool] = lambda: False,
) -> list[str]:
    """Run the workflow for each existing input and return per-file outcomes.

    Each destination is reserved before FFmpeg runs, and a failed run removes
    it; failures for one input are reported without preventing later inputs
    from being processed. When should_cancel() turns true, the running FFmpeg
    is stopped, its output removed, and the remaining inputs are skipped.
    """
    ffmpeg = find_tool("ffmpeg")
    output_folder.mkdir(parents=True, exist_ok=True)

    outcomes: list[str] = []
    for source in inputs:
        if should_cancel():
            outcomes.append(f"Cancelled before {source.name}")
            break
        if not source.is_file():
            outcomes.append(f"Skipped {source}: file no longer exists")
            continue
        try:
            destination = processed_output_path(source, output_folder, steps)
        except (OSError, KeyError) as error:
            outcomes.append(f"Failed {source.name}: {error}")
            continue
        try:
            command = build_ffmpeg_command(source, destination, steps, ffmpeg)
            # -y may only ever replace the placeholder reserved above.
            if Path(command[-1]) != destination:
                raise ValueError(f"Output path does not match reserved {destination}.")
            result = run_cancellable(command, timeout=3600, should_cancel=should_cancel)
        except ProcessingCancelled:
            destination.unlink(missing_ok=True)
            outcomes.append(f"Cancelled {source.name}")
            break
        except (OSError, KeyError, ValueError, subprocess.TimeoutExpired) as error:
            destination.unlink(missing_ok=True)
            outcomes.append(f"Failed {source.name}: {error}")
            continue
        if result.returncode != 0:
            destination.unlink(missing_ok=True)
            reason = result.stderr.strip() or "ffmpeg returned an error"
            outcomes.append(f"Failed {source.name}: {reason}")
        else:
            outcomes.append(f"Created {destination}")
    return outcomes
