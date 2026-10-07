"""The Tags button: a panel for building tag searches with AND, OR, and NOT."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from media_toolkit.core.tag_query import TagQuery

_HAS_COLUMN, _NOT_COLUMN = 1, 2
_MATCH_ALL, _MATCH_ANY = "All checked tags (AND)", "Any checked tag (OR)"


class TagSearchPanel(QFrame):
    """Pop-up panel listing tags with Has / Not checkboxes and search options."""

    query_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the search box, tag tree, match mode, and scope option."""
        super().__init__(parent, Qt.WindowType.Popup)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setMinimumSize(360, 460)
        self._query = TagQuery()
        self._items: dict[str, QTreeWidgetItem] = {}
        self._updating = False

        self.find_input = QLineEdit()
        self.find_input.setPlaceholderText("Find a tag")
        self.find_input.setClearButtonEnabled(True)
        self.find_input.textChanged.connect(self._filter_tags)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Tag", "Has", "Not"])
        self.tree.setRootIsDecorated(True)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_HAS_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_NOT_COLUMN, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(False)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.match_mode = QComboBox()
        self.match_mode.addItems([_MATCH_ALL, _MATCH_ANY])
        self.match_mode.setToolTip('How tags checked in "Has" combine; "Not" tags are always excluded')
        self.match_mode.currentIndexChanged.connect(self._on_options_changed)
        self.whole_catalog = QCheckBox("Search the whole catalog")
        self.whole_catalog.setToolTip(
            "Show matching files from every indexed folder instead of only this folder"
        )
        self.whole_catalog.toggled.connect(self._on_options_changed)
        clear_button = QPushButton("Clear")
        clear_button.clicked.connect(self.clear)

        match_row = QHBoxLayout()
        match_label = QLabel("Match")
        match_row.addWidget(match_label)
        match_row.addWidget(self.match_mode, stretch=1)
        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.whole_catalog, stretch=1)
        bottom_row.addWidget(clear_button)
        layout = QVBoxLayout(self)
        layout.addWidget(self.find_input)
        layout.addWidget(self.tree, stretch=1)
        layout.addLayout(match_row)
        layout.addLayout(bottom_row)

    def query(self) -> TagQuery:
        """Return the search currently built in the panel."""
        return self._query

    def set_taxonomy(self, taxonomy: dict[str, list[str]]) -> None:
        """List taxonomy tags; checked tags that no longer exist are dropped."""
        known = {tag for tags in taxonomy.values() for tag in tags}
        previous = self._query
        self._query = replace(
            previous, include=previous.include & known, exclude=previous.exclude & known
        )
        self._updating = True
        try:
            self.tree.clear()
            self._items = {}
            for category, tags in taxonomy.items():
                category_item = QTreeWidgetItem([category])
                category_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
                self.tree.addTopLevelItem(category_item)
                for tag in tags:
                    item = QTreeWidgetItem([tag])
                    item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                    item.setCheckState(_HAS_COLUMN, self._state(tag in self._query.include))
                    item.setCheckState(_NOT_COLUMN, self._state(tag in self._query.exclude))
                    category_item.addChild(item)
                    self._items[tag] = item
            self.tree.expandAll()
        finally:
            self._updating = False
        self._filter_tags(self.find_input.text())
        if self._query != previous:
            self.query_changed.emit(self._query)

    def set_tag(self, tag: str, state: str | None) -> None:
        """Set a tag to "has", "not", or None (ignored)."""
        item = self._items[tag]
        self._updating = True
        try:
            item.setCheckState(_HAS_COLUMN, self._state(state == "has"))
            item.setCheckState(_NOT_COLUMN, self._state(state == "not"))
        finally:
            self._updating = False
        self._rebuild_query()

    def set_match_all(self, match_all: bool) -> None:
        """Combine "Has" tags with AND (True) or OR (False)."""
        self.match_mode.setCurrentText(_MATCH_ALL if match_all else _MATCH_ANY)

    def set_whole_catalog(self, whole_catalog: bool) -> None:
        """Search every folder (True) or only the current one (False)."""
        self.whole_catalog.setChecked(whole_catalog)

    def clear(self) -> None:
        """Uncheck every tag; the match mode and scope are kept."""
        self._updating = True
        try:
            for item in self._items.values():
                item.setCheckState(_HAS_COLUMN, Qt.CheckState.Unchecked)
                item.setCheckState(_NOT_COLUMN, Qt.CheckState.Unchecked)
        finally:
            self._updating = False
        self._rebuild_query()

    @staticmethod
    def _state(checked: bool) -> Qt.CheckState:
        return Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        """Keep Has and Not exclusive for a tag, then update the query."""
        if self._updating or column not in (_HAS_COLUMN, _NOT_COLUMN):
            return
        if item.checkState(column) == Qt.CheckState.Checked:
            other = _NOT_COLUMN if column == _HAS_COLUMN else _HAS_COLUMN
            self._updating = True
            try:
                item.setCheckState(other, Qt.CheckState.Unchecked)
            finally:
                self._updating = False
        self._rebuild_query()

    def _on_options_changed(self, *_args: object) -> None:
        """Apply a new match mode or scope."""
        self._rebuild_query()

    def _rebuild_query(self) -> None:
        """Read the panel into a TagQuery and announce it if it changed."""
        query = TagQuery(
            include=frozenset(
                tag for tag, item in self._items.items()
                if item.checkState(_HAS_COLUMN) == Qt.CheckState.Checked
            ),
            exclude=frozenset(
                tag for tag, item in self._items.items()
                if item.checkState(_NOT_COLUMN) == Qt.CheckState.Checked
            ),
            match_all=self.match_mode.currentText() == _MATCH_ALL,
            whole_catalog=self.whole_catalog.isChecked(),
        )
        if query != self._query:
            self._query = query
            self.query_changed.emit(query)

    def _filter_tags(self, text: str) -> None:
        """Hide tags (and empty categories) not containing text."""
        needle = text.casefold().strip()
        for index in range(self.tree.topLevelItemCount()):
            category = self.tree.topLevelItem(index)
            visible_children = 0
            for child_index in range(category.childCount()):
                child = category.child(child_index)
                hidden = bool(needle) and needle not in child.text(0).casefold()
                child.setHidden(hidden)
                visible_children += not hidden
            category.setHidden(visible_children == 0)


class TagFilterButton(QToolButton):
    """Toolbar button that opens the tag search panel and summarizes the query."""

    # The new TagQuery.
    query_changed = Signal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Create the button and its (hidden) panel."""
        super().__init__(parent)
        self.panel = TagSearchPanel(self)
        self.panel.query_changed.connect(self._on_query_changed)
        self.clicked.connect(self._show_panel)
        self._update_appearance()

    def query(self) -> TagQuery:
        """Return the current tag search."""
        return self.panel.query()

    def set_taxonomy(self, taxonomy: dict[str, list[str]]) -> None:
        """List the taxonomy's tags in the panel."""
        self.panel.set_taxonomy(taxonomy)

    def clear(self) -> None:
        """Remove every tag condition."""
        self.panel.clear()

    def _show_panel(self) -> None:
        """Open the panel just below the button."""
        self.panel.adjustSize()
        self.panel.move(self.mapToGlobal(QPoint(0, self.height())))
        self.panel.show()
        self.panel.find_input.setFocus()

    def _on_query_changed(self, query: TagQuery) -> None:
        self._update_appearance()
        self.query_changed.emit(query)

    def _update_appearance(self) -> None:
        """Show the number of tag conditions and describe them in the tooltip."""
        query = self.query()
        count = len(query.include) + len(query.exclude)
        scope = "whole catalog" if query.whole_catalog else "this folder"
        if count:
            self.setText(f"Tags ({count})")
            self.setToolTip(f"Showing files in the {scope} with {query.describe()}")
        else:
            self.setText("Tags")
            self.setToolTip("Search by tags: all of, any of, or none of (AND / OR / NOT)")
        self.setProperty("active", bool(count))
        self.style().unpolish(self)
        self.style().polish(self)
