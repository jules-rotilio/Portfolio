"""Duplicates tab: review duplicate groups, dismiss false positives, trash copies."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.core.database import (
    DEFAULT_DUPLICATE_DISTANCE,
    DEFAULT_DUPLICATE_MIN_FRAMES,
    MediaDatabase,
    MediaRecord,
)
from media_toolkit.core.filesystem import format_size
from media_toolkit.ui.theme import current_theme, theme_manager
from media_toolkit.logging_setup import name_current_thread
from media_toolkit.ui.preview import MediaPreviewWidget

LOGGER = logging.getLogger(__name__)

_DISMISSED_SUFFIX = " (marked not duplicate)"
_GROUP_KEY_ROLE = Qt.ItemDataRole.UserRole
_DISMISSED_ROLE = Qt.ItemDataRole.UserRole + 1


class DuplicateGroupsWorker(QThread):
    """Load duplicate groups and their display data without blocking Qt."""

    completed = Signal(object, object, object, object)

    def __init__(
        self,
        database_path: Path,
        *,
        remove_missing: bool = False,
        distance: int = DEFAULT_DUPLICATE_DISTANCE,
        min_frames: int = DEFAULT_DUPLICATE_MIN_FRAMES,
    ) -> None:
        """Create a catalog refresh task, optionally pruning missing files first."""
        super().__init__()
        self.database_path = database_path
        self.remove_missing = remove_missing
        self.distance = distance
        self.min_frames = min_frames

    def run(self) -> None:
        """Compute the group snapshot and emit either data or an explicit error."""
        name_current_thread("DuplicateGroupsWorker")
        LOGGER.info("Starting duplicate-group refresh")
        try:
            with MediaDatabase(self.database_path) as database:
                removed = (
                    database.remove_missing_media() if self.remove_missing else None
                )
                groups = database.duplicate_groups(
                    include_dismissed=True,
                    distance=self.distance,
                    min_frames=self.min_frames,
                )
                dismissed_keys = database.dismissed_duplicate_group_keys()
                paths = [path for _, group_paths in groups for path in group_paths]
                records = database.cached_records(paths)
        except (OSError, ValueError, sqlite3.Error) as error:
            LOGGER.exception("Duplicate-group refresh failed")
            self.completed.emit([], set(), {}, (None, str(error)))
        else:
            LOGGER.info(
                "Duplicate-group refresh completed: %d group(s), removed %s missing record(s)",
                len(groups),
                removed if removed is not None else "no",
            )
            self.completed.emit(groups, dismissed_keys, records, (removed, ""))


def _style_group_item(item: QTreeWidgetItem, dismissed: bool) -> None:
    """Colour a group row as a duplicate when active, neutral when dismissed."""
    colors = current_theme().statuses["not-indexed" if dismissed else "duplicate"]
    for column in range(item.columnCount()):
        item.setForeground(column, QBrush(QColor(colors.text)))
        item.setBackground(column, QBrush(QColor(colors.background)))


class DuplicatesTab(QWidget):
    """List duplicate groups from a background snapshot of the catalog."""

    # Paths the user asked to move to Trash; the main window confirms and trashes.
    trash_requested = Signal(list)
    status_message = Signal(str)
    # True while a refresh runs; catalog-changing actions elsewhere should pause.
    busy_changed = Signal(bool)
    # duplicate_paths changed, so Explorer status colours need refreshing.
    duplicate_paths_changed = Signal()

    def __init__(self, database: MediaDatabase, parent: QWidget | None = None) -> None:
        """Create the group tree, preview, and group actions."""
        super().__init__(parent)
        self.database = database
        # Similarity thresholds for the next refresh; see set_thresholds.
        self.distance = DEFAULT_DUPLICATE_DISTANCE
        self.min_frames = DEFAULT_DUPLICATE_MIN_FRAMES
        # Members of groups that are not dismissed, as path strings.
        self.duplicate_paths: set[str] = set()
        self._worker: DuplicateGroupsWorker | None = None

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(
            ["Duplicate group / file", "Match", "File size / group total"]
        )
        self.tree.setColumnWidth(0, 600)
        self.tree.setColumnWidth(1, 190)
        self.tree.setColumnWidth(2, 160)
        self.tree.setToolTip("Click Refresh duplicate groups to find duplicate media.")
        self.tree.currentItemChanged.connect(self._on_item_selected)
        self.mark_group_button = QPushButton("Mark group as not duplicate")
        self.mark_group_button.clicked.connect(self._toggle_group_dismissed)
        self.delete_button = QPushButton("Move selected file to Trash")
        self.delete_button.clicked.connect(self._request_trash)
        self.refresh_button = QPushButton("Refresh duplicate groups")
        self.refresh_button.clicked.connect(self.refresh)
        self.preview = MediaPreviewWidget()

        actions = QHBoxLayout()
        actions.addWidget(self.mark_group_button)
        actions.addWidget(self.delete_button)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.tree)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(splitter)
        self._update_actions()
        theme_manager().changed.connect(self._restyle_groups)

    def _restyle_groups(self) -> None:
        """Recolour group rows after the theme changed."""
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            _style_group_item(item, bool(item.data(0, _DISMISSED_ROLE)))

    def is_busy(self) -> bool:
        """Return whether a duplicate-group refresh is running."""
        return self._worker is not None and self._worker.isRunning()

    def stop_background_work(self) -> list[QThread]:
        """Drop a running refresh's result; return the thread to wait for.

        The refresh cannot be interrupted, but it only reads the catalog
        (apart from pruning missing files) and usually ends within seconds.
        """
        if not self.is_busy():
            return []
        assert self._worker is not None
        self._worker.completed.disconnect()
        return [self._worker]

    def refresh(self) -> None:
        """Prune missing files and recompute groups in the background."""
        if self.is_busy():
            return
        self.status_message.emit("Refreshing duplicate groups…")
        worker = DuplicateGroupsWorker(
            self.database.database_path,
            remove_missing=True,
            distance=self.distance,
            min_frames=self.min_frames,
        )
        worker.completed.connect(self._on_refreshed)
        worker.finished.connect(self._on_worker_finished)
        worker.finished.connect(worker.deleteLater)
        worker.start()
        self._worker = worker
        self._update_actions()
        self.busy_changed.emit(True)

    def set_thresholds(self, distance: int, min_frames: int) -> None:
        """Use new similarity thresholds from the next refresh on."""
        self.distance = distance
        self.min_frames = min_frames

    def clear_preview(self) -> None:
        """Stop and clear the duplicate preview."""
        self.preview.clear_preview()

    def forget_paths(self, paths: list[Path]) -> None:
        """Stop treating paths as duplicates, e.g. after they were trashed."""
        self.duplicate_paths.difference_update(str(path) for path in paths)
        self.duplicate_paths_changed.emit()

    def _on_refreshed(
        self,
        groups: list[tuple[str, list[Path]]],
        dismissed_keys: set[str],
        records: dict[str, MediaRecord],
        result: tuple[int | None, str],
    ) -> None:
        """Apply a background snapshot and report any refresh failure."""
        removed, error_message = result
        if error_message:
            LOGGER.error("Duplicate group refresh failed: %s", error_message)
            QMessageBox.warning(self, "Could not refresh duplicate groups", error_message)
            return
        self.duplicate_paths = {
            str(path)
            for group_key, paths in groups
            if group_key not in dismissed_keys
            for path in paths
        }
        self._populate(groups, dismissed_keys, records)
        self.duplicate_paths_changed.emit()
        active_count = sum(group_key not in dismissed_keys for group_key, _ in groups)
        removal_summary = (
            f"; removed {removed} missing media record(s)" if removed is not None else ""
        )
        self.status_message.emit(
            f"Duplicate groups refreshed{removal_summary}; "
            f"{active_count} active group(s) remain."
        )

    def _on_worker_finished(self) -> None:
        """Release the completed worker and re-enable catalog actions."""
        self._worker = None
        self._update_actions()
        self.busy_changed.emit(False)

    def _populate(
        self,
        groups: list[tuple[str, list[Path]]],
        dismissed_keys: set[str],
        records: dict[str, MediaRecord],
    ) -> None:
        """Render duplicate groups with match type, sizes, and member paths."""
        self.tree.clear()
        for number, (group_key, paths) in enumerate(groups, start=1):
            group_records = {
                str(path): records[str(path)] for path in paths if str(path) in records
            }
            exact = len({record.sha256 for record in group_records.values()}) == 1
            dismissed = group_key in dismissed_keys
            total_size = sum(record.size for record in group_records.values())
            label = f"Group {number}: {len(paths)} files"
            if dismissed:
                label += _DISMISSED_SUFFIX
            group_item = QTreeWidgetItem(
                [
                    label,
                    "Exact file match" if exact else "Visually similar media",
                    format_size(total_size),
                ]
            )
            group_item.setData(0, _GROUP_KEY_ROLE, group_key)
            group_item.setData(0, _DISMISSED_ROLE, dismissed)
            _style_group_item(group_item, dismissed)
            for path in paths:
                record = group_records.get(str(path))
                detail = (
                    record.sha256[:16]
                    if exact and record is not None
                    else "Perceptual image match"
                )
                child = QTreeWidgetItem(
                    [str(path), detail, format_size(record.size) if record else "Unavailable"]
                )
                child.setData(0, Qt.ItemDataRole.UserRole, str(path))
                group_item.addChild(child)
            self.tree.addTopLevelItem(group_item)
        self.tree.expandToDepth(1)

    def _selected_group(self) -> QTreeWidgetItem | None:
        """Return the selected group row whether a group or member is selected."""
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.parent() or item

    def _selected_member_path(self) -> Path | None:
        """Return the selected member file, or None for a group row or no selection."""
        item = self.tree.currentItem()
        if item is None or item.parent() is None:
            return None
        path_text = item.data(0, Qt.ItemDataRole.UserRole)
        return Path(path_text) if path_text else None

    def _on_item_selected(self, *_args: object) -> None:
        """Preview the selected member and update the group actions."""
        path = self._selected_member_path()
        if path is None:
            self.preview.clear_preview()
        else:
            record = self.database.cached_records([path]).get(str(path))
            self.preview.show_file(path, record.metadata if record is not None else None)
        self._update_actions()

    def _update_actions(self) -> None:
        """Enable actions for the selection unless a refresh is running."""
        busy = self.is_busy()
        group_item = self._selected_group()
        self.mark_group_button.setEnabled(not busy and group_item is not None)
        if group_item is not None:
            self.mark_group_button.setText(
                "Restore duplicate status"
                if group_item.data(0, _DISMISSED_ROLE)
                else "Mark group as not duplicate"
            )
        self.delete_button.setEnabled(not busy and self._selected_member_path() is not None)
        self.refresh_button.setEnabled(not busy)

    def _toggle_group_dismissed(self) -> None:
        """Dismiss or restore the currently selected duplicate group."""
        group_item = self._selected_group()
        if group_item is None:
            return
        group_key = group_item.data(0, _GROUP_KEY_ROLE)
        if not group_key:
            return
        dismissed = not group_item.data(0, _DISMISSED_ROLE)
        LOGGER.info(
            "%s duplicate group %s", "Dismissing" if dismissed else "Restoring", group_key
        )
        try:
            self.database.set_duplicate_group_dismissed(group_key, dismissed=dismissed)
        except sqlite3.Error as error:
            LOGGER.exception("Could not update duplicate-group dismissal")
            QMessageBox.warning(self, "Could not update duplicate group", str(error))
            return

        group_item.setData(0, _DISMISSED_ROLE, dismissed)
        label = group_item.text(0).removesuffix(_DISMISSED_SUFFIX)
        group_item.setText(0, label + _DISMISSED_SUFFIX if dismissed else label)
        _style_group_item(group_item, dismissed)
        member_paths = {
            group_item.child(index).data(0, Qt.ItemDataRole.UserRole)
            for index in range(group_item.childCount())
        } - {None, ""}
        if dismissed:
            self.duplicate_paths.difference_update(member_paths)
        else:
            self.duplicate_paths.update(member_paths)
        self._update_actions()
        self.duplicate_paths_changed.emit()

    def _request_trash(self) -> None:
        """Ask the main window to trash the selected member file."""
        path = self._selected_member_path()
        if path is not None:
            self.trash_requested.emit([path])
