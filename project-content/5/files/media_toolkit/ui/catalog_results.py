"""Table model for tag searches across the whole catalog."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QDateTime, QLocale, QModelIndex, QObject, Qt
from PySide6.QtGui import QBrush, QColor

from media_toolkit.core.database import MediaDatabase
from media_toolkit.core.filesystem import format_size
from media_toolkit.core.tag_query import TagQuery
from media_toolkit.ui.filter_model import FILE_STATUSES, PATH_ROLE, natural_key
from media_toolkit.ui.theme import current_theme

_HEADERS = ("Name", "Folder", "Size", "Date Modified")
_NAME, _FOLDER, _SIZE, _DATE = range(4)


@dataclass(frozen=True)
class ResultRow:
    """One matching file with the values the table shows and sorts by."""

    path: str
    size: int
    modified: float
    status: str
    tags: frozenset[str]

    @property
    def name(self) -> str:
        return Path(self.path).name

    @property
    def folder(self) -> str:
        return str(Path(self.path).parent)


def find_catalog_matches(
    database: MediaDatabase, query: TagQuery, duplicate_paths: set[str]
) -> list[ResultRow]:
    """Search the catalog and gather display data; blocking, so run it off the UI thread."""
    paths = [Path(path) for path in database.search_by_tags(query)]
    statuses = database.status_map(paths, duplicate_paths)
    tags = database.tags_by_path(paths)
    rows = []
    for path in paths:
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append(
            ResultRow(
                str(path),
                stat.st_size,
                stat.st_mtime,
                statuses.get(str(path), "indexed"),
                frozenset(tags.get(str(path), ())),
            )
        )
    return rows


class CatalogResultsModel(QAbstractTableModel):
    """Rows of ResultRow with Explorer's status colours, tooltips, and PATH_ROLE."""

    def __init__(self, parent: QObject | None = None) -> None:
        """Start empty."""
        super().__init__(parent)
        self._rows: list[ResultRow] = []
        self._sort_column = _NAME
        self._sort_order = Qt.SortOrder.AscendingOrder

    def set_rows(self, rows: list[ResultRow]) -> None:
        """Replace all rows, keeping the current sort order."""
        self.beginResetModel()
        self._rows = sorted(rows, key=self._sort_key, reverse=self._descending)
        self.endResetModel()

    def rows(self) -> list[ResultRow]:
        """Return the rows in display order."""
        return list(self._rows)

    def refresh_colors(self) -> None:
        """Repaint rows after the theme changed."""
        if self._rows:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self._rows) - 1, len(_HEADERS) - 1)
            )

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(_HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return _HEADERS[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """Return text, alignment, status colours, tooltip, or path for a cell."""
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        column = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            if column == _NAME:
                return row.name
            if column == _FOLDER:
                return row.folder
            if column == _SIZE:
                return format_size(row.size)
            return QLocale().toString(
                QDateTime.fromSecsSinceEpoch(int(row.modified)), QLocale.FormatType.ShortFormat
            )
        if role == PATH_ROLE:
            return row.path
        if role == Qt.ItemDataRole.TextAlignmentRole and column == _SIZE:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role in (Qt.ItemDataRole.BackgroundRole, Qt.ItemDataRole.ForegroundRole):
            colors = current_theme().statuses.get(row.status)
            if colors is None:
                return None
            color = colors.background if role == Qt.ItemDataRole.BackgroundRole else colors.text
            return QBrush(QColor(color))
        if role == Qt.ItemDataRole.ToolTipRole:
            lines = [row.path, FILE_STATUSES.get(row.status, ("", ""))[1]]
            if row.tags:
                lines.append("Tags: " + ", ".join(sorted(row.tags, key=str.casefold)))
            return "\n".join(line for line in lines if line)
        return None

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        """Sort by real values, keeping selections attached to their rows."""
        self._sort_column, self._sort_order = column, order
        self.layoutAboutToBeChanged.emit()
        old_rows = self._rows
        self._rows = sorted(old_rows, key=self._sort_key, reverse=self._descending)
        new_position = {row.path: position for position, row in enumerate(self._rows)}
        old_indexes = self.persistentIndexList()
        self.changePersistentIndexList(
            old_indexes,
            [
                self.index(new_position[old_rows[index.row()].path], index.column())
                for index in old_indexes
            ],
        )
        self.layoutChanged.emit()

    @property
    def _descending(self) -> bool:
        return self._sort_order == Qt.SortOrder.DescendingOrder

    def _sort_key(self, row: ResultRow) -> tuple:
        """Return the key for the current sort column, with the name as tie-breaker."""
        name = natural_key(row.name)
        if self._sort_column == _FOLDER:
            return natural_key(row.folder), name
        if self._sort_column == _SIZE:
            return row.size, name
        if self._sort_column == _DATE:
            return row.modified, name
        return (name,)
