"""Regression tests for media database grouping and taxonomy behavior.
"""

import gc
import sqlite3
import tempfile
import time
import unittest
import warnings
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from media_toolkit.core.database import MediaDatabase, MediaRecord


class MediaDatabaseTests(unittest.TestCase):
    """Exercises database behavior for duplicate groups and tag records."""
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        self.database = MediaDatabase(self.root / "catalog.sqlite3")
        self.database.update_taxonomy({"People": ["One", "Two"], "Misc": ["Animated"]})

    def tearDown(self) -> None:
        self.database.close()
        self.temporary_directory.cleanup()

    def record(
        self,
        path: Path,
        digest: str,
        *,
        perceptual_hash: str | None = None,
        media_type: str = "image",
    ) -> MediaRecord:
        """Build a MediaRecord fixture with optional perceptual-hash metadata."""
        return MediaRecord(
            path=str(path),
            root=str(path.parent),
            size=10,
            mtime_ns=1,
            sha256=digest,
            perceptual_hash=perceptual_hash,
            media_type=media_type,
            metadata={"duration": 1},
        )

    def test_tracks_index_state_tags_and_duplicate_groups(self) -> None:
        first = self.root / "first.png"
        second = self.root / "second.png"
        self.assertEqual(
            self.database.status_map([first]),
            {str(first): "not-indexed"},
        )
        self.database.save_records(
            [
                self.record(first, "same-sha", perceptual_hash="0000000000000000"),
                self.record(second, "same-sha", perceptual_hash="0000000000000000"),
            ]
        )
        self.assertEqual(self.database.status_map([first])[str(first)], "duplicate")
        self.database.save_tags(first, {"One"})
        self.assertEqual(self.database.tags_for(first), {"One"})
        self.assertEqual(self.database.status_map([first])[str(first)], "duplicate")
        groups = self.database.duplicate_groups()
        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0][1]), {first, second})

    def test_finds_perceptually_similar_images_with_distinct_file_hashes(self) -> None:
        first = self.root / "first.png"
        second = self.root / "second.png"
        self.database.save_records(
            [
                self.record(first, "sha-one", perceptual_hash="0000000000000000"),
                self.record(second, "sha-two", perceptual_hash="0000000000000003"),
            ]
        )

        groups = self.database.duplicate_groups()

        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0][1]), {first, second})

    def test_finds_videos_matching_across_four_of_five_sampled_frames(self) -> None:
        first = self.root / "first.mp4"
        second = self.root / "second.mp4"
        unrelated = self.root / "unrelated.mp4"

        def video_hashes(values: list[int]) -> str:
            return "video-v1:" + ",".join(f"{value:016x}" for value in values)

        self.database.save_records(
            [
                self.record(
                    first,
                    "sha-first",
                    media_type="video",
                    perceptual_hash=video_hashes([0, 1, 2, 3, 4]),
                ),
                self.record(
                    second,
                    "sha-second",
                    media_type="video",
                    perceptual_hash=video_hashes([1, 2, 3, 4, 2**64 - 1]),
                ),
                self.record(
                    unrelated,
                    "sha-unrelated",
                    media_type="video",
                    perceptual_hash=video_hashes(
                        [
                            0,
                            1,
                            2,
                            0xAAAAAAAAAAAAAAAA,
                            0x5555555555555555,
                        ]
                    ),
                ),
            ]
        )

        groups = self.database.duplicate_groups()

        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0][1]), {first, second})

    def test_matches_still_image_to_any_similar_sampled_video_frame(self) -> None:
        image = self.root / "frame.png"
        video = self.root / "clip.mp4"

        self.database.save_records(
            [
                self.record(
                    image, "sha-image", perceptual_hash=f"{42:016x}"
                ),
                self.record(
                    video,
                    "sha-video",
                    media_type="video",
                    perceptual_hash="frames-v1:"
                    + ",".join(f"{value:016x}" for value in [0, 42, 3, 4, 5]),
                ),
            ]
        )

        groups = self.database.duplicate_groups()

        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0][1]), {image, video})

    def test_matches_animated_image_sequences_to_video_sequences(self) -> None:
        animation = self.root / "animation.gif"
        video = self.root / "clip.mp4"
        hashes = "frames-v1:" + ",".join(f"{value:016x}" for value in [1, 2, 3, 4, 5])

        self.database.save_records(
            [
                self.record(
                    animation,
                    "sha-animation",
                    media_type="image",
                    perceptual_hash=hashes,
                ),
                self.record(
                    video,
                    "sha-video",
                    media_type="video",
                    perceptual_hash=hashes,
                ),
            ]
        )

        groups = self.database.duplicate_groups()

        self.assertEqual(len(groups), 1)
        self.assertEqual(set(groups[0][1]), {animation, video})

    def test_dismisses_and_restores_duplicate_groups(self) -> None:
        first = self.root / "first.png"
        second = self.root / "second.png"
        self.database.save_records(
            [self.record(first, "same-sha"), self.record(second, "same-sha")]
        )

        group_key, paths = self.database.duplicate_groups()[0]
        self.database.set_duplicate_group_dismissed(group_key, True)

        self.assertEqual(self.database.duplicate_groups(), [])
        self.assertEqual(
            self.database.duplicate_groups(include_dismissed=True),
            [(group_key, paths)],
        )
        self.assertEqual(self.database.status_map([first])[str(first)], "indexed")

        self.database.close()
        self.database = MediaDatabase(self.root / "catalog.sqlite3")
        self.assertEqual(self.database.duplicate_groups(), [])
        self.database.set_duplicate_group_dismissed(group_key, False)
        self.assertEqual(len(self.database.duplicate_groups()), 1)

    def test_removes_missing_media_and_tags(self) -> None:
        existing = self.root / "existing.png"
        removed = self.root / "removed.png"
        existing.touch()
        removed.touch()
        self.database.save_records(
            [self.record(existing, "existing"), self.record(removed, "removed")]
        )
        self.database.save_tags(removed, {"One"})
        removed.unlink()

        self.assertEqual(self.database.remove_missing_media(), 1)
        self.assertEqual(self.database.cached_records([removed]), {})
        self.assertEqual(self.database.tags_for(removed), set())
        self.assertEqual(self.database.cached_records([existing]).keys(), {str(existing)})

    def test_relocates_media_records_and_tags_for_files_and_directories(self) -> None:
        source = self.root / "source"
        child = source / "nested" / "item.png"
        destination = self.root / "destination"
        self.database.save_records(
            [
                self.record(child, "sha-child"),
            ]
        )
        self.database.save_tags(child, {"One"})

        self.database.relocate_path(source, destination, copy=False)

        new_child = destination / "nested" / "item.png"
        self.assertEqual(self.database.tags_for(new_child), {"One"})
        self.assertEqual(self.database.cached_records([new_child])[str(new_child)].sha256, "sha-child")
        self.assertEqual(self.database.tags_for(child), set())

    def test_copying_database_tags_does_not_mark_file_as_indexed(self) -> None:
        source = self.root / "source.png"
        copy = self.root / "copy.png"
        self.database.save_records([self.record(source, "sha-source")])
        self.database.save_tags(source, {"Two"})

        self.database.relocate_path(source, copy, copy=True)

        self.assertEqual(self.database.tags_for(copy), {"Two"})
        self.assertEqual(self.database.status_map([copy])[str(copy)], "not-indexed")

    def test_saves_and_loads_named_workflows(self) -> None:
        steps = [{"operation": "Trim", "start": "0", "duration": "3"}]
        self.database.save_workflow("Short clip", steps)
        self.assertEqual(self.database.workflows(), {"Short clip": steps})

    def test_replacing_tag_taxonomy_removes_obsolete_assignments(self) -> None:
        media = self.root / "file.png"
        self.database.save_tags(media, {"One"})

        self.database.update_taxonomy({"People": ["New tag"]})

        self.assertEqual(self.database.tags_for(media), set())

    def test_reloading_tag_taxonomy_keeps_assignments_of_retained_tags(self) -> None:
        media = self.root / "file.png"
        self.database.save_tags(media, {"One", "Two", "Animated"})

        # "One" stays put, "Animated" moves category, "Two" and "Misc" are dropped.
        self.database.update_taxonomy(
            {"Effects": ["Animated", "Looping"], "People": ["One"]}
        )

        self.assertEqual(self.database.tags_for(media), {"One", "Animated"})
        self.assertEqual(
            self.database.taxonomy(),
            {"Effects": ["Animated", "Looping"], "People": ["One"]},
        )

    def test_reloading_identical_tag_taxonomy_is_lossless(self) -> None:
        media = self.root / "file.png"
        self.database.save_tags(media, {"One", "Animated"})

        self.database.update_taxonomy({"People": ["One", "Two"], "Misc": ["Animated"]})

        self.assertEqual(self.database.tags_for(media), {"One", "Animated"})

    def test_keeps_records_and_tags_under_unavailable_scan_root(self) -> None:
        unmounted_root = self.root / "unmounted-drive"
        offline = unmounted_root / "photo.png"
        missing = self.root / "missing.png"
        self.database.save_records(
            [
                self.record(offline, "offline"),
                self.record(missing, "missing"),
            ]
        )
        self.database.save_tags(offline, {"One"})

        self.assertEqual(self.database.remove_missing_media(), 1)
        self.assertEqual(self.database.cached_records([offline]).keys(), {str(offline)})
        self.assertEqual(self.database.tags_for(offline), {"One"})
        self.assertEqual(self.database.cached_records([missing]), {})

    def test_uses_write_ahead_logging(self) -> None:
        with closing(sqlite3.connect(self.database.database_path)) as connection:
            journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
        self.assertEqual(journal_mode, "wal")

    def test_reuses_one_connection_until_closed(self) -> None:
        media = self.root / "file.png"
        with patch("media_toolkit.core.database.sqlite3.connect", wraps=sqlite3.connect) as connect:
            self.database.save_records([self.record(media, "sha")])
            self.database.save_tags(media, {"One"})
            self.database.tags_for(media)
            self.database.taxonomy()
        self.assertEqual(connect.call_count, 0)
        with self.database._connect() as connection:
            synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
        self.assertEqual(synchronous, 1)  # NORMAL

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always", ResourceWarning)
            self.database.close()
            gc.collect()
        self.assertEqual(
            [str(w.message) for w in caught if issubclass(w.category, ResourceWarning)],
            [],
        )
        # A closed catalog reopens on its next use.
        self.assertEqual(self.database.tags_for(media), {"One"})

    def test_reads_are_not_blocked_by_an_open_write_transaction(self) -> None:
        media = self.root / "file.png"
        self.database.save_tags(media, {"One"})
        with closing(sqlite3.connect(self.database.database_path)) as writer:
            writer.execute("PRAGMA foreign_keys = ON")
            writer.execute("BEGIN EXCLUSIVE")
            writer.execute(
                "INSERT INTO media_tags(path, tag) VALUES (?, 'Two')", (str(media),)
            )
            started = time.monotonic()
            self.assertEqual(self.database.tags_for(media), {"One"})
            self.assertLess(time.monotonic() - started, 1)
            writer.rollback()

    def test_failed_write_is_rolled_back(self) -> None:
        media = self.root / "file.png"
        self.database.save_tags(media, {"One"})

        with self.assertRaises(sqlite3.IntegrityError):
            self.database.save_tags(media, {"Not in taxonomy"})

        self.assertEqual(self.database.tags_for(media), {"One"})

    def relocated_root(self, path: Path) -> str:
        """Return the stored scan root of the record at path."""
        return self.database.cached_records([path])[str(path)].root

    def test_relocation_keeps_records_under_their_scan_root(self) -> None:
        photos = self.root / "photos"
        other_scan = self.root / "videos"
        nested = photos / "trip" / "beach.png"
        self.database.save_records(
            [
                replace(self.record(nested, "beach"), root=str(photos)),
                replace(self.record(other_scan / "clip.png", "clip"), root=str(other_scan)),
            ]
        )

        # Renamed inside the scan root: the root is unchanged.
        renamed = photos / "trip" / "sea.png"
        self.database.relocate_path(nested, renamed, copy=False)
        self.assertEqual(self.relocated_root(renamed), str(photos))

        # Moved into another scanned folder: that folder becomes the root.
        moved = other_scan / "sub" / "sea.png"
        self.database.relocate_path(renamed, moved, copy=False)
        self.assertEqual(self.relocated_root(moved), str(other_scan))

        # Moved outside every scanned folder: the folder it was pasted into.
        outside = self.root / "elsewhere" / "sea.png"
        self.database.relocate_path(moved, outside, copy=False)
        self.assertEqual(self.relocated_root(outside), str(self.root / "elsewhere"))

    def test_renaming_the_scan_root_moves_the_root_with_it(self) -> None:
        photos = self.root / "photos"
        kept = photos / "kept.png"
        deleted = photos / "sub" / "deleted.png"
        for path in (kept, deleted):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        self.database.save_records(
            [
                replace(self.record(kept, "kept"), root=str(photos)),
                replace(self.record(deleted, "deleted"), root=str(photos)),
            ]
        )
        renamed_root = self.root / "pictures"
        photos.rename(renamed_root)
        self.database.relocate_path(photos, renamed_root, copy=False)
        (renamed_root / "sub" / "deleted.png").unlink()

        self.assertEqual(self.relocated_root(renamed_root / "kept.png"), str(renamed_root))
        # The moved root exists, so the deleted file is still pruned.
        self.assertEqual(self.database.remove_missing_media(), 1)
        self.assertEqual(
            set(self.database.cached_records([renamed_root / "kept.png"])),
            {str(renamed_root / "kept.png")},
        )


if __name__ == "__main__":
    unittest.main()
