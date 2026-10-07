"""Media file categories and filesystem scanning/size helpers."""

from __future__ import annotations

import os
from collections.abc import Callable, Collection
from dataclasses import dataclass, field
from pathlib import Path


IMAGE_EXTENSIONS = frozenset({
    ".bmp", ".gif", ".heic", ".jpeg", ".jpg", ".png", ".tif", ".tiff",
    ".webp",
})
VIDEO_EXTENSIONS = frozenset({
    ".3gp", ".avi", ".m4v", ".mkv", ".mov", ".mp4", ".ts", ".webm", ".wmv",
})
AUDIO_EXTENSIONS = frozenset({
    ".aac", ".aiff", ".flac", ".m4a", ".mp3", ".ogg", ".opus", ".wav",
})
MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS


def media_kind(path: Path) -> str | None:
    """Return "image", "video", or "audio" for a supported extension, else None."""
    extension = path.suffix.lower()
    if extension in VIDEO_EXTENSIONS:
        return "video"
    if extension in AUDIO_EXTENSIONS:
        return "audio"
    if extension in IMAGE_EXTENSIONS:
        return "image"
    return None


@dataclass
class DiskUsageNode:
    """One file or directory and its aggregated disk-usage details."""

    path: Path
    size: int
    kind: str
    files: int = 0
    directories: int = 0
    # Subfolders below this node that could not be read and are not counted.
    unreadable: int = 0
    children: list[DiskUsageNode] = field(default_factory=list)


def list_media_files(
    folder: Path, extensions: Collection[str] = MEDIA_EXTENSIONS
) -> list[Path]:
    """Return files below folder with a lowercase extension in extensions.

    Hidden files and folders are skipped and symbolic links to folders are
    not followed. Traversal errors propagate rather than returning a partial
    listing. Results are sorted case-insensitively by path.
    """
    if not folder.is_dir():
        raise NotADirectoryError(folder)

    media: list[Path] = []

    def raise_walk_error(error: OSError) -> None:
        """Propagate traversal errors rather than returning partial results."""
        raise error

    for root, directories, filenames in os.walk(folder, onerror=raise_walk_error):
        directories[:] = [name for name in directories if not name.startswith(".")]
        for filename in filenames:
            path = Path(root, filename)
            if (
                not filename.startswith(".")
                and path.suffix.lower() in extensions
                and path.is_file()
            ):
                media.append(path)

    return sorted(media, key=lambda path: str(path).casefold())


class ScanCancelled(Exception):
    """Raised when a disk-usage scan is stopped on request."""


def build_disk_usage_tree(
    folder: Path, should_cancel: Callable[[], bool] = lambda: False
) -> DiskUsageNode:
    """Build a size tree for a folder, without following symbolic links.

    A subfolder that cannot be read is kept as an empty "Unreadable folder"
    node and counted in ``unreadable`` instead of failing the whole scan; only
    an unreadable top folder raises. Raises ScanCancelled as soon as
    should_cancel() returns True (checked once per folder).
    """
    if not folder.is_dir():
        raise NotADirectoryError(folder)
    return _scan_folder(folder, should_cancel)


def _scan_folder(folder: Path, should_cancel: Callable[[], bool]) -> DiskUsageNode:
    """Recursively total one readable folder; OSError propagates to the caller."""
    if should_cancel():
        raise ScanCancelled(folder)
    node = DiskUsageNode(path=folder, size=0, kind="Folder")
    with os.scandir(folder) as entries:
        for entry in entries:
            path = Path(entry.path)
            try:
                is_folder = entry.is_dir(follow_symlinks=False)
                if not is_folder and not entry.is_file(follow_symlinks=False):
                    continue
                if not is_folder:
                    size = entry.stat(follow_symlinks=False).st_size
            except OSError:
                # The entry vanished or cannot be inspected; leave it out.
                continue
            if is_folder:
                try:
                    child = _scan_folder(path, should_cancel)
                except OSError:
                    child = DiskUsageNode(
                        path=path, size=0, kind="Unreadable folder", unreadable=1
                    )
                node.directories += child.directories + 1
                node.unreadable += child.unreadable
            else:
                child = DiskUsageNode(path=path, size=size, kind="File", files=1)
            node.children.append(child)
            node.size += child.size
            node.files += child.files
    node.children.sort(
        key=lambda child: (child.kind == "File", -child.size, child.path.name.casefold())
    )
    return node


def format_size(size: int) -> str:
    """Format a byte count using binary 1024-based units."""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024:
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"
