"""The main window: hosts the tabs and coordinates what they share."""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.app_settings import AppSettings, load_settings, open_settings, save_settings
from media_toolkit.core.database import MediaDatabase
from media_toolkit.core.file_operations import move_to_trash
from media_toolkit.ui.database_browser import DatabaseBrowser
from media_toolkit.ui.disk_usage_tab import DiskUsageTab
from media_toolkit.ui.duplicates_tab import DuplicatesTab
from media_toolkit.ui.explorer_tab import ExplorerTab
from media_toolkit.ui.quick_process_tab import QuickProcessWidget
from media_toolkit.ui.settings_dialog import SettingsDialog
from media_toolkit.ui.theme import THEME_MODES, theme_manager
from media_toolkit.ui.workflow_tab import WorkflowWidget

LOGGER = logging.getLogger(__name__)
# The bundled tag taxonomy, loaded into an empty catalog on first launch.
DEFAULT_TAXONOMY_PATH = Path(__file__).resolve().parents[2] / "tags.json"


class MainWindow(QMainWindow):
    """Host the feature tabs and coordinate what they share.

    Each tab owns its own widgets and logic. The window routes status
    messages, the Explorer folder and selection, duplicate state, and Trash
    requests between them.
    """

    def __init__(
        self, database: MediaDatabase, settings: QSettings | None = None
    ) -> None:
        """Build all tabs on database and connect their signals.

        settings defaults to the user's MediaToolkit settings; tests pass
        their own so they do not touch it.
        """
        super().__init__()
        self.settings = settings or open_settings()
        self.preferences = load_settings(self.settings)
        theme_manager().set_mode(self.preferences.theme)
        self.setWindowTitle("MediaToolkit")
        self.resize(1000, 650)
        self.database = database
        if not self.database.taxonomy():
            self.database.update_taxonomy(
                json.loads(DEFAULT_TAXONOMY_PATH.read_text(encoding="utf-8"))
            )
        self._quick_process_source: tuple[Path | None, dict[str, Any] | None] = (
            None,
            None,
        )
        self._quick_process_source_pending = False

        self.explorer_tab = ExplorerTab(self.database, self.settings)
        self.disk_usage_tab = DiskUsageTab()
        self.duplicates_tab = DuplicatesTab(self.database)
        self.workflow_widget = WorkflowWidget(self.database)
        self.quick_process_widget = QuickProcessWidget()
        self.database_browser = DatabaseBrowser(self.database.database_path)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.explorer_tab, "Explorer")
        self.tabs.addTab(self.disk_usage_tab, "Disk Usage")
        self.tabs.addTab(self.duplicates_tab, "Duplicates")
        self.tabs.addTab(self.workflow_widget, "Process")
        self.tabs.addTab(self.quick_process_widget, "Quick Process")
        self.tabs.addTab(self.database_browser, "Database")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # Explorer commands sit above the tabs and show only for the Explorer tab.
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.addWidget(self.explorer_tab.controls)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.explorer_tab.status_message.connect(self._show_status)
        self.explorer_tab.folder_changed.connect(self._on_folder_changed)
        self.explorer_tab.media_selected.connect(self._set_quick_process_source)
        self.explorer_tab.trash_requested.connect(self._move_paths_to_trash)
        self.disk_usage_tab.status_message.connect(self._show_status)
        self.disk_usage_tab.trash_requested.connect(self._move_paths_to_trash)
        self.duplicates_tab.status_message.connect(self._show_status)
        self.duplicates_tab.trash_requested.connect(self._move_paths_to_trash)
        self.duplicates_tab.busy_changed.connect(self.explorer_tab.set_catalog_busy)
        self.duplicates_tab.busy_changed.connect(self.disk_usage_tab.set_busy)
        self.duplicates_tab.duplicate_paths_changed.connect(
            lambda: self.explorer_tab.set_duplicate_paths(
                self.duplicates_tab.duplicate_paths
            )
        )

        self._build_menus()
        self.apply_preferences(self.preferences)
        self._show_status("Choose a folder to get started")
        self._load_startup_directory()

    def _build_menus(self) -> None:
        """Create the View menu (theme) and the Settings menu (preferences)."""
        theme_menu = self.menuBar().addMenu("&View").addMenu("Theme")
        self.theme_actions = QActionGroup(self)
        for mode in THEME_MODES:
            action = theme_menu.addAction(mode)
            action.setCheckable(True)
            action.setChecked(mode == theme_manager().mode)
            action.triggered.connect(lambda _checked, mode=mode: self.set_theme_mode(mode))
            self.theme_actions.addAction(action)

        settings_menu = self.menuBar().addMenu("&Settings")
        preferences_action = settings_menu.addAction("Preferences…")
        preferences_action.setShortcut(QKeySequence("Ctrl+,"))
        preferences_action.setMenuRole(QAction.MenuRole.PreferencesRole)
        preferences_action.triggered.connect(self.open_preferences)

        find_shortcut = QShortcut(QKeySequence(QKeySequence.StandardKey.Find), self)
        find_shortcut.activated.connect(self.focus_search)

    def focus_search(self) -> None:
        """Show Explorer and put the cursor in its name filter (Ctrl+F)."""
        self.tabs.setCurrentWidget(self.explorer_tab)
        self.explorer_tab.focus_search()

    def set_theme_mode(self, mode: str) -> None:
        """Apply and remember "System", "Light", or "Dark"."""
        self.apply_preferences(replace(self.preferences, theme=mode), save=True)

    def open_preferences(self) -> None:
        """Show the Preferences dialog and apply the result if accepted."""
        dialog = SettingsDialog(self.preferences, self)
        if dialog.exec() == SettingsDialog.DialogCode.Accepted:
            self.apply_preferences(dialog.settings(), save=True)
            self._show_status("Preferences saved")

    def apply_preferences(self, preferences: AppSettings, *, save: bool = False) -> None:
        """Apply preferences to every tab; save them to the settings store if asked."""
        self.preferences = preferences
        theme_manager().set_mode(preferences.theme)
        for action in self.theme_actions.actions():
            action.setChecked(action.text() == preferences.theme)
        self.explorer_tab.apply_preferences(preferences)
        self.duplicates_tab.set_thresholds(
            preferences.duplicate_distance, preferences.duplicate_min_frames
        )
        if save:
            save_settings(self.settings, preferences)

    def closeEvent(self, event: QCloseEvent) -> None:
        """Stop background threads before the window and its objects go away.

        Running media processing is only stopped after confirmation. Indexing
        stops after the files in progress; everything indexed so far is kept.
        """
        if self.workflow_widget.is_busy() or self.quick_process_widget.is_busy():
            answer = QMessageBox.question(
                self,
                "Stop media processing?",
                "Media processing is still running. Stop it and close MediaToolkit?\n\n"
                "Unfinished output files will be removed.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
        threads = [
            thread
            for tab in (
                self.explorer_tab,
                self.disk_usage_tab,
                self.duplicates_tab,
                self.workflow_widget,
                self.quick_process_widget,
            )
            for thread in tab.stop_background_work()
        ]
        # Drop queued preview probes; ones already running end within seconds.
        QThreadPool.globalInstance().clear()
        if threads:
            LOGGER.info("Waiting for %d background task(s) to stop", len(threads))
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                for thread in threads:
                    thread.wait()
            finally:
                QApplication.restoreOverrideCursor()
            LOGGER.info("Background tasks stopped")
        super().closeEvent(event)

    def _load_startup_directory(self) -> None:
        """Open the saved default folder in Explorer."""
        self.explorer_tab.load_startup_directory()

    def _show_status(self, message: str, log: bool = True) -> None:
        """Display a status message, also logging it unless log is False."""
        if log:
            LOGGER.info("Status: %s", message)
        self.statusBar().showMessage(message)

    def _on_tab_changed(self, index: int) -> None:
        """Refresh the newly shown tab and show Explorer controls only on Explorer."""
        widget = self.tabs.widget(index)
        self.explorer_tab.controls.setVisible(widget is self.explorer_tab)
        if widget is self.disk_usage_tab:
            self.disk_usage_tab.refresh_if_dirty()
        elif widget is self.database_browser:
            self.database_browser.refresh_data()
        elif widget is self.quick_process_widget and self._quick_process_source_pending:
            self._quick_process_source_pending = False
            self.quick_process_widget.set_source(*self._quick_process_source)

    def _on_folder_changed(self, folder: Path) -> None:
        """Point Disk Usage at the Explorer folder, scanning now only if visible."""
        self.disk_usage_tab.set_folder(folder)
        if self.tabs.currentWidget() is self.disk_usage_tab:
            self.disk_usage_tab.refresh()

    def _set_quick_process_source(
        self, path: Path | None, metadata: dict[str, Any] | None = None
    ) -> None:
        """Follow the Explorer selection, probing it only while the tab is shown.

        Loading a source runs ffprobe/FFmpeg, so a hidden Quick Process tab is
        cleared immediately (stopping any playback) and loads on activation.
        """
        self._quick_process_source = (path, metadata)
        if self.tabs.currentWidget() is self.quick_process_widget:
            self._quick_process_source_pending = False
            self.quick_process_widget.set_source(path, metadata)
        else:
            self._quick_process_source_pending = path is not None
            self.quick_process_widget.set_source(None)

    def _move_paths_to_trash(self, paths: list[Path]) -> None:
        """Confirm trashing paths, remove their records, and update every tab."""
        if not paths:
            return
        names = "\n".join(path.name for path in paths[:8])
        if len(paths) > 8:
            names += f"\n…and {len(paths) - 8} more"
        answer = QMessageBox.question(
            self,
            "Move to Trash",
            f"Move {len(paths)} selected item(s) to Trash?\n\n{names}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        errors: list[str] = []
        deleted = 0
        for path in paths:
            try:
                move_to_trash(path)
            except OSError as error:
                LOGGER.exception("Could not move %s to Trash", path)
                errors.append(f"{path.name}: {error}")
                continue
            deleted += 1
            try:
                self.database.remove_path(path)
            except sqlite3.Error as error:
                LOGGER.exception("Could not remove trashed media from catalog: %s", path)
                errors.append(
                    f"{path.name} was trashed, but its indexed data could not be removed: {error}"
                )
        self.explorer_tab.preview.clear_preview()
        self.duplicates_tab.clear_preview()
        self.disk_usage_tab.mark_dirty()
        if self.tabs.currentWidget() is self.disk_usage_tab:
            self.disk_usage_tab.refresh()
        if errors:
            QMessageBox.warning(self, "Some items could not be trashed", "\n".join(errors))
        if deleted:
            # Also refreshes Explorer's status colours.
            self.duplicates_tab.forget_paths(paths)
            self._show_status(f"Moved {deleted} item(s) to Trash")
