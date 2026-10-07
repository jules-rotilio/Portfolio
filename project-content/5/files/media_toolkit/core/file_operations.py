"""Filesystem actions used by the media browser and file-management tools."""

from __future__ import annotations

import random
import shutil
import tempfile
import uuid
from pathlib import Path

from send2trash import send2trash

from media_toolkit.core.filesystem import MEDIA_EXTENSIONS, list_media_files


def create_folder(parent: Path, name: str) -> Path:
    """Create a child folder after rejecting empty or path-like names."""
    name = name.strip()
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Enter a valid folder name without a path.")
    target = parent / name
    target.mkdir()
    return target


def rename_path(source: Path, name: str) -> Path:
    """Rename one path to a validated sibling name without overwriting."""
    name = name.strip()
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("Enter a valid name without a path.")
    target = source.with_name(name)
    if target == source:
        return source
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    source.rename(target)
    return target


def paste_path(source: Path, destination: Path, *, move: bool) -> Path:
    """Copy or move a file, directory, or symlink into a destination folder."""
    if not source.exists() and not source.is_symlink():
        raise FileNotFoundError(source)

    target = destination / source.name
    if target == source:
        raise ValueError("The source is already in this folder.")
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)

    if source.is_dir() and not source.is_symlink():
        try:
            target.resolve().relative_to(source.resolve())
        except ValueError:
            pass
        else:
            raise ValueError("A folder cannot be copied or moved into itself.")

    if move:
        shutil.move(str(source), str(target))
    elif source.is_symlink():
        target.symlink_to(source.readlink(), target_is_directory=source.is_dir())
    elif source.is_dir():
        shutil.copytree(source, target, copy_function=shutil.copy2)
    else:
        shutil.copy2(source, target)
    return target


def copy_random_media(
    source: Path,
    count: int,
    extensions: set[str],
    destination_name: str,
) -> tuple[Path, list[Path]]:
    """Copy up to count randomly selected matching files into <tempdir>/name.

    Duplicate basenames receive numbered suffixes. If any copy fails, remove
    copied files and the new destination directory where possible.
    """
    if not source.is_dir():
        raise NotADirectoryError(source)
    if count < 1:
        raise ValueError("Choose at least one media file.")
    name = destination_name.strip()
    if (
        not name
        or Path(name).name != name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
    ):
        raise ValueError("Enter a valid destination folder name.")
    selected_extensions = {extension.lower() for extension in extensions}
    if not selected_extensions or not selected_extensions <= MEDIA_EXTENSIONS:
        raise ValueError("Select one or more supported media extensions.")

    files = list_media_files(source, selected_extensions)
    if not files:
        raise FileNotFoundError("No matching media files were found.")

    chosen = random.sample(files, min(count, len(files)))
    destination = Path(tempfile.gettempdir()) / name
    destination.mkdir()
    copied: list[Path] = []
    used_names: set[str] = set()
    try:
        for source_path in chosen:
            candidate_name = source_path.name
            suffix = source_path.suffix
            stem = source_path.stem
            number = 1
            while (
                candidate_name.casefold() in used_names
                or (destination / candidate_name).exists()
                or (destination / candidate_name).is_symlink()
            ):
                candidate_name = f"{stem}_{number}{suffix}"
                number += 1
            target = destination / candidate_name
            copied.append(target)
            shutil.copy2(source_path, target)
            used_names.add(candidate_name.casefold())
    except OSError as error:
        cleanup_errors: list[str] = []
        for copied_path in copied:
            try:
                copied_path.unlink(missing_ok=True)
            except OSError as cleanup_error:
                cleanup_errors.append(f"{copied_path.name}: {cleanup_error}")
        try:
            destination.rmdir()
        except OSError as cleanup_error:
            cleanup_errors.append(f"{destination}: {cleanup_error}")
        detail = (
            f" Cleanup also failed: {'; '.join(cleanup_errors)}"
            if cleanup_errors
            else ""
        )
        raise OSError(f"Copy failed: {error}.{detail}") from error
    return destination, copied


def rename_files_with_guids(folder: Path) -> list[tuple[Path, Path]]:
    """Rename regular files to UUID names, restoring originals on failure."""
    if not folder.is_dir():
        raise NotADirectoryError(folder)
    sources = sorted(
        (path for path in folder.iterdir() if path.is_file()),
        key=lambda path: path.name.casefold(),
    )
    if not sources:
        return []

    source_names = {path.name.casefold() for path in sources}
    destinations: dict[Path, Path] = {}
    reserved_names = set(source_names)
    for source in sources:
        while True:
            candidate = source.with_name(f"{uuid.uuid4()}{source.suffix}")
            if (
                candidate.name.casefold() not in reserved_names
                and not candidate.exists()
                and not candidate.is_symlink()
            ):
                destinations[source] = candidate
                reserved_names.add(candidate.name.casefold())
                break

    staged: dict[Path, Path] = {}
    # Include current entries when choosing temporary names for staging.
    reserved_names.update(path.name.casefold() for path in folder.iterdir())
    try:
        # Move sources aside before writing final names so failures can roll back.
        for source in sources:
            while True:
                temporary = source.with_name(f".mediakit-rename-{uuid.uuid4()}.tmp")
                if (
                    temporary.name.casefold() not in reserved_names
                    and not temporary.exists()
                    and not temporary.is_symlink()
                ):
                    reserved_names.add(temporary.name.casefold())
                    break
            source.rename(temporary)
            staged[source] = temporary
        for source in sources:
            staged[source].rename(destinations[source])
    except OSError as error:
        rollback_errors: list[str] = []
        for source, temporary in staged.items():
            current = destinations[source] if destinations[source].exists() else temporary
            if current.exists() and not source.exists():
                try:
                    current.rename(source)
                except OSError as rollback_error:
                    rollback_errors.append(f"{current.name}: {rollback_error}")
        detail = (
            f" Could not restore: {'; '.join(rollback_errors)}"
            if rollback_errors
            else " Original filenames were restored."
        )
        raise OSError(f"Could not rename files: {error}.{detail}") from error

    return [(source, destinations[source]) for source in sources]


def move_to_trash(path: Path) -> None:
    """Send a path to the platform trash/recycle bin."""
    send2trash(str(path))
