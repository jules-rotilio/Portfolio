"""Tests for catalog tag search, grid view, Ctrl+F, and preferences."""

import os
import random
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QSettings, QThreadPool
from PySide6.QtWidgets import QApplication

from media_toolkit.app_settings import AppSettings, load_settings, save_settings
from media_toolkit.core.database import MediaDatabase, MediaRecord
from media_toolkit.core.tag_query import TagQuery
from media_toolkit.ui.filter_model import PATH_ROLE
from media_toolkit.ui.main_window import MainWindow
from media_toolkit.ui.settings_dialog import SettingsDialog
from test_background import dispose, wait_until

TAXONOMY = {"People": ["Alice", "Bob"], "Places": ["Beach", "City"]}


class TagQueryTests(unittest.TestCase):
    """AND, OR, and NOT conditions on one file's tags."""

    def test_matches_all_any_and_none(self) -> None:
        both = {"Alice", "Beach"}
        self.assertTrue(TagQuery(frozenset({"Alice", "Beach"})).matches(both))
        self.assertFalse(TagQuery(frozenset({"Alice", "City"})).matches(both))
        self.assertTrue(TagQuery(frozenset({"Alice", "City"}), match_all=False).matches(both))
        self.assertFalse(TagQuery(exclude=frozenset({"Beach"})).matches(both))
        self.assertTrue(TagQuery(exclude=frozenset({"Beach"})).matches(set()))
        self.assertEqual(
            TagQuery(frozenset({"B", "A"}), frozenset({"C"}), match_all=False).describe(),
            "any of: A, B; none of: C",
        )


class CatalogSearchAndGridTests(unittest.TestCase):
    """Whole-catalog search, grid mode, Ctrl+F, and preferences in the window."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.application = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.root = Path(temporary_directory.name)
        self.trips = self.root / "trips"
        self.home = self.root / "home"
        for folder in (self.trips, self.home):
            folder.mkdir()
        colours = {"beach.png": "orange", "city.png": "grey", "family.png": "green"}
        for name, colour in colours.items():
            folder = self.home if name == "family.png" else self.trips
            Image.new("RGB", (400, 300), colour).save(folder / name)
        self.database = MediaDatabase(self.root / "catalog.sqlite3")
        self.addCleanup(self.database.close)
        self.database.update_taxonomy(TAXONOMY)
        self.database.save_tags(self.trips / "beach.png", {"Alice", "Beach"})
        self.database.save_tags(self.trips / "city.png", {"Bob", "City"})
        self.database.save_tags(self.home / "family.png", {"Alice", "Bob"})
        self.settings = QSettings(str(self.root / "settings.ini"), QSettings.Format.IniFormat)

    def open_window(self) -> MainWindow:
        with patch.object(MainWindow, "_load_startup_directory"):
            window = MainWindow(self.database, self.settings)
        self.addCleanup(QThreadPool.globalInstance().waitForDone)
        self.addCleanup(dispose, window)
        self.addCleanup(lambda: window.explorer_tab.thumbnail_cache.wait_for_done())
        return window

    def shown_names(self, explorer) -> list[str]:
        view = explorer.file_view
        model = view.model()
        root = view.rootIndex()
        return sorted(model.index(row, 0, root).data() for row in range(model.rowCount(root)))

    def test_database_search_by_tags_across_folders(self) -> None:
        names = lambda query: sorted(Path(p).name for p in self.database.search_by_tags(query))
        self.assertEqual(names(TagQuery(frozenset({"Alice"}))), ["beach.png", "family.png"])
        self.assertEqual(names(TagQuery(frozenset({"Alice", "Bob"}))), ["family.png"])
        self.assertEqual(
            names(TagQuery(frozenset({"Beach", "City"}), match_all=False)), ["beach.png", "city.png"]
        )
        self.assertEqual(names(TagQuery(frozenset({"Alice"}), frozenset({"Beach"}))), ["family.png"])
        (self.home / "family.png").unlink()
        self.assertEqual(names(TagQuery(frozenset({"Alice"}))), ["beach.png"])

    def test_whole_catalog_search_lists_files_from_every_folder(self) -> None:
        window = self.open_window()
        explorer = window.explorer_tab
        explorer.load_folder(self.trips)
        panel = explorer.tag_filter.panel
        panel.set_whole_catalog(True)
        panel.set_tag("Alice", "has")
        wait_until(lambda: explorer._catalog_mode)
        self.assertEqual(self.shown_names(explorer), ["beach.png", "family.png"])
        self.assertFalse(explorer.results_bar.isHidden())
        self.assertIn("Whole catalog: 2 file(s) with all of: Alice", explorer.results_banner.text())

        explorer.file_view.selectAll()
        self.assertEqual(
            sorted(path.name for path in explorer.selected_paths()), ["beach.png", "family.png"]
        )
        self.assertFalse(explorer.paste_action.isEnabled())

        explorer.show_in_folder(self.home / "family.png")
        self.assertFalse(explorer._catalog_mode)
        self.assertEqual(explorer.current_folder, self.home.resolve())
        self.assertTrue(explorer.results_bar.isHidden())

    def test_grid_view_shares_selection_and_shows_thumbnails(self) -> None:
        window = self.open_window()
        window.show()
        explorer = window.explorer_tab
        explorer.load_folder(self.trips)
        wait_until(lambda: len(self.shown_names(explorer)) == 2)
        explorer.grid_view_button.setChecked(True)
        self.assertIs(explorer.active_view(), explorer.grid_view)
        self.assertIs(explorer.grid_view.selectionModel(), explorer.file_view.selectionModel())
        self.assertEqual(self.settings.value("explorer_view"), "grid")

        grid = explorer.grid_view
        index = grid.model().index(0, 0, grid.rootIndex())
        grid.setCurrentIndex(index)
        self.assertEqual([path.name for path in explorer.selected_paths()], [Path(index.data(PATH_ROLE)).name])

        cache = explorer.thumbnail_cache
        path = index.data(PATH_ROLE)
        self.assertIsNone(cache.thumbnail(path))  # queued
        wait_until(lambda: cache.thumbnail(path) is not None)
        pixmap = cache.thumbnail(path)
        self.assertLessEqual(max(pixmap.width(), pixmap.height()), cache.size)

    def test_ctrl_f_focuses_the_name_filter(self) -> None:
        window = self.open_window()
        window.explorer_tab.search_input.setText("beach")
        window.tabs.setCurrentWidget(window.duplicates_tab)
        window.focus_search()
        self.assertIs(window.tabs.currentWidget(), window.explorer_tab)
        self.assertEqual(window.explorer_tab.search_input.selectedText(), "beach")

    def test_preferences_round_trip_and_reach_the_tabs(self) -> None:
        self.settings.setValue("duplicate_distance", 99)  # out of range
        self.assertEqual(load_settings(self.settings).duplicate_distance, 8)

        window = self.open_window()
        dialog = SettingsDialog(window.preferences)
        dialog._spins["thumbnail_size"].setValue(200)
        dialog._spins["index_threads"].setValue(1)
        dialog._spins["duplicate_distance"].setValue(5)
        dialog._spins["duplicate_min_frames"].setValue(6)
        dialog.theme.setCurrentText("Dark")
        window.apply_preferences(dialog.settings(), save=True)

        self.assertEqual(window.explorer_tab.thumbnail_cache.size, 200)
        self.assertEqual(window.explorer_tab.index_threads, 1)
        self.assertEqual((window.duplicates_tab.distance, window.duplicates_tab.min_frames), (5, 6))
        saved = load_settings(self.settings)
        self.assertEqual((saved.thumbnail_size, saved.theme), (200, "Dark"))
        window.set_theme_mode("Light")

        save_settings(self.settings, AppSettings())
        self.assertEqual(load_settings(self.settings), AppSettings())


class DuplicateThresholdTests(unittest.TestCase):
    """Bucketed matching finds exactly the pairs a brute-force scan finds."""

    def test_matches_brute_force_at_every_distance(self) -> None:
        generator = random.Random(7)
        base = [generator.getrandbits(64) for _ in range(12)]
        hashes = []
        for value in base:
            hashes.append(value)
            for flips in (3, 6, 9, 12):  # near copies at growing distances
                variant = value
                for bit in generator.sample(range(64), flips):
                    variant ^= 1 << bit
                hashes.append(variant)
        with tempfile.TemporaryDirectory() as temporary_directory:
            with MediaDatabase(Path(temporary_directory) / "c.sqlite3") as database:
                database.save_records(
                    [
                        MediaRecord(f"/x/{index}.png", "/x", 1, 1, f"sha{index}", f"{value:016x}", "image", {})
                        for index, value in enumerate(hashes)
                    ]
                )
                for distance in (0, 4, 8, 12, 16):
                    expected = self.brute_force_groups(hashes, distance)
                    found = {
                        frozenset(int(path.stem) for path in paths)
                        for _, paths in database.duplicate_groups(distance=distance)
                    }
                    self.assertEqual(found, expected, f"distance {distance}")

    @staticmethod
    def brute_force_groups(hashes: list[int], distance: int) -> set[frozenset[int]]:
        parents = list(range(len(hashes)))

        def find(index: int) -> int:
            while parents[index] != index:
                index = parents[index]
            return index

        for left in range(len(hashes)):
            for right in range(left + 1, len(hashes)):
                if (hashes[left] ^ hashes[right]).bit_count() <= distance:
                    parents[find(right)] = find(left)
        groups: dict[int, set[int]] = {}
        for index in range(len(hashes)):
            groups.setdefault(find(index), set()).add(index)
        return {frozenset(group) for group in groups.values() if len(group) > 1}


if __name__ == "__main__":
    unittest.main()
