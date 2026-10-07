"""Tests for light/dark themes, the AND tag filter, and the Explorer toolbar."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication

from media_toolkit.core.database import MediaDatabase
from media_toolkit.ui.filter_model import status_legend_html
from media_toolkit.ui.main_window import MainWindow
from media_toolkit.ui.tag_filter import TagFilterButton
from media_toolkit.ui.theme import DARK, LIGHT, current_theme, theme_manager
from test_background import dispose, wait_until

TAXONOMY = {"People": ["Alice", "Bob"], "Places": ["Beach", "City"]}


class ThemeAndTagFilterTests(unittest.TestCase):
    """Themes switch everywhere; the tag filter requires every chosen tag."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.root = Path(self.temporary_directory.name)
        self.media = self.root / "media"
        (self.media / "sub").mkdir(parents=True)
        for name in ("both.jpg", "alice.jpg", "none.jpg"):
            (self.media / name).write_bytes(b"x")
        self.database = MediaDatabase(self.root / "catalog.sqlite3")
        self.addCleanup(self.database.close)
        self.database.update_taxonomy(TAXONOMY)
        self.database.save_tags(self.media / "both.jpg", {"Alice", "Beach"})
        self.database.save_tags(self.media / "alice.jpg", {"Alice"})
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)

    def tearDown(self) -> None:
        theme_manager().set_mode("Light")

    def open_window(self) -> MainWindow:
        with patch.object(MainWindow, "_load_startup_directory"):
            window = MainWindow(self.database, self.settings)
        # Cleanups run last-in first-out: the window goes before its catalog.
        self.addCleanup(dispose, window)
        return window

    def visible_names(self, window: MainWindow) -> list[str]:
        explorer = window.explorer_tab
        root = explorer.file_view.rootIndex()
        return sorted(
            explorer.filter_model.index(row, 0, root).data()
            for row in range(explorer.filter_model.rowCount(root))
        )

    def test_theme_switch_updates_palette_statuses_and_settings(self) -> None:
        window = self.open_window()
        window.set_theme_mode("Dark")
        palette = QApplication.instance().palette()
        self.assertEqual(palette.color(QPalette.ColorRole.Window).name(), DARK.window)
        self.assertIs(current_theme(), DARK)
        self.assertIn(DARK.statuses["tagged"].background, status_legend_html())
        self.assertEqual(self.settings.value("theme"), "Dark")
        checked = [action.text() for action in window.theme_actions.actions() if action.isChecked()]
        self.assertEqual(checked, ["Dark"])

        window.set_theme_mode("Light")
        self.assertEqual(
            QApplication.instance().palette().color(QPalette.ColorRole.Window).name(),
            LIGHT.window,
        )
        self.assertIn(LIGHT.statuses["tagged"].background, window.explorer_tab.status_legend.text())

    def test_tag_filter_supports_and_or_and_not(self) -> None:
        window = self.open_window()
        explorer = window.explorer_tab
        panel = explorer.tag_filter.panel
        explorer.load_folder(self.media)
        wait_until(lambda: len(self.visible_names(window)) == 4)
        self.assertEqual(self.visible_names(window), ["alice.jpg", "both.jpg", "none.jpg", "sub"])

        panel.set_tag("Alice", "has")
        self.assertEqual(self.visible_names(window), ["alice.jpg", "both.jpg"])
        panel.set_tag("Beach", "has")  # AND
        self.assertEqual(self.visible_names(window), ["both.jpg"])
        self.assertIn("all of: Alice, Beach", window.statusBar().currentMessage())
        self.assertEqual(explorer.tag_filter.text(), "Tags (2)")

        panel.set_match_all(False)  # OR
        self.assertEqual(self.visible_names(window), ["alice.jpg", "both.jpg"])
        panel.clear()
        panel.set_tag("Beach", "not")  # NOT keeps untagged files
        self.assertEqual(self.visible_names(window), ["alice.jpg", "none.jpg"])

        panel.clear()
        self.assertEqual(len(self.visible_names(window)), 4)
        self.assertEqual(explorer.tag_filter.text(), "Tags")

    def test_tag_picker_drops_tags_removed_from_taxonomy(self) -> None:
        button = TagFilterButton()
        changes = []
        button.query_changed.connect(changes.append)
        button.set_taxonomy(TAXONOMY)
        button.panel.set_tag("Alice", "has")
        button.panel.set_tag("City", "not")

        button.set_taxonomy({"People": ["Alice"]})

        self.assertEqual(button.query().include, {"Alice"})
        self.assertEqual(button.query().exclude, frozenset())
        self.assertEqual(changes[-1], button.query())

    def test_has_and_not_are_exclusive_for_a_tag(self) -> None:
        button = TagFilterButton()
        button.set_taxonomy(TAXONOMY)
        button.panel.set_tag("Bob", "has")
        item = button.panel._items["Bob"]
        item.setCheckState(2, Qt.CheckState.Checked)  # tick "Not"
        self.assertEqual(item.checkState(1), Qt.CheckState.Unchecked)
        self.assertEqual(button.query().exclude, {"Bob"})
        self.assertEqual(button.query().include, frozenset())

    def test_toolbar_buttons_follow_action_state_and_rare_commands_are_in_more(self) -> None:
        explorer = self.open_window().explorer_tab
        buttons = {
            button.defaultAction(): button
            for button in explorer.controls.findChildren(type(explorer.back_button))
            if button.defaultAction() is not None
        }
        self.assertFalse(explorer.paste_action.isEnabled())
        self.assertFalse(buttons[explorer.paste_action].isEnabled())
        self.assertEqual(buttons[explorer.index_action].objectName(), "primaryButton")
        self.assertEqual(buttons[explorer.delete_action].objectName(), "dangerButton")
        more = next(
            button for button in explorer.controls.findChildren(type(explorer.back_button))
            if button.text() == "More"
        )
        self.assertEqual(
            [action.text() for action in more.menu().actions() if not action.isSeparator()],
            ["Load tags.json…", "Copy random media…", "Rename files with GUIDs…"],
        )

    def test_tags_by_path_returns_only_tagged_paths(self) -> None:
        paths = [self.media / name for name in ("both.jpg", "alice.jpg", "none.jpg")]
        self.assertEqual(
            self.database.tags_by_path(paths),
            {
                str(self.media / "both.jpg"): {"Alice", "Beach"},
                str(self.media / "alice.jpg"): {"Alice"},
            },
        )


if __name__ == "__main__":
    unittest.main()
