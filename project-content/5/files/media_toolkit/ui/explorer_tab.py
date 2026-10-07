"""Explorer tab: browse folders, manage files and tags, and index media."""

from __future__ import annotations

import json
import logging
import sqlite3
import tempfile
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import (
    QAbstractItemModel,
    QDir,
    QItemSelection,
    QModelIndex,
    QPoint,
    QSettings,
    QSize,
    Qt,
    QThread,
    QUrl,
    Signal,
)
from PySide6.QtGui import QAction, QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFileSystemModel,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListView,
    QMenu,
    QMessageBox,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QToolButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.app_settings import INT_SETTINGS, AppSettings
from media_toolkit.core.database import MediaDatabase, MediaRecord
from media_toolkit.core.file_operations import (
    copy_random_media,
    create_folder,
    paste_path,
    rename_files_with_guids,
    rename_path,
)
from media_toolkit.core.filesystem import MEDIA_EXTENSIONS
from media_toolkit.core.tag_query import TagQuery
from media_toolkit.ui.background import BackgroundCalls
from media_toolkit.ui.catalog_results import CatalogResultsModel, ResultRow, find_catalog_matches
from media_toolkit.ui.filter_model import (
    CATEGORY_EXTENSIONS,
    PATH_ROLE,
    ExplorerFilterProxyModel,
    status_legend_html,
)
from media_toolkit.ui.index_worker import INDEX_THREADS, IndexWorker
from media_toolkit.ui.preview import MediaPreviewWidget
from media_toolkit.ui.tag_editor import TagEditorDialog
from media_toolkit.ui.tag_filter import TagFilterButton
from media_toolkit.ui.theme import theme_manager
from media_toolkit.ui.thumbnails import ThumbnailCache, ThumbnailDelegate
from media_toolkit.core.xdg_tags import write_xdg_tags

DEFAULT_DIRECTORY = Path.home()
LOGGER = logging.getLogger(__name__)


def _is_media_file(path: Path) -> bool:
    """Return whether path is an existing file with a supported media extension."""
    return path.suffix.lower() in MEDIA_EXTENSIONS and path.is_file()


class ExplorerTab(QWidget):
    """Folder tree, file list, and preview, plus the Explorer toolbar.

    The toolbar is a separate widget, ``controls``, which the main window
    places above its tabs and shows only while this tab is active.
    """

    # (message, log): text for the status bar and whether to log it.
    status_message = Signal(str, bool)
    # The folder now shown, as a Path.
    folder_changed = Signal(object)
    # (Path or None, metadata or None) for the selected media file.
    media_selected = Signal(object, object)
    # Paths the user asked to move to Trash; the main window confirms and trashes.
    trash_requested = Signal(list)

    def __init__(
        self,
        database: MediaDatabase,
        settings: QSettings,
        parent: QWidget | None = None,
    ) -> None:
        """Build the browser, toolbar, and file actions."""
        super().__init__(parent)
        self.database = database
        self.settings = settings
        self.current_folder: Path | None = None
        self.index_worker: IndexWorker | None = None
        self._duplicate_paths: set[str] = set()
        self._catalog_busy = False
        self._syncing_folder_tree = False
        self._history: list[Path] = []
        self._history_index = -1
        self._clipboard_paths: list[Path] = []
        self._clipboard_mode = "copy"
        # Files indexed at once; see apply_preferences.
        self.index_threads = INDEX_THREADS

        self._build_controls()
        self._build_browser()
        self._update_navigation_buttons()
        self._update_action_states()

    def _build_controls(self) -> None:
        """Create the toolbar: location on top, actions and filters below."""
        self.new_folder_action = self._create_action("New folder…", "Ctrl+Shift+N", self.create_new_folder)
        self.rename_action = self._create_action("Rename…", "F2", self.rename_selected)
        self.cut_action = self._create_action("Cut", "Ctrl+X", self.cut_selected)
        self.copy_action = self._create_action("Copy", "Ctrl+C", self.copy_selected)
        self.paste_action = self._create_action("Paste", "Ctrl+V", self.paste_into_folder)
        self.delete_action = self._create_action("Move to Trash", "Delete", self.delete_selected)
        self.tag_action = self._create_action("Edit tags…", "Ctrl+T", self.edit_selected_tags)
        self.index_action = self._create_action(
            "Index folder",
            "",
            self.start_indexing,
            tooltip="Index this folder and its subfolders for tags and duplicate "
            "detection, then refresh the Duplicates tab",
        )
        self.load_tags_action = self._create_action(
            "Load tags.json…", "", self.load_tag_taxonomy
        )
        self.copy_random_media_action = self._create_action(
            "Copy random media…", "", self.copy_random_media_from_folder
        )
        self.rename_guid_action = self._create_action(
            "Rename files with GUIDs…", "", self.rename_current_folder_files_with_guids
        )
        # Actions for the selected files, also in the context menu and shortcuts.
        self._file_actions = (
            self.new_folder_action,
            self.rename_action,
            self.cut_action,
            self.copy_action,
            self.paste_action,
            self.delete_action,
            self.tag_action,
        )

        self.controls = QWidget()
        controls_layout = QVBoxLayout(self.controls)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(6)

        # Row 1: where you are.
        self.back_button = self._nav_button("←", "Back", "Alt+Left", self.go_back)
        self.forward_button = self._nav_button("→", "Forward", "Alt+Right", self.go_forward)
        self.up_button = self._nav_button("↑", "Up to the parent folder", "Alt+Up", self.go_up)
        self.folder_input = QLineEdit()
        self.folder_input.setPlaceholderText("Folder path; press Enter to open")
        self.folder_input.returnPressed.connect(self.load_folder_from_input)
        go_button = QToolButton()
        go_button.setText("Go")
        go_button.setToolTip("Open the folder typed in the path field")
        go_button.clicked.connect(self.load_folder_from_input)
        browse_button = QToolButton()
        browse_button.setText("Browse…")
        browse_button.setToolTip("Choose a folder in a dialog")
        browse_button.clicked.connect(self.choose_folder)
        self.set_default_directory_button = QToolButton()
        self.set_default_directory_button.setText("Set as start folder")
        self.set_default_directory_button.setToolTip(
            "Open this folder when MediaToolkit starts"
        )
        self.set_default_directory_button.setEnabled(False)
        self.set_default_directory_button.clicked.connect(
            self.set_current_folder_as_default
        )
        location_row = QHBoxLayout()
        for widget in (self.back_button, self.forward_button, self.up_button):
            location_row.addWidget(widget)
        location_row.addWidget(self.folder_input, stretch=1)
        for widget in (go_button, browse_button, self.set_default_directory_button):
            location_row.addWidget(widget)
        controls_layout.addLayout(location_row)

        # Row 2: what you can do, then how the list is filtered.
        actions_row = QHBoxLayout()
        for action in (
            self.new_folder_action,
            self.rename_action,
            self.cut_action,
            self.copy_action,
            self.paste_action,
        ):
            actions_row.addWidget(self._action_button(action))
        actions_row.addWidget(self._action_button(self.delete_action, "dangerButton"))
        actions_row.addWidget(self._separator())
        actions_row.addWidget(self._action_button(self.tag_action))
        actions_row.addWidget(self._action_button(self.index_action, "primaryButton"))
        more_button = QToolButton()
        more_button.setText("More")
        more_button.setToolTip("Less frequent folder and catalog commands")
        more_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        more_menu = QMenu(more_button)
        more_menu.addAction(self.load_tags_action)
        more_menu.addSeparator()
        more_menu.addAction(self.copy_random_media_action)
        more_menu.addAction(self.rename_guid_action)
        more_button.setMenu(more_menu)
        actions_row.addWidget(more_button)
        actions_row.addStretch(1)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by name (Ctrl+F)")
        self.search_input.setToolTip("Show only names containing this text; Esc clears it")
        self.search_input.setClearButtonEnabled(True)
        clear_search = QShortcut(QKeySequence(Qt.Key.Key_Escape), self.search_input)
        clear_search.setContext(Qt.ShortcutContext.WidgetShortcut)
        clear_search.activated.connect(self.search_input.clear)
        self.search_input.setMinimumWidth(180)
        self.search_input.textChanged.connect(self._on_search_changed)
        self.tag_filter = TagFilterButton()
        self.tag_filter.set_taxonomy(self.database.taxonomy())
        self.tag_filter.query_changed.connect(self._on_tag_query_changed)
        self.category_filter = QComboBox()
        self.category_filter.addItems(["All files", *CATEGORY_EXTENSIONS])
        self.category_filter.setToolTip("Show only this type of file")
        self.category_filter.currentTextChanged.connect(self._on_category_changed)
        actions_row.addWidget(self.search_input, stretch=1)
        actions_row.addWidget(self.tag_filter)
        actions_row.addWidget(self.category_filter)
        actions_row.addWidget(self._separator())
        self.list_view_button = QToolButton()
        self.list_view_button.setText("List")
        self.list_view_button.setToolTip("Show files as a detailed list")
        self.grid_view_button = QToolButton()
        self.grid_view_button.setText("Grid")
        self.grid_view_button.setToolTip("Show files as a grid of thumbnails")
        self.view_mode_buttons = QButtonGroup(self)
        for button in (self.list_view_button, self.grid_view_button):
            button.setCheckable(True)
            self.view_mode_buttons.addButton(button)
            actions_row.addWidget(button)
        self.list_view_button.setChecked(True)
        self.grid_view_button.toggled.connect(self._on_view_mode_toggled)
        controls_layout.addLayout(actions_row)

    def _nav_button(
        self, glyph: str, tooltip: str, shortcut: str, callback: Callable[[], None]
    ) -> QToolButton:
        """Create a compact history/navigation button with a shortcut."""
        button = QToolButton()
        button.setObjectName("navButton")
        button.setText(glyph)
        button.setShortcut(QKeySequence(shortcut))
        shortcut_text = QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)
        button.setToolTip(f"{tooltip} ({shortcut_text})")
        button.clicked.connect(callback)
        return button

    @staticmethod
    def _action_button(action: QAction, object_name: str = "") -> QToolButton:
        """Create a button that mirrors an action's text, tooltip, and enabled state."""
        button = QToolButton()
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        if object_name:
            button.setObjectName(object_name)
        return button

    @staticmethod
    def _separator() -> QFrame:
        """Create a thin vertical line between groups of toolbar buttons."""
        line = QFrame()
        line.setObjectName("toolbarSeparator")
        line.setFixedWidth(1)
        line.setFrameShape(QFrame.Shape.NoFrame)
        return line

    def _build_browser(self) -> None:
        """Create the folder tree, the filtered file list, and the preview."""
        self.folder_model = QFileSystemModel(self)
        self.folder_model.setFilter(QDir.Filter.AllDirs | QDir.Filter.NoDotAndDotDot)
        self.folder_tree = QTreeView()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setAnimated(True)
        self.folder_tree.setModel(self.folder_model)
        for column in range(1, self.folder_model.columnCount()):
            self.folder_tree.hideColumn(column)

        # The proxy adds search/type filtering and database-backed row colors.
        self.file_model = QFileSystemModel(self)
        self.file_model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.filter_model = ExplorerFilterProxyModel(self)
        self.filter_model.setSourceModel(self.file_model)
        self.file_view = QTreeView()
        self.file_view.setModel(self.filter_model)
        self.file_view.setRootIsDecorated(False)
        self.file_view.setItemsExpandable(False)
        self.file_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.file_view.setSortingEnabled(True)
        self.file_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        for column, width in enumerate((280, 100, 140, 160)):
            self.file_view.setColumnWidth(column, width)

        # Grid mode shows the same model with thumbnails; both views share
        # one selection model (see _set_content_model).
        self.thumbnail_cache = ThumbnailCache(INT_SETTINGS["thumbnail_size"].default, self)
        self.grid_view = QListView()
        self.grid_view.setViewMode(QListView.ViewMode.IconMode)
        self.grid_view.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid_view.setMovement(QListView.Movement.Static)
        self.grid_view.setUniformItemSizes(True)
        self.grid_view.setWordWrap(True)
        self.grid_view.setSpacing(6)
        self.grid_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # Whole rows, like the list: selected_paths() reads fully selected rows.
        self.grid_view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.grid_view.setSelectionRectVisible(True)
        self.grid_view.setItemDelegate(ThumbnailDelegate(self.thumbnail_cache, self.grid_view))
        self.thumbnail_cache.ready.connect(self.grid_view.viewport().update)
        self._apply_thumbnail_size()

        # Whole-catalog tag searches are listed by their own model.
        self.results_model = CatalogResultsModel(self)
        self._catalog_mode = False
        self._background = BackgroundCalls(self)
        self.results_banner = QLabel()
        self.results_banner.setObjectName("mutedLabel")
        self.results_banner.setWordWrap(True)
        back_to_folder = QToolButton()
        back_to_folder.setText("Back to folder")
        back_to_folder.setToolTip("Leave the catalog search and show the current folder")
        back_to_folder.clicked.connect(lambda: self.tag_filter.panel.set_whole_catalog(False))
        banner_row = QHBoxLayout()
        banner_row.setContentsMargins(0, 0, 0, 0)
        banner_row.addWidget(self.results_banner, stretch=1)
        banner_row.addWidget(back_to_folder)
        self.results_bar = QWidget()
        self.results_bar.setLayout(banner_row)
        self.results_bar.hide()

        self.view_stack = QStackedWidget()
        self.view_stack.addWidget(self.file_view)
        self.view_stack.addWidget(self.grid_view)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.results_bar)
        content_layout.addWidget(self.view_stack, stretch=1)

        self.preview = MediaPreviewWidget()
        browser = QSplitter(Qt.Orientation.Horizontal)
        browser.addWidget(self.folder_tree)
        browser.addWidget(content)
        browser.setStretchFactor(0, 1)
        browser.setStretchFactor(1, 3)
        browser_and_preview = QSplitter(Qt.Orientation.Horizontal)
        browser_and_preview.addWidget(browser)
        browser_and_preview.addWidget(self.preview)
        browser_and_preview.setStretchFactor(0, 3)
        browser_and_preview.setStretchFactor(1, 2)
        self.status_legend = QLabel(status_legend_html())
        self.status_legend.setToolTip("Row colours in the file list")
        self.scan_progress = QProgressBar()
        self.scan_progress.setRange(0, 100)
        self.scan_progress.setMaximumWidth(320)
        self.scan_progress.hide()
        footer = QHBoxLayout()
        footer.addWidget(self.status_legend)
        footer.addStretch(1)
        footer.addWidget(self.scan_progress)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(browser_and_preview, stretch=1)
        layout.addLayout(footer)
        theme_manager().changed.connect(self._on_theme_changed)

        self.folder_tree.selectionModel().currentChanged.connect(self._on_folder_selected)
        for view in (self.file_view, self.grid_view):
            view.activated.connect(self._on_file_activated)
            view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            view.customContextMenuRequested.connect(
                lambda position, view=view: self._show_file_context_menu(view, position)
            )
            for action in self._file_actions:
                view.addAction(action)
        for action in self._file_actions:
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._set_content_model(self.filter_model)
        self.file_model.directoryLoaded.connect(self.refresh_statuses)
        if self.settings.value("explorer_view", "list") == "grid":
            self.grid_view_button.setChecked(True)

    def _create_action(
        self,
        text: str,
        shortcut: str,
        callback: Callable[[], None],
        *,
        tooltip: str = "",
    ) -> QAction:
        """Create a reusable action for buttons, menus, and keyboard shortcuts."""
        action = QAction(text, self)
        action.setShortcut(QKeySequence(shortcut))
        tooltip = tooltip or text.rstrip("…")
        if shortcut:
            native = QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.NativeText)
            tooltip += f" ({native})"
        action.setToolTip(tooltip)
        action.triggered.connect(callback)
        return action

    def _on_theme_changed(self) -> None:
        """Repaint status colours for the new theme."""
        self.status_legend.setText(status_legend_html())
        self.filter_model.refresh_colors()
        self.results_model.refresh_colors()

    def _show_status(self, message: str, *, log: bool = True) -> None:
        """Send a status-bar message to the main window."""
        self.status_message.emit(message, log)

    # Shared state from other tabs -------------------------------------------

    def set_duplicate_paths(self, paths: set[str]) -> None:
        """Use paths of active duplicate groups for the red status colour."""
        self._duplicate_paths = set(paths)
        self.refresh_statuses()

    def set_catalog_busy(self, busy: bool) -> None:
        """Pause catalog-changing actions while a duplicate snapshot is computed."""
        self._catalog_busy = busy
        self._update_action_states()

    def focus_search(self) -> None:
        """Move keyboard focus to the name filter, selecting its text."""
        self.search_input.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_input.selectAll()

    def apply_preferences(self, preferences: AppSettings) -> None:
        """Use the user's indexing and thumbnail preferences."""
        self.index_threads = preferences.index_threads
        self.thumbnail_cache.set_size(preferences.thumbnail_size)
        self._apply_thumbnail_size()

    def is_indexing(self) -> bool:
        """Return whether the background indexer is running."""
        return self.index_worker is not None and self.index_worker.isRunning()

    def stop_background_work(self) -> list[QThread]:
        """Stop indexing without reporting back; return the thread to wait for.

        Records indexed so far are saved, so the next scan resumes from them.
        """
        self.thumbnail_cache.forget_pending()
        self._background.cancel_all()
        if self.index_worker is None or not self.index_worker.isRunning():
            return []
        self.index_worker.progress.disconnect()
        self.index_worker.completed.disconnect()
        self.index_worker.requestInterruption()
        return [self.index_worker]

    # Selection and action state ---------------------------------------------

    def selected_paths(self) -> list[Path]:
        """Return the paths of the selected rows in the visible list or grid."""
        return [
            Path(index.data(PATH_ROLE))
            for index in self.file_view.selectionModel().selectedRows(0)
            if index.data(PATH_ROLE)
        ]

    def active_view(self) -> QAbstractItemView:
        """Return the list or grid view currently shown."""
        return self.grid_view if self.grid_view_button.isChecked() else self.file_view

    def _set_content_model(self, model: QAbstractItemModel) -> None:
        """Show model in both views, sharing one selection between them."""
        old_selection = self.file_view.selectionModel()
        self.file_view.setModel(model)
        self.grid_view.setModel(model)
        replaced_grid_selection = self.grid_view.selectionModel()
        selection = self.file_view.selectionModel()
        self.grid_view.setSelectionModel(selection)
        for stale in (old_selection, replaced_grid_selection):
            if stale is not None and stale is not selection:
                stale.deleteLater()
        selection.currentChanged.connect(self._on_file_selected)
        selection.selectionChanged.connect(self._on_file_selection_changed)
        self.preview.clear_preview()
        self._update_action_states()

    def _on_view_mode_toggled(self, grid: bool) -> None:
        """Switch between the detailed list and the thumbnail grid."""
        self.view_stack.setCurrentWidget(self.grid_view if grid else self.file_view)
        self.settings.setValue("explorer_view", "grid" if grid else "list")
        if not grid:
            self.thumbnail_cache.forget_pending()

    def _apply_thumbnail_size(self) -> None:
        """Size grid cells for the current thumbnail size."""
        size = self.thumbnail_cache.size
        line = self.grid_view.fontMetrics().height()
        self.grid_view.setIconSize(QSize(size, size))
        self.grid_view.setGridSize(QSize(size + 28, size + 2 * line + 20))
        self.grid_view.viewport().update()

    def _on_file_selection_changed(
        self, selected: QItemSelection, deselected: QItemSelection
    ) -> None:
        """Recalculate which file operations apply after a selection change."""
        if selected.isEmpty() and deselected.isEmpty():
            return
        self._update_action_states()

    def _update_action_states(self) -> None:
        """Enable operations for the selection; catalog changes wait while busy."""
        busy = self._catalog_busy
        paths = self.selected_paths()
        self.rename_action.setEnabled(not busy and len(paths) == 1)
        self.copy_action.setEnabled(bool(paths))
        self.cut_action.setEnabled(bool(paths))
        self.delete_action.setEnabled(not busy and bool(paths))
        self.tag_action.setEnabled(
            not busy
            and any(_is_media_file(path) for path in paths)
            and bool(self.database.taxonomy())
        )
        in_folder = not self._catalog_mode
        self.new_folder_action.setEnabled(in_folder)
        self.paste_action.setEnabled(not busy and in_folder and bool(self._clipboard_paths))
        self.index_action.setEnabled(not busy and not self.is_indexing())
        self.rename_guid_action.setEnabled(not busy)

    def _show_file_context_menu(self, view: QAbstractItemView, position: QPoint) -> None:
        """Show the same file actions as the toolbar at the pointer location."""
        index = view.indexAt(position)
        if index.isValid() and not view.selectionModel().isSelected(index):
            view.setCurrentIndex(index)
        menu = QMenu(self)
        paths = self.selected_paths()
        if self._catalog_mode and len(paths) == 1:
            open_folder = menu.addAction("Show in folder")
            open_folder.triggered.connect(lambda: self.show_in_folder(paths[0]))
            menu.addSeparator()
        for action in self._file_actions:
            menu.addAction(action)
        menu.exec(view.viewport().mapToGlobal(position))

    def show_in_folder(self, path: Path) -> None:
        """Leave the catalog search, open path's folder, and select path."""
        self.tag_filter.panel.set_whole_catalog(False)
        self.load_folder(path.parent)
        index = self.filter_model.mapFromSource(self.file_model.index(str(path)))
        if index.isValid():
            self.active_view().setCurrentIndex(index)

    # Filtering and status colours --------------------------------------------

    def _on_search_changed(self, text: str) -> None:
        """Apply a filename query and update the file list."""
        self.filter_model.set_search_text(text)
        if self._catalog_mode:
            self._search_catalog(self.tag_filter.query())
        else:
            self._set_file_root()

    def _on_tag_query_changed(self, query: TagQuery) -> None:
        """Filter this folder by tags, or search the whole catalog."""
        self.filter_model.set_tag_query(query)
        if query.active and query.whole_catalog:
            self._search_catalog(query)
            return
        if self._catalog_mode:
            self._leave_catalog_mode()
        self._set_file_root()
        if query.active:
            shown = self.filter_model.rowCount(self.file_view.rootIndex())
            self._show_status(f"Showing {shown} file(s) with {query.describe()}", log=False)
        else:
            self._show_status("Tag filter cleared", log=False)

    def _search_catalog(self, query: TagQuery) -> None:
        """Run a whole-catalog tag search in the background and list the results."""
        self.results_banner.setText(f"Searching the whole catalog for files with {query.describe()}…")
        self.results_bar.show()
        duplicate_paths = set(self._duplicate_paths)
        self._background.submit(
            "catalog-search",
            lambda: find_catalog_matches(self.database, query, duplicate_paths),
            lambda rows: self._show_catalog_results(query, rows),
            lambda error: self._show_status(f"Catalog search failed: {error}"),
        )

    def _show_catalog_results(self, query: TagQuery, rows: list[ResultRow]) -> None:
        """Show search results in place of the folder contents."""
        name_filter = self.search_input.text().casefold().strip()
        allowed = CATEGORY_EXTENSIONS.get(self.category_filter.currentText())
        rows = [
            row for row in rows
            if (not name_filter or name_filter in row.name.casefold())
            and (allowed is None or Path(row.path).suffix.lower() in allowed)
        ]
        self.results_model.set_rows(rows)
        if not self._catalog_mode:
            self._catalog_mode = True
            self.thumbnail_cache.forget_pending()
            self._set_content_model(self.results_model)
            self.file_view.setRootIndex(QModelIndex())
            self.grid_view.setRootIndex(QModelIndex())
            self.file_view.setColumnWidth(0, 240)
            self.file_view.setColumnWidth(1, 300)
        self.results_banner.setText(
            f"Whole catalog: {len(rows)} file(s) with {query.describe()}"
        )
        self.results_bar.show()
        self._update_action_states()
        self._show_status(f"Found {len(rows)} file(s) in the catalog with {query.describe()}", log=False)

    def _leave_catalog_mode(self) -> None:
        """Return from catalog results to the current folder."""
        self._catalog_mode = False
        self._background.cancel("catalog-search")
        self.results_bar.hide()
        self.thumbnail_cache.forget_pending()
        self._set_content_model(self.filter_model)
        for column, width in enumerate((280, 100, 140, 160)):
            self.file_view.setColumnWidth(column, width)

    def _on_category_changed(self, category: str) -> None:
        """Apply the selected media category to the file list."""
        self.filter_model.set_category(category)
        if self._catalog_mode:
            self._search_catalog(self.tag_filter.query())
        else:
            self._set_file_root()

    def _set_file_root(self) -> None:
        """Keep the list and grid rooted at the folder selected in the tree."""
        if self.current_folder is None or self._catalog_mode:
            return
        root = self.filter_model.mapFromSource(self.file_model.index(str(self.current_folder)))
        self.file_view.setRootIndex(root)
        self.grid_view.setRootIndex(root)
        self.refresh_statuses()

    def refresh_statuses(self, *_args: object) -> None:
        """Refresh status colours, or re-run the catalog search in catalog mode."""
        if self._catalog_mode:
            if not _args:  # Folder loads in the background do not affect results.
                self._search_catalog(self.tag_filter.query())
            return
        if self.current_folder is None:
            return
        root_index = self.file_model.index(str(self.current_folder))
        paths: list[Path] = []
        for row in range(self.file_model.rowCount(root_index)):
            index = self.file_model.index(row, 0, root_index)
            path = Path(self.file_model.filePath(index))
            if not self.file_model.isDir(index) and path.suffix.lower() in MEDIA_EXTENSIONS:
                paths.append(path)
        try:
            statuses = self.database.status_map(paths, self._duplicate_paths)
            file_tags = self.database.tags_by_path(paths)
        except sqlite3.Error:
            LOGGER.warning("Could not load catalog status for %s", self.current_folder, exc_info=True)
            return
        self.filter_model.set_catalog_data(statuses, file_tags)

    # Navigation ---------------------------------------------------------------

    def choose_folder(self) -> None:
        """Prompt for a folder and navigate to the selection."""
        initial = str(self.current_folder or Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Select media folder", initial)
        if folder:
            self.folder_input.setText(folder)
            self.load_folder(Path(folder))

    def load_startup_directory(self) -> None:
        """Open the saved folder, using the home directory as a fallback."""
        saved_directory = self.settings.value("default_directory", "", type=str)
        directory = Path(saved_directory).expanduser() if saved_directory else DEFAULT_DIRECTORY
        if directory.is_dir():
            self.load_folder(directory)
            return

        if saved_directory:
            self._show_status(f"Saved default directory is unavailable: {directory}")
            if DEFAULT_DIRECTORY.is_dir():
                self.load_folder(DEFAULT_DIRECTORY)
                self._show_status(
                    f"Saved default directory is unavailable: {directory}. "
                    f"Opened fallback directory: {DEFAULT_DIRECTORY}"
                )

    def set_current_folder_as_default(self) -> None:
        """Save the current folder as the next launch's starting location."""
        if self.current_folder is None:
            return
        self.settings.setValue("default_directory", str(self.current_folder))
        self.settings.sync()
        if self.settings.status() != QSettings.Status.NoError:
            QMessageBox.warning(
                self,
                "Could not save default directory",
                "MediaToolkit could not save the default directory setting.",
            )
            return
        self._show_status(f"Default directory set to {self.current_folder}")

    def load_folder_from_input(self) -> None:
        """Navigate to the expanded path from the location field."""
        self.load_folder(Path(self.folder_input.text()).expanduser())

    def load_folder(self, folder: Path, *, add_to_history: bool = True) -> None:
        """Update folder models, navigation history, and dependent previews."""
        folder = folder.expanduser()
        if not folder.is_dir():
            LOGGER.warning("Rejected navigation to missing directory: %s", folder)
            QMessageBox.warning(self, "Invalid folder", f"Folder does not exist:\n{folder}")
            return

        if self._catalog_mode:
            self.tag_filter.panel.set_whole_catalog(False)
        self.thumbnail_cache.forget_pending()
        self.current_folder = folder.resolve()
        if add_to_history and (
            self._history_index < 0 or self._history[self._history_index] != self.current_folder
        ):
            del self._history[self._history_index + 1 :]
            self._history.append(self.current_folder)
            self._history_index = len(self._history) - 1
        self._update_navigation_buttons()
        self.set_default_directory_button.setEnabled(True)
        self.folder_input.setText(str(self.current_folder))
        self.file_model.setRootPath(str(self.current_folder))
        self._set_file_root()

        anchor = Path(self.current_folder.anchor)
        self.folder_model.setRootPath(str(anchor))
        self.folder_tree.setRootIndex(self.folder_model.index(str(anchor)))
        self._syncing_folder_tree = True
        try:
            current_index = self.folder_model.index(str(self.current_folder))
            for ancestor in reversed(self.current_folder.parents):
                if ancestor == anchor:
                    break
                self.folder_tree.expand(self.folder_model.index(str(ancestor)))
            self.folder_tree.setCurrentIndex(current_index)
            self.folder_tree.scrollTo(current_index)
        finally:
            self._syncing_folder_tree = False

        self.preview.clear_preview()
        self.media_selected.emit(None, None)
        self._show_status(f"Opened folder: {self.current_folder}")
        self.folder_changed.emit(self.current_folder)

    def go_back(self) -> None:
        """Navigate to the previous folder in the Explorer history."""
        if self._history_index > 0:
            self._history_index -= 1
            self.load_folder(self._history[self._history_index], add_to_history=False)

    def go_forward(self) -> None:
        """Navigate to the next folder in the Explorer history."""
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.load_folder(self._history[self._history_index], add_to_history=False)

    def go_up(self) -> None:
        """Navigate from the current folder to its parent."""
        if self.current_folder is not None and self.current_folder.parent != self.current_folder:
            self.load_folder(self.current_folder.parent)

    def _update_navigation_buttons(self) -> None:
        """Enable navigation controls according to the history position."""
        self.back_button.setEnabled(self._history_index > 0)
        self.forward_button.setEnabled(self._history_index < len(self._history) - 1)
        self.up_button.setEnabled(
            self.current_folder is not None
            and self.current_folder.parent != self.current_folder
        )

    def _on_folder_selected(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Navigate when a different folder is selected in the directory tree."""
        if self._syncing_folder_tree or not current.isValid():
            return
        self.load_folder(Path(self.folder_model.filePath(current)))

    def _on_file_selected(self, current: QModelIndex, _previous: QModelIndex) -> None:
        """Update the media preview and announce the selected media file."""
        path: Path | None = None
        path_text = current.data(PATH_ROLE) if current.isValid() else None
        if path_text:
            candidate = Path(path_text)
            if candidate.suffix.lower() in MEDIA_EXTENSIONS and not candidate.is_dir():
                path = candidate
        if path is None:
            self.preview.clear_preview()
            self.media_selected.emit(None, None)
            return
        record = self.database.cached_records([path]).get(str(path))
        metadata = record.metadata if record is not None else None
        self.preview.show_file(path, metadata)
        self.media_selected.emit(path, metadata)

    def _on_file_activated(self, index: QModelIndex) -> None:
        """Open a directory in Explorer or launch the activated file."""
        path_text = index.data(PATH_ROLE)
        if not path_text:
            return
        path = Path(path_text)
        if path.is_dir():
            self.load_folder(path)
        else:
            LOGGER.info("Opening media file with desktop handler: %s", path)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    # Tags ---------------------------------------------------------------------

    def load_tag_taxonomy(self) -> None:
        """Load category/tag definitions from a selected JSON file."""
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Load tag definitions",
            str(Path.home()),
            "JSON files (*.json);;All files (*)",
        )
        if not filename:
            return
        try:
            payload = json.loads(Path(filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            LOGGER.exception("Could not read tag taxonomy from %s", filename)
            QMessageBox.warning(self, "Could not load tags.json", str(error))
            return
        if (
            not isinstance(payload, dict)
            or not payload
            or any(
                not isinstance(category, str)
                or not isinstance(tags, list)
                or any(not isinstance(tag, str) or not tag.strip() for tag in tags)
                for category, tags in payload.items()
            )
        ):
            QMessageBox.warning(
                self,
                "Invalid tags.json",
                "Expected an object of category names mapped to arrays of tag names.",
            )
            return
        flattened = [tag for tags in payload.values() for tag in tags]
        if len(flattened) != len(set(flattened)):
            QMessageBox.warning(
                self, "Invalid tags.json", "Each tag must belong to only one category."
            )
            return
        try:
            self.database.update_taxonomy(
                {category: [tag.strip() for tag in tags] for category, tags in payload.items()}
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            LOGGER.exception("Could not save loaded tag taxonomy")
            QMessageBox.warning(self, "Could not save tag definitions", str(error))
            return
        self.tag_filter.set_taxonomy(self.database.taxonomy())
        self._update_action_states()
        self._show_status(f"Loaded {len(flattened)} tags in {len(payload)} categories")

    def edit_selected_tags(self) -> None:
        """Save selected tags to both the catalog and supported XDG attributes."""
        taxonomy = self.database.taxonomy()
        if not taxonomy:
            QMessageBox.information(
                self, "No tag definitions", "Load your tags.json file first."
            )
            return
        paths = [path for path in self.selected_paths() if _is_media_file(path)]
        if not paths:
            return
        common_tags = self.database.tags_for(paths[0])
        for path in paths[1:]:
            common_tags.intersection_update(self.database.tags_for(path))
        dialog = TagEditorDialog(taxonomy, common_tags, self)
        if dialog.exec() != TagEditorDialog.DialogCode.Accepted:
            return
        chosen = dialog.selected_tags()
        unsupported: list[str] = []
        failures: list[str] = []
        saved = 0
        for path in paths:
            try:
                self.database.save_tags(path, chosen)
                supported = write_xdg_tags(path, chosen)
            except (OSError, ValueError, sqlite3.Error) as error:
                LOGGER.exception("Could not save tags for %s", path)
                failures.append(f"{path.name}: {error}")
            else:
                saved += 1
                if not supported:
                    unsupported.append(path.name)
        self.refresh_statuses()
        self._show_status(f"Saved tags for {saved} file(s)")
        messages = failures[:20]
        if unsupported:
            LOGGER.warning("XDG tags are not supported for: %s", ", ".join(unsupported))
            messages.append(
                "XDG tags are not supported for: " + ", ".join(unsupported[:20])
            )
        if messages:
            QMessageBox.warning(self, "Tagging completed with issues", "\n".join(messages))

    # Indexing -----------------------------------------------------------------

    def start_indexing(self) -> None:
        """Launch the background indexer for the current directory tree."""
        if self.current_folder is None:
            QMessageBox.information(self, "Choose a folder", "Choose a folder to index first.")
            return
        if self.is_indexing():
            return
        self.scan_progress.setValue(0)
        self.scan_progress.show()
        self._show_status(f"Starting media index for {self.current_folder}")
        worker = IndexWorker(
            self.current_folder, self.database.database_path, threads=self.index_threads
        )
        worker.progress.connect(self._on_index_progress)
        worker.completed.connect(self._on_index_completed)
        worker.finished.connect(self._update_action_states)
        worker.start()
        self.index_worker = worker
        self.index_action.setEnabled(False)

    def _on_index_progress(self, percent: int, message: str) -> None:
        """Reflect background indexing progress in the UI."""
        self.scan_progress.setValue(percent)
        # IndexWorker logs progress milestones; per-file statuses are not logged.
        self._show_status(message, log=False)

    def _on_index_completed(self, records: list[MediaRecord], errors: list[str]) -> None:
        """Import discovered tags and refresh catalog-backed views after indexing."""
        self.scan_progress.hide()
        imported = 0
        taxonomy = {tag for tags in self.database.taxonomy().values() for tag in tags}
        for record in records:
            existing_xdg_tags = set(record.metadata.get("xdg_tags", [])) & taxonomy
            if existing_xdg_tags and not self.database.tags_for(Path(record.path)):
                try:
                    self.database.save_tags(Path(record.path), existing_xdg_tags)
                except (OSError, ValueError, sqlite3.Error) as error:
                    LOGGER.exception("Could not import XDG tags for %s", record.path)
                    errors.append(f"Could not import tags for {record.path}: {error}")
                else:
                    imported += 1
        self.refresh_statuses()
        summary = (
            f"Indexed {len(records)} media files; click Refresh duplicate groups "
            f"to update matches; imported tags from {imported} file(s)."
        )
        if errors:
            summary += f" {len(errors)} issue(s)."
            QMessageBox.warning(
                self,
                "Indexing completed with issues",
                summary + "\n\n" + "\n".join(errors[:20]),
            )
        self._show_status(summary)

    # File operations ----------------------------------------------------------

    def create_new_folder(self) -> None:
        """Create a named child directory in the current Explorer folder."""
        if self.current_folder is None:
            return
        name, accepted = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not accepted:
            return
        try:
            create_folder(self.current_folder, name)
        except (OSError, ValueError) as error:
            LOGGER.exception("Could not create folder %s", name)
            QMessageBox.warning(self, "Could not create folder", str(error))
            return
        self._show_status(f"Created folder: {name}")

    def copy_random_media_from_folder(self) -> None:
        """Choose media types and copy a random subset into a new temporary folder."""
        if self.current_folder is None:
            QMessageBox.information(self, "No folder selected", "Open a folder in Explorer first.")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Copy random media")
        dialog.resize(480, 350)
        dialog_layout = QVBoxLayout(dialog)
        form = QFormLayout()
        count = QSpinBox()
        count.setRange(1, 100_000)
        count.setValue(20)
        destination_name = QLineEdit("random_media")
        form.addRow("Number of files", count)
        form.addRow(f"Destination name in {tempfile.gettempdir()}", destination_name)
        dialog_layout.addLayout(form)

        dialog_layout.addWidget(QLabel("Choose file extensions:"))
        extension_content = QWidget()
        extension_layout = QGridLayout(extension_content)
        extension_checks: dict[str, QCheckBox] = {}
        for index, extension in enumerate(sorted(MEDIA_EXTENSIONS)):
            checkbox = QCheckBox(extension)
            extension_checks[extension] = checkbox
            extension_layout.addWidget(checkbox, index // 5, index % 5)
        extension_scroll = QScrollArea()
        extension_scroll.setWidgetResizable(True)
        extension_scroll.setWidget(extension_content)
        extension_scroll.setMinimumHeight(130)
        dialog_layout.addWidget(extension_scroll)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dialog_layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        extensions = {
            extension for extension, checkbox in extension_checks.items() if checkbox.isChecked()
        }
        try:
            destination, copied = copy_random_media(
                self.current_folder, count.value(), extensions, destination_name.text()
            )
        except (OSError, ValueError) as error:
            LOGGER.exception("Could not copy random media from %s", self.current_folder)
            QMessageBox.warning(self, "Could not copy random media", str(error))
            return
        QMessageBox.information(
            self,
            "Random media copied",
            f"Copied {len(copied)} of {count.value()} requested file(s) to:\n{destination}",
        )
        self._show_status(f"Copied {len(copied)} random media file(s) to {destination}")

    def rename_current_folder_files_with_guids(self) -> None:
        """Rename immediate child files and update their catalog paths."""
        if self.current_folder is None:
            QMessageBox.information(self, "No folder selected", "Open a folder in Explorer first.")
            return
        try:
            file_count = sum(1 for path in self.current_folder.iterdir() if path.is_file())
        except OSError as error:
            QMessageBox.warning(self, "Could not list folder files", str(error))
            return
        if file_count == 0:
            QMessageBox.information(
                self, "No files to rename", "The current folder contains no files."
            )
            return
        answer = QMessageBox.question(
            self,
            "Rename files with GUIDs",
            f"Rename all {file_count} file(s) directly inside this folder?\n\n"
            f"{self.current_folder}\n\nExtensions will be preserved. "
            "Files in subfolders will not be renamed.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            renamed = rename_files_with_guids(self.current_folder)
        except (OSError, ValueError) as error:
            LOGGER.exception("Could not rename files in %s", self.current_folder)
            QMessageBox.warning(self, "Could not rename files", str(error))
            self.load_folder(self.current_folder, add_to_history=False)
            return

        database_errors: list[str] = []
        for source, destination in renamed:
            try:
                self.database.relocate_path(source, destination, copy=False)
            except sqlite3.Error as error:
                database_errors.append(f"{source.name}: {error}")

        self.load_folder(self.current_folder, add_to_history=False)
        if database_errors:
            for error in database_errors:
                LOGGER.error("GUID rename catalog issue: %s", error)
            QMessageBox.warning(
                self,
                "Files renamed with database issues",
                f"Renamed {len(renamed)} file(s), but some indexed data could not be updated:\n"
                + "\n".join(database_errors),
            )
        else:
            self._show_status(f"Renamed {len(renamed)} file(s) with GUIDs")

    def rename_selected(self) -> None:
        """Prompt for a replacement name and update the catalog after renaming."""
        paths = self.selected_paths()
        if len(paths) != 1:
            return
        source = paths[0]
        name, accepted = QInputDialog.getText(self, "Rename", "New name:", text=source.name)
        if not accepted or name == source.name:
            return
        LOGGER.info("Renaming %s to %s", source, name)
        try:
            destination = rename_path(source, name)
        except (OSError, ValueError) as error:
            LOGGER.exception("Could not rename %s", source)
            QMessageBox.warning(self, "Could not rename item", str(error))
            return
        try:
            self.database.relocate_path(source, destination, copy=False)
        except sqlite3.Error as error:
            LOGGER.exception("Renamed %s but could not update its catalog record", source)
            QMessageBox.warning(
                self,
                "Database update failed",
                f"Renamed the file, but could not update its indexed data: {error}",
            )
        self.preview.clear_preview()
        self.media_selected.emit(None, None)
        self.refresh_statuses()

    def copy_selected(self) -> None:
        """Place the current selection on the app's internal copy clipboard."""
        self._set_clipboard("copy")

    def cut_selected(self) -> None:
        """Place the current selection on the app's internal move clipboard."""
        self._set_clipboard("move")

    def _set_clipboard(self, mode: str) -> None:
        """Store selected paths and the requested copy-or-move operation."""
        self._clipboard_paths = self.selected_paths()
        self._clipboard_mode = mode
        self._update_action_states()
        if self._clipboard_paths:
            verb = "Copied" if mode == "copy" else "Cut"
            self._show_status(
                f"{verb} {len(self._clipboard_paths)} item(s). Choose a folder and paste."
            )

    def paste_into_folder(self) -> None:
        """Paste queued paths and keep failed move sources on the clipboard."""
        if self.current_folder is None or not self._clipboard_paths:
            return
        move = self._clipboard_mode == "move"
        remaining: list[Path] = []
        errors: list[str] = []
        pasted = 0
        for source in self._clipboard_paths:
            try:
                destination = paste_path(source, self.current_folder, move=move)
                self.database.relocate_path(source, destination, copy=not move)
            except (OSError, ValueError, sqlite3.Error) as error:
                LOGGER.exception("Could not paste %s into %s", source, self.current_folder)
                errors.append(f"{source.name}: {error}")
                if source.exists() or source.is_symlink():
                    remaining.append(source)
            else:
                pasted += 1

        if move:
            self._clipboard_paths = remaining
        self._update_action_states()
        if errors:
            QMessageBox.warning(self, "Some items could not be pasted", "\n".join(errors))
        if pasted:
            self._show_status(f"Pasted {pasted} item(s)")

    def delete_selected(self) -> None:
        """Ask the main window to trash all selected Explorer paths."""
        paths = self.selected_paths()
        if paths:
            self.trash_requested.emit(paths)
