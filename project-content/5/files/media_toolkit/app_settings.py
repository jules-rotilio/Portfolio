"""User preferences stored with QSettings, with defaults and allowed ranges."""

from __future__ import annotations

import os
from dataclasses import dataclass, fields

from PySide6.QtCore import QSettings

# Organization and application names for the user's settings file.
SETTINGS_SCOPE = ("MediaToolkit", "MediaToolkit")


@dataclass(frozen=True)
class IntSetting:
    """Range and default for one integer preference."""

    default: int
    minimum: int
    maximum: int


# Allowed values for each integer preference, keyed by AppSettings field name.
INT_SETTINGS = {
    "thumbnail_size": IntSetting(160, 96, 320),
    "index_threads": IntSetting(min(8, os.cpu_count() or 1), 1, max(1, os.cpu_count() or 1)),
    # Differing bits allowed between two 64-bit image hashes (0 = identical).
    "duplicate_distance": IntSetting(8, 0, 16),
    # Sampled video/GIF frames (of 10) that must match for a duplicate.
    "duplicate_min_frames": IntSetting(4, 1, 10),
    "log_files_kept": IntSetting(20, 1, 500),
}


@dataclass(frozen=True)
class AppSettings:
    """All user preferences; each integer is kept within INT_SETTINGS."""

    theme: str = "System"
    thumbnail_size: int = INT_SETTINGS["thumbnail_size"].default
    index_threads: int = INT_SETTINGS["index_threads"].default
    duplicate_distance: int = INT_SETTINGS["duplicate_distance"].default
    duplicate_min_frames: int = INT_SETTINGS["duplicate_min_frames"].default
    log_files_kept: int = INT_SETTINGS["log_files_kept"].default


def open_settings() -> QSettings:
    """Return the user's MediaToolkit settings store."""
    return QSettings(*SETTINGS_SCOPE)


def load_settings(store: QSettings) -> AppSettings:
    """Read preferences, replacing missing or out-of-range values with defaults."""
    values: dict[str, object] = {"theme": str(store.value("theme", "System"))}
    for field in fields(AppSettings):
        rule = INT_SETTINGS.get(field.name)
        if rule is None:
            continue
        try:
            value = int(store.value(field.name, rule.default))
        except (TypeError, ValueError):
            value = rule.default
        values[field.name] = value if rule.minimum <= value <= rule.maximum else rule.default
    return AppSettings(**values)  # type: ignore[arg-type]


def save_settings(store: QSettings, settings: AppSettings) -> None:
    """Write every preference to store."""
    for field in fields(AppSettings):
        store.setValue(field.name, getattr(settings, field.name))
    store.sync()
