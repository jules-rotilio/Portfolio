"""Read-only, paginated Qt browser for tables in the media catalog."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


PAGE_SIZE = 100


def _quote_identifier(identifier: str) -> str:
    """Quote an SQLite identifier, escaping embedded double quotes."""
    return '"' + identifier.replace('"', '""') + '"'


def _display_value(value: object) -> str:
    """Render database values compactly, without expanding binary blobs."""
    if value is None:
        return "NULL"
    if isinstance(value, bytes):
        return f"[BLOB: {len(value)} bytes]"
    return str(value)


class DatabaseBrowser(QWidget):
    """Read-only table browser for the app's SQLite catalog."""

    def __init__(self, database_path: Path, parent: QWidget | None = None) -> None:
        """Build the browser controls and load available tables."""
        super().__init__(parent)
        self.database_path = database_path
        self.offset = 0

        self.table_selector = QComboBox()
        self.table_selector.currentTextChanged.connect(self._on_table_changed)
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter rows…")
        self.search_input.returnPressed.connect(self._apply_search)
        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh_tables)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Table:"))
        toolbar.addWidget(self.table_selector)
        toolbar.addWidget(self.search_input, stretch=1)
        toolbar.addWidget(self.refresh_button)

        self.table = QTableWidget()
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.horizontalHeader().setStretchLastSection(True)

        self.previous_button = QPushButton("Previous")
        self.previous_button.setEnabled(False)
        self.previous_button.clicked.connect(self._previous_page)
        self.next_button = QPushButton("Next")
        self.next_button.setEnabled(False)
        self.next_button.clicked.connect(self._next_page)
        self.page_label = QLabel()
        self.status_label = QLabel()
        self.status_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        footer = QHBoxLayout()
        footer.addWidget(self.status_label, stretch=1)
        footer.addWidget(self.previous_button)
        footer.addWidget(self.page_label)
        footer.addWidget(self.next_button)

        layout = QVBoxLayout(self)
        layout.addLayout(toolbar)
        layout.addWidget(self.table, stretch=1)
        layout.addLayout(footer)

        self.refresh_tables()

    def refresh_tables(self) -> None:
        """Reload table/view names and refresh the selected table's first page."""
        selected_table = self.table_selector.currentText()
        try:
            with closing(self._connect()) as connection:
                names = [
                    row[0]
                    for row in connection.execute(
                        """
                        SELECT name FROM sqlite_schema
                        WHERE type IN ('table', 'view')
                          AND name NOT LIKE 'sqlite_%'
                        ORDER BY name COLLATE NOCASE
                        """
                    )
                ]
        except (OSError, sqlite3.Error) as error:
            self._show_error(error)
            return

        self.table_selector.blockSignals(True)
        self.table_selector.clear()
        self.table_selector.addItems(names)
        if selected_table in names:
            self.table_selector.setCurrentText(selected_table)
        self.table_selector.blockSignals(False)
        self.offset = 0
        self._load_rows()

    def refresh_data(self) -> None:
        """Reload the current table page using the current search."""
        self._load_rows()

    def _connect(self) -> sqlite3.Connection:
        """Open the catalog using SQLite read-only URI mode."""
        return sqlite3.connect(f"{self.database_path.as_uri()}?mode=ro", uri=True)

    def _on_table_changed(self, _: str) -> None:
        """Reset pagination when the selected table changes."""
        self.offset = 0
        self._load_rows()

    def _apply_search(self) -> None:
        """Apply the entered filter from the first result page."""
        self.offset = 0
        self._load_rows()

    def _previous_page(self) -> None:
        """Move back one page, bounded at the first page."""
        self.offset = max(0, self.offset - PAGE_SIZE)
        self._load_rows()

    def _next_page(self) -> None:
        """Move forward one page."""
        self.offset += PAGE_SIZE
        self._load_rows()

    def _load_rows(self) -> None:
        """Fetch and display the selected table's filtered page."""
        table_name = self.table_selector.currentText()
        if not table_name:
            self.table.clear()
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.status_label.setText("No tables found.")
            self.page_label.clear()
            self.previous_button.setEnabled(False)
            self.next_button.setEnabled(False)
            return

        quoted_table = _quote_identifier(table_name)
        search = self.search_input.text().strip()
        try:
            with closing(self._connect()) as connection:
                columns = [
                    row[1]
                    for row in connection.execute(
                        f"PRAGMA table_info({quoted_table})"
                    )
                ]
                if not columns:
                    self._clear_for_error(f"Could not read columns for {table_name}.")
                    return

                where_clause = ""
                parameters: list[str | int] = []
                if search:
                    # Treat user-supplied LIKE metacharacters as literal text.
                    escaped_search = (
                        search.replace("\\", "\\\\")
                        .replace("%", "\\%")
                        .replace("_", "\\_")
                    )
                    where_clause = " WHERE " + " OR ".join(
                        f"CAST({_quote_identifier(column)} AS TEXT) LIKE ? ESCAPE '\\'"
                        for column in columns
                    )
                    parameters.extend([f"%{escaped_search}%"] * len(columns))

                total_rows = connection.execute(
                    f"SELECT COUNT(*) FROM {quoted_table}{where_clause}",
                    parameters,
                ).fetchone()[0]
                if self.offset >= total_rows and self.offset > 0:
                    self.offset = ((total_rows - 1) // PAGE_SIZE) * PAGE_SIZE if total_rows else 0
                rows = connection.execute(
                    f"SELECT * FROM {quoted_table}{where_clause} LIMIT ? OFFSET ?",
                    [*parameters, PAGE_SIZE, self.offset],
                ).fetchall()
        except (OSError, sqlite3.Error) as error:
            self._show_error(error)
            return

        self.table.clear()
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                item = QTableWidgetItem(_display_value(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.table.setItem(row_index, column_index, item)

        first_row = self.offset + 1 if total_rows else 0
        last_row = self.offset + len(rows)
        self.status_label.setText(
            f"{table_name}: {first_row}–{last_row} of {total_rows} rows"
        )
        page_number = self.offset // PAGE_SIZE + 1
        page_count = max(1, (total_rows + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page_label.setText(f"Page {page_number} of {page_count}")
        self.previous_button.setEnabled(self.offset > 0)
        self.next_button.setEnabled(self.offset + len(rows) < total_rows)
        self.table.resizeColumnsToContents()

    def _show_error(self, error: Exception) -> None:
        """Display a database read error and clear stale rows."""
        self._clear_for_error(f"Could not read database: {error}")

    def _clear_for_error(self, message: str) -> None:
        """Clear table and paging controls while showing a status message."""
        self.table.clear()
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
        self.status_label.setText(message)
        self.page_label.clear()
        self.previous_button.setEnabled(False)
        self.next_button.setEnabled(False)
