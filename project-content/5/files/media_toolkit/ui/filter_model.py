"""Explorer file-list filtering (name, type, tags) and catalog status colours."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from PySide6.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QObject,
    QSortFilterProxyModel,
    Qt,
)
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QFileSystemModel

from media_toolkit.core.filesystem import (
    AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    MEDIA_EXTENSIONS,
    VIDEO_EXTENSIONS,
)
from media_toolkit.core.tag_query import TagQuery
from media_toolkit.ui.theme import current_theme

# status: (legend label, tooltip description). Colours come from the theme.
FILE_STATUSES = {
    "not-indexed": ("Not indexed", "Not yet indexed"),
    "indexed": ("Indexed, no tags", "Indexed, no tags"),
    "tagged": ("Tagged", "Indexed and tagged"),
    "duplicate": ("Duplicate", "Duplicate detected"),
}
# Item data role holding a row's file path (str), answered by every Explorer
# content model so views and delegates need not know which model they show.
PATH_ROLE = Qt.ItemDataRole.UserRole + 100
# QFileSystemModel columns.
_NAME_COLUMN, _SIZE_COLUMN, _TYPE_COLUMN, _DATE_COLUMN = range(4)
CATEGORY_EXTENSIONS = {
    "Media files": MEDIA_EXTENSIONS,
    "Images": IMAGE_EXTENSIONS,
    "Video": VIDEO_EXTENSIONS,
    "Audio": AUDIO_EXTENSIONS,
}


_DIGITS = re.compile(r"(\d+)")


def natural_key(text: str) -> tuple[tuple[str | int, ...], str, str]:
    """Return a key ordering text like a file manager.

    Case and accents are ignored and digit runs compare as numbers, so
    "File2" < "file10" and "École" sorts next to "ecole"; the exact text
    breaks ties. The result is a plain tuple, so cached keys compare quickly.
    """
    folded = text.casefold()
    plain = "".join(
        char for char in unicodedata.normalize("NFKD", folded) if not unicodedata.combining(char)
    )
    parts = tuple(int(part) if part.isdigit() else part for part in _DIGITS.split(plain))
    return parts, folded, text


def status_legend_html() -> str:
    """Return rich text showing each status colour of the current theme."""
    statuses = current_theme().statuses
    return "&nbsp;&nbsp;".join(
        f'<span style="color:{statuses[status].text};'
        f'background:{statuses[status].background}">&nbsp;{label}&nbsp;</span>'
        for status, (label, _description) in FILE_STATUSES.items()
    )


class ExplorerFilterProxyModel(QSortFilterProxyModel):
    """Filter files by name, type, and tags, and colour them by catalog status.

    The tag filter is a TagQuery (all/any of some tags, none of others).
    While it is active, folders are hidden because they have no tags.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        """Initialize an enabled recursive, dynamically updated proxy."""
        super().__init__(parent)
        self._search_text = ""
        self._category = "All files"
        self._statuses: dict[str, str] = {}
        self._file_tags: dict[str, set[str]] = {}
        self._tag_query = TagQuery()
        self._sort_keys: dict[tuple[int, int], tuple[bool, object, tuple]] = {}
        self.setRecursiveFilteringEnabled(True)
        self.setDynamicSortFilter(True)

    def set_search_text(self, text: str) -> None:
        """Set the case-insensitive filename substring filter."""
        self._search_text = text.casefold().strip()
        self.invalidateFilter()

    def set_category(self, category: str) -> None:
        """Set the media category filter, or show all files."""
        self._category = category
        self.invalidateFilter()

    def set_tag_query(self, query: TagQuery) -> None:
        """Show only files matching query; an inactive query shows everything."""
        self._tag_query = query
        self.invalidateFilter()

    def set_catalog_data(
        self, statuses: dict[str, str], file_tags: dict[str, set[str]]
    ) -> None:
        """Replace per-path statuses and tags, then refresh colours and filtering."""
        self._statuses = statuses
        self._file_tags = file_tags
        self.invalidate()

    def refresh_colors(self) -> None:
        """Repaint rows after the theme changed."""
        self.invalidate()

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return source data with status-specific colors, tooltips, and paths."""
        if role == PATH_ROLE and index.isValid():
            source = self.sourceModel()
            if isinstance(source, QFileSystemModel):
                return source.filePath(self.mapToSource(index.siblingAtColumn(0)))
        if index.isValid() and role in {
            Qt.ItemDataRole.BackgroundRole,
            Qt.ItemDataRole.ForegroundRole,
            Qt.ItemDataRole.ToolTipRole,
        }:
            source = self.sourceModel()
            if isinstance(source, QFileSystemModel):
                source_index = self.mapToSource(index.siblingAtColumn(0))
                path_text = source.filePath(source_index)
                status = self._statuses.get(path_text)
                if status in FILE_STATUSES:
                    colors = current_theme().statuses[status]
                    if role == Qt.ItemDataRole.BackgroundRole:
                        return QBrush(QColor(colors.background))
                    if role == Qt.ItemDataRole.ForegroundRole:
                        return QBrush(QColor(colors.text))
                    description = FILE_STATUSES[status][1]
                    tags = sorted(self._file_tags.get(path_text, ()), key=str.casefold)
                    if tags:
                        return f"{description}\nTags: {', '.join(tags)}"
                    return description
        return super().data(index, role)

    def setSourceModel(self, source: QAbstractItemModel) -> None:
        """Watch source changes so cached sort keys never outlive the data.

        These connections are made before the proxy's own, so the cache is
        cleared before a change triggers a re-sort.
        """
        for signal in (
            source.dataChanged,
            source.rowsInserted,
            source.rowsRemoved,
            source.layoutChanged,
            source.modelReset,
        ):
            signal.connect(self._clear_sort_keys)
        super().setSourceModel(source)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sort with freshly computed keys."""
        self._clear_sort_keys()
        super().sort(column, order)

    def _clear_sort_keys(self, *_args: object) -> None:
        """Forget cached sort keys after the files changed."""
        self._sort_keys.clear()

    def _sort_key(self, index: QModelIndex) -> tuple[bool, object, tuple]:
        """Return (is folder, column value, name key) for a source index, cached.

        Sorting 10,000 files compares about 140,000 pairs, so values are read
        from the file model once per file instead of once per comparison.
        """
        cache_key = (index.internalId(), index.column())
        key = self._sort_keys.get(cache_key)
        if key is None:
            source = self.sourceModel()
            assert isinstance(source, QFileSystemModel)
            is_folder = source.isDir(index)
            column = index.column()
            value: object = 0
            if column == _SIZE_COLUMN and not is_folder:
                value = source.size(index)
            elif column == _DATE_COLUMN:
                value = source.lastModified(index).toMSecsSinceEpoch()
            elif column == _TYPE_COLUMN:
                value = natural_key(source.type(index))
            key = (is_folder, value, natural_key(source.fileName(index)))
            self._sort_keys[cache_key] = key
        return key

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        """Order rows by real size, date, type, or name instead of display text.

        Folders stay above files in both sort orders; equal values fall back
        to the name, compared naturally ("2" before "10") and ignoring case.
        """
        if not isinstance(self.sourceModel(), QFileSystemModel):
            return super().lessThan(left, right)
        left_key, right_key = self._sort_key(left), self._sort_key(right)
        if left_key[0] != right_key[0]:
            ascending = self.sortOrder() == Qt.SortOrder.AscendingOrder
            return left_key[0] if ascending else right_key[0]
        return left_key[1:] < right_key[1:]

    def filterAcceptsRow(self, source_row: int, source_parent: QModelIndex) -> bool:
        """Keep rows matching the name, type, and tag filters."""
        source = self.sourceModel()
        if not isinstance(source, QFileSystemModel):
            return True
        index = source.index(source_row, 0, source_parent)
        path = Path(source.filePath(index))
        if self._search_text and self._search_text not in path.name.casefold():
            return False
        if source.isDir(index):
            return not self._tag_query.active
        if self._tag_query.active and not self._tag_query.matches(
            self._file_tags.get(str(path), set())
        ):
            return False
        allowed = CATEGORY_EXTENSIONS.get(self._category)
        return allowed is None or path.suffix.lower() in allowed
