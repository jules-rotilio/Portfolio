"""Locate FFmpeg tools and run ffprobe/ffmpeg with consistent error handling."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

# Leading ffmpeg options shared by every command: quiet output, no prompts.
FFMPEG_QUIET_ARGS = ("-hide_banner", "-loglevel", "error", "-nostdin")
FFPROBE_TIMEOUT_SECONDS = 8
# How often a running command checks whether it should be cancelled.
_CANCEL_POLL_SECONDS = 0.2


class ProcessingCancelled(Exception):
    """Raised when a running command was stopped on request."""


def find_tool(name: str) -> str:
    """Return the path of an FFmpeg program on PATH, or raise FileNotFoundError."""
    path = shutil.which(name)
    if path is None:
        raise FileNotFoundError(
            f"{name} was not found; install FFmpeg and make sure it is on PATH."
        )
    return path


def run_ffprobe(
    path: Path, *arguments: str, timeout: float = FFPROBE_TIMEOUT_SECONDS
) -> dict[str, Any]:
    """Run ffprobe with arguments and JSON output on path; return the parsed data.

    Raises FileNotFoundError when ffprobe is missing, and RuntimeError when it
    cannot run, times out, rejects the file, or prints invalid JSON.
    """
    ffprobe = find_tool("ffprobe")
    try:
        result = subprocess.run(
            [ffprobe, "-v", "error", *arguments, "-of", "json", "--", str(path)],
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("Media inspection timed out.") from error
    except OSError as error:
        raise RuntimeError(f"Could not run ffprobe: {error}") from error
    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip() or "Unsupported or unreadable media file."
        )
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("ffprobe returned invalid metadata.") from error
    if not isinstance(data, dict):
        raise RuntimeError("ffprobe returned invalid metadata.")
    return data


def run_cancellable(
    command: list[str],
    *,
    timeout: float,
    should_cancel: Callable[[], bool],
) -> subprocess.CompletedProcess[str]:
    """Run command like subprocess.run(capture_output=True, text=True).

    The process is killed, and ProcessingCancelled raised, as soon as
    should_cancel() returns True; it is killed and subprocess.TimeoutExpired
    raised once timeout seconds have passed.
    """
    deadline = time.monotonic() + timeout
    with subprocess.Popen(
        command,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ) as process:
        while True:
            try:
                stdout, stderr = process.communicate(timeout=_CANCEL_POLL_SECONDS)
            except subprocess.TimeoutExpired:
                cancelled = should_cancel()
                if cancelled or time.monotonic() >= deadline:
                    process.kill()
                    process.communicate()
                    if cancelled:
                        raise ProcessingCancelled("Processing was cancelled.") from None
                    raise subprocess.TimeoutExpired(command, timeout) from None
            else:
                return subprocess.CompletedProcess(
                    command, process.returncode, stdout, stderr
                )
