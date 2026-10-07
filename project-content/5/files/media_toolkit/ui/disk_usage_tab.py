"""Disk Usage tab: folder sizes, file counts, and trashing selected entries."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtWidgets import (
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.ui.background import BackgroundCalls
from media_toolkit.core.filesystem import DiskUsageNode, build_disk_usage_tree, format_size

LOGGER = logging.getLogger(__name__)

_PATH_ROLE = Qt.ItemDataRole.UserRole
# The DiskUsageNode whose children are added when the row is first expanded.
_NODE_ROLE = Qt.ItemDataRole.UserRole + 1


class DiskUsageTab(QWidget):
    """Show a size tree for the Explorer folder, rebuilt lazily when stale.

    The folder is scanned in the background, and rows are created only when
    their parent is expanded, so large folders keep the window responsive.
    """

    # Paths the user asked to move to Trash; the main window confirms and trashes.
    trash_requested = Signal(list)
    status_message = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the tree and its Trash button."""
        super().__init__(parent)
        self._folder: Path | None = None
        self._dirty = True
        self._busy = False
        self._scan_cancel: threading.Event | None = None
        self._background = BackgroundCalls(self)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size", "Type", "Files", "Folders"])
        self.tree.setColumnWidth(0, 340)
        self.tree.currentItemChanged.connect(self._update_delete_button)
        self.tree.itemExpanded.connect(self._add_child_rows)
        self.delete_button = QPushButton("Move selected item to Trash")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._request_trash)

        layout = QVBoxLayout(self)
        layout.addWidget(self.delete_button)
        layout.addWidget(self.tree)

    def set_folder(self, folder: Path) -> None:
        """Track the Explorer folder; the tree is rebuilt on the next refresh."""
        self._folder = folder
        self._dirty = True
        self._update_delete_button()

    def mark_dirty(self) -> None:
        """Note that files changed, so the next refresh_if_dirty rebuilds."""
        self._dirty = True

    def refresh_if_dirty(self) -> None:
        """Rebuild the tree only if the folder or its contents changed."""
        if self._dirty:
            self.refresh()

    def is_scanning(self) -> bool:
        """Return whether a background scan is in progress."""
        return self._scan_cancel is not None

    def set_busy(self, busy: bool) -> None:
        """Disable trashing while a catalog snapshot is being computed."""
        self._busy = busy
        self._update_delete_button()

    def stop_background_work(self) -> list[QThread]:
        """Cancel a running scan; it stops at its next folder (no thread to wait for)."""
        self._cancel_scan()
        return []

    def refresh(self) -> None:
        """Start scanning the current folder, replacing any scan in progress."""
        if self._folder is None:
            return
        self._cancel_scan()
        folder = self._folder
        cancel = threading.Event()
        self._scan_cancel = cancel
        self._dirty = False
        self.tree.clear()
        self.tree.addTopLevelItem(QTreeWidgetItem([f"Scanning {folder}…"]))
        self._update_delete_button()
        self.status_message.emit(f"Scanning disk usage of {folder}…")
        self._background.submit(
            "scan",
            lambda: build_disk_usage_tree(folder, should_cancel=cancel.is_set),
            self._show_tree,
            lambda error: self._show_scan_error(folder, error),
        )

    def _cancel_scan(self) -> None:
        """Stop the running scan, if any, and drop its result."""
        if self._scan_cancel is not None:
            self._scan_cancel.set()
            self._scan_cancel = None
        self._background.cancel("scan")

    def _show_tree(self, tree: DiskUsageNode) -> None:
        """Display a finished scan with the top two levels expanded."""
        self._scan_cancel = None
        self.tree.clear()
        root_item = self._make_tree_item(tree)
        self.tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
        for index in range(root_item.childCount()):
            root_item.child(index).setExpanded(True)
        self._update_delete_button()
        message = (
            f"{format_size(tree.size)} used by {tree.files} files "
            f"in {tree.directories} folders"
        )
        if tree.unreadable:
            message += f"; {tree.unreadable} folder(s) could not be read"
        self.status_message.emit(message)

    def _show_scan_error(self, folder: Path, error: Exception) -> None:
        """Report a scan that failed before producing a tree."""
        self._scan_cancel = None
        self._dirty = True
        self.tree.clear()
        self._update_delete_button()
        LOGGER.error(
            "Could not calculate disk usage for %s",
            folder,
            exc_info=(type(error), error, error.__traceback__),
        )
        QMessageBox.critical(self, "Could not scan disk usage", str(error))

    def _make_tree_item(self, node: DiskUsageNode) -> QTreeWidgetItem:
        """Create the row for one node; its children are added on expansion."""
        item = QTreeWidgetItem(
            [
                node.path.name or str(node.path),
                format_size(node.size),
                node.kind,
                str(node.files),
                str(node.directories),
            ]
        )
        item.setData(0, _PATH_ROLE, str(node.path))
        if node.children:
            item.setData(0, _NODE_ROLE, node)
            item.setChildIndicatorPolicy(
                QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator
            )
        return item

    def _add_child_rows(self, item: QTreeWidgetItem) -> None:
        """Create a folder's child rows the first time it is expanded."""
        node = item.data(0, _NODE_ROLE)
        if node is None or item.childCount():
            return
        item.addChildren([self._make_tree_item(child) for child in node.children])

    def _selected_path(self) -> Path | None:
        """Return the selected row's path, or None if nothing is selected."""
        item = self.tree.currentItem()
        path_text = item.data(0, _PATH_ROLE) if item is not None else None
        return Path(path_text) if path_text else None

    def _update_delete_button(self, *_args: object) -> None:
        """Allow trashing any selected entry except the scanned folder itself."""
        path = self._selected_path()
        self.delete_button.setEnabled(
            not self._busy and path is not None and path != self._folder
        )

    def _request_trash(self) -> None:
        """Ask the main window to trash the selected entry."""
        path = self._selected_path()
        if path is not None:
            self.trash_requested.emit([path])
