"""SQLite storage for indexed media, tags, duplicate decisions, and workflows."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from media_toolkit.core.tag_query import TagQuery

LOGGER = logging.getLogger(__name__)


# Defaults for duplicate_groups; users can change both in the settings dialog.
# Maximum differing bits for still-image pairs and corresponding frame pHashes
# (64-bit hashes).
DEFAULT_DUPLICATE_DISTANCE = 8
# Frame sequences match when at least this many corresponding frames are within
# that distance; short sequences lower the required count. At most the frame
# sample count configured in indexer.py.
DEFAULT_DUPLICATE_MIN_FRAMES = 4


def _hash_chunks(distance: int) -> list[tuple[int, int]]:
    """Split a 64-bit hash into distance + 1 (offset, width) slices.

    Two hashes within ``distance`` differing bits must agree on at least one
    slice (pigeonhole), so comparing only hashes that share a slice finds
    every match.
    """
    count = distance + 1
    base, extra = divmod(64, count)
    chunks: list[tuple[int, int]] = []
    offset = 0
    for index in range(count):
        width = base + (1 if index < extra else 0)
        chunks.append((offset, width))
        offset += width
    return chunks


def _perceptual_hash_frames(value: str | None) -> tuple[int, ...] | None:
    """Decode a stored still-image or frame-sequence pHash, if valid."""
    if value is None:
        return None
    if value.startswith("frames-v1:"):
        encoded_hashes = value.removeprefix("frames-v1:").split(",")
    elif value.startswith("video-v1:"):
        encoded_hashes = value.removeprefix("video-v1:").split(",")
    else:
        encoded_hashes = [value]
    if not encoded_hashes or any(len(item) != 16 for item in encoded_hashes):
        return None
    try:
        return tuple(int(perceptual_hash, 16) for perceptual_hash in encoded_hashes)
    except ValueError:
        return None


# Paths per "IN (...)" query; well below SQLite's bound-parameter limit.
_QUERY_CHUNK_SIZE = 500


def _chunks(items: list[str], size: int = _QUERY_CHUNK_SIZE) -> list[list[str]]:
    """Split items into consecutive lists of at most size elements."""
    return [items[start : start + size] for start in range(0, len(items), size)]


def _placeholders(items: list[str]) -> str:
    """Return "?, ?, ..." with one parameter marker per item."""
    return ", ".join("?" * len(items))


def _is_within(path: str, folder: str) -> bool:
    """Return whether path is folder itself or lies below it."""
    return path == folder or path.startswith(folder.rstrip("/") + "/")


def _relocated_root(
    root: str,
    new_path: str,
    source: str,
    destination: str,
    known_roots: list[str],
) -> str:
    """Choose the scan root for a record moved from below source to new_path.

    A root that was itself moved (e.g. the indexed folder was renamed) moves
    with it. Otherwise the root is kept while the file stays below it, or
    replaced by the deepest other scan root now containing the file. A file
    moved outside every scan root gets the folder it was moved into.
    """
    if _is_within(root, source):
        return destination + root[len(source) :]
    if _is_within(new_path, root):
        return root
    containing = [known for known in known_roots if _is_within(new_path, known)]
    if containing:
        return max(containing, key=len)
    return str(Path(destination).parent)


@dataclass(frozen=True)
class MediaRecord:
    """Indexed metadata and hashes for one media file."""

    path: str
    root: str
    size: int
    mtime_ns: int
    sha256: str
    perceptual_hash: str | None
    media_type: str
    metadata: dict[str, Any]


class MediaDatabase:
    """Persist the media catalog and app-managed metadata in SQLite.

    Each instance keeps one connection open until close(). Reopening a
    connection per operation made every write checkpoint the WAL and sync the
    disk (about 17 ms per tag save versus 0.2 ms). Threads that work in
    parallel should use separate instances; calls on one instance are
    serialized by a lock.
    """

    def __init__(self, database_path: Path) -> None:
        """Create the database directory and initialize missing catalog tables."""
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection: sqlite3.Connection | None = None
        with self._connect() as connection:
            # WAL is persistent in the file and lets UI reads proceed while a
            # background worker writes, instead of waiting on the busy timeout.
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if journal_mode.lower() != "wal":
                LOGGER.warning(
                    "SQLite WAL mode unavailable for %s; using %s journal",
                    self.database_path,
                    journal_mode,
                )
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                CREATE TABLE IF NOT EXISTS media (
                    path TEXT PRIMARY KEY,
                    root TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    sha256 TEXT NOT NULL,
                    perceptual_hash TEXT,
                    media_type TEXT NOT NULL DEFAULT 'other',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    indexed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS media_sha256_idx ON media(sha256);
                CREATE TABLE IF NOT EXISTS dismissed_duplicate_groups (
                    group_key TEXT PRIMARY KEY
                );
                CREATE TABLE IF NOT EXISTS tag_categories (
                    category TEXT PRIMARY KEY,
                    position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tag_definitions (
                    tag TEXT PRIMARY KEY,
                    category TEXT NOT NULL REFERENCES tag_categories(category)
                        ON DELETE CASCADE,
                    position INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS media_tags (
                    path TEXT NOT NULL,
                    tag TEXT NOT NULL REFERENCES tag_definitions(tag) ON DELETE CASCADE,
                    PRIMARY KEY (path, tag)
                );
                CREATE TABLE IF NOT EXISTS workflows (
                    name TEXT PRIMARY KEY,
                    steps_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def close(self) -> None:
        """Close the connection; a later call on this instance reopens it."""
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None

    def __enter__(self) -> MediaDatabase:
        """Use the catalog in a with-block that closes it afterwards."""
        return self

    def __exit__(self, *_exc_info: object) -> None:
        """Close the connection when leaving a with-block."""
        self.close()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        """Yield the shared connection inside one transaction.

        Commits on success and rolls back on an exception.
        """
        with self._lock:
            if self._connection is None:
                connection = sqlite3.connect(
                    self.database_path, timeout=15, check_same_thread=False
                )
                connection.row_factory = sqlite3.Row
                connection.execute("PRAGMA foreign_keys = ON")
                # With WAL, NORMAL syncs at checkpoints rather than on every
                # commit: the file cannot be corrupted, but a power cut may
                # lose the last moments of changes. An app crash loses nothing.
                connection.execute("PRAGMA synchronous = NORMAL")
                self._connection = connection
            with self._connection:
                yield self._connection

    def cached_records(self, paths: list[Path]) -> dict[str, MediaRecord]:
        """Load cached records for the requested paths, keyed by stored path."""
        records: dict[str, MediaRecord] = {}
        if not paths:
            return records
        with self._connect() as connection:
            for chunk in _chunks([str(path) for path in paths]):
                rows = connection.execute(
                    "SELECT path, root, size, mtime_ns, sha256, perceptual_hash, "
                    "media_type, metadata_json "
                    f"FROM media WHERE path IN ({_placeholders(chunk)})",
                    chunk,
                ).fetchall()
                for row in rows:
                    records[row["path"]] = MediaRecord(
                        path=row["path"],
                        root=row["root"],
                        size=row["size"],
                        mtime_ns=row["mtime_ns"],
                        sha256=row["sha256"],
                        perceptual_hash=row["perceptual_hash"],
                        media_type=row["media_type"],
                        metadata=json.loads(row["metadata_json"]),
                    )
        return records

    def save_records(self, records: list[MediaRecord]) -> None:
        """Insert or replace indexed records without changing their tags."""
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO media(
                    path, root, size, mtime_ns, sha256, perceptual_hash,
                    media_type, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    root = excluded.root,
                    size = excluded.size,
                    mtime_ns = excluded.mtime_ns,
                    sha256 = excluded.sha256,
                    perceptual_hash = excluded.perceptual_hash,
                    media_type = excluded.media_type,
                    metadata_json = excluded.metadata_json,
                    indexed_at = CURRENT_TIMESTAMP
                """,
                [
                    (
                        record.path,
                        record.root,
                        record.size,
                        record.mtime_ns,
                        record.sha256,
                        record.perceptual_hash,
                        record.media_type,
                        json.dumps(record.metadata, sort_keys=True),
                    )
                    for record in records
                ],
            )

    def update_taxonomy(self, categories: dict[str, list[str]]) -> None:
        """Replace the ordered category/tag definitions.

        Definitions are upserted in place so that assignments of tags kept in
        the new taxonomy survive; only tags absent from it lose their
        assignments (through the media_tags cascade).
        """
        new_tags = [tag for tags in categories.values() for tag in tags]
        with self._connect() as connection:
            for category_position, (category, tags) in enumerate(categories.items()):
                connection.execute(
                    """
                    INSERT INTO tag_categories(category, position) VALUES (?, ?)
                    ON CONFLICT(category) DO UPDATE SET position = excluded.position
                    """,
                    (category, category_position),
                )
                for tag_position, tag in enumerate(tags):
                    connection.execute(
                        """
                        INSERT INTO tag_definitions(tag, category, position)
                        VALUES (?, ?, ?)
                        ON CONFLICT(tag) DO UPDATE SET
                            category = excluded.category,
                            position = excluded.position
                        """,
                        (tag, category, tag_position),
                    )
            connection.execute(
                f"DELETE FROM tag_definitions WHERE tag NOT IN "
                f"({', '.join('?' * len(new_tags))})",
                new_tags,
            )
            connection.execute(
                f"DELETE FROM tag_categories WHERE category NOT IN "
                f"({', '.join('?' * len(categories))})",
                list(categories),
            )

    def taxonomy(self) -> dict[str, list[str]]:
        """Return tag definitions in their stored category and tag order."""
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT c.category, d.tag
                FROM tag_categories c
                LEFT JOIN tag_definitions d ON d.category = c.category
                ORDER BY c.position, d.position
                """
            ).fetchall()
        taxonomy: dict[str, list[str]] = {}
        for row in rows:
            tags = taxonomy.setdefault(row["category"], [])
            if row["tag"] is not None:
                tags.append(row["tag"])
        return taxonomy

    def tags_for(self, path: Path) -> set[str]:
        """Return the assigned tags for one exact path."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT tag FROM media_tags WHERE path = ?", (str(path),)
            ).fetchall()
        return {row["tag"] for row in rows}

    def tags_by_path(self, paths: list[Path]) -> dict[str, set[str]]:
        """Return assigned tags for each of paths that has any, keyed by path."""
        result: dict[str, set[str]] = {}
        with self._connect() as connection:
            for chunk in _chunks([str(path) for path in paths]):
                rows = connection.execute(
                    f"SELECT path, tag FROM media_tags WHERE path IN ({_placeholders(chunk)})",
                    chunk,
                ).fetchall()
                for row in rows:
                    result.setdefault(row["path"], set()).add(row["tag"])
        return result

    def search_by_tags(self, query: TagQuery) -> list[str]:
        """Return catalog paths matching query, sorted, from every folder.

        Candidates are all indexed or tagged paths; files that no longer
        exist on disk are left out.
        """
        with self._connect() as connection:
            if query.include:
                included = sorted(query.include)
                having = (
                    f"HAVING COUNT(DISTINCT tag) = {len(included)}" if query.match_all else ""
                )
                rows = connection.execute(
                    f"""
                    SELECT path FROM media_tags
                    WHERE tag IN ({_placeholders(included)})
                    GROUP BY path {having}
                    """,
                    included,
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT path FROM media UNION SELECT path FROM media_tags"
                ).fetchall()
            paths = {row["path"] for row in rows}
            if query.exclude:
                excluded = sorted(query.exclude)
                paths -= {
                    row["path"]
                    for row in connection.execute(
                        f"SELECT DISTINCT path FROM media_tags "
                        f"WHERE tag IN ({_placeholders(excluded)})",
                        excluded,
                    ).fetchall()
                }
        return sorted(path for path in paths if Path(path).is_file())

    def save_tags(self, path: Path, tags: set[str]) -> None:
        """Replace the assigned tags for one exact path."""
        with self._connect() as connection:
            connection.execute("DELETE FROM media_tags WHERE path = ?", (str(path),))
            connection.executemany(
                "INSERT INTO media_tags(path, tag) VALUES (?, ?)",
                [(str(path), tag) for tag in sorted(tags)],
            )

    def status_map(
        self,
        paths: list[Path],
        duplicate_paths: set[str] | None = None,
    ) -> dict[str, str]:
        """Map paths to not-indexed, indexed, tagged, or duplicate status."""
        result: dict[str, str] = {}
        if not paths:
            return result
        if duplicate_paths is None:
            duplicate_paths = {
                str(path)
                for _, group_paths in self.duplicate_groups()
                for path in group_paths
            }
        has_tags: dict[str, bool] = {}
        with self._connect() as connection:
            for chunk in _chunks([str(path) for path in paths]):
                rows = connection.execute(
                    f"""
                    SELECT
                        m.path,
                        EXISTS(
                            SELECT 1 FROM media_tags mt WHERE mt.path = m.path
                        ) AS has_tags
                    FROM media m WHERE m.path IN ({_placeholders(chunk)})
                    """,
                    chunk,
                ).fetchall()
                has_tags.update((row["path"], bool(row["has_tags"])) for row in rows)
        for path in paths:
            text_path = str(path)
            if text_path not in has_tags:
                result[text_path] = "not-indexed"
            elif text_path in duplicate_paths:
                result[text_path] = "duplicate"
            elif has_tags[text_path]:
                result[text_path] = "tagged"
            else:
                result[text_path] = "indexed"
        return result

    def duplicate_groups(
        self,
        *,
        include_dismissed: bool = False,
        distance: int = DEFAULT_DUPLICATE_DISTANCE,
        min_frames: int = DEFAULT_DUPLICATE_MIN_FRAMES,
    ) -> list[tuple[str, list[Path]]]:
        """Group exact or sufficiently similar media and return stable keys.

        Exact SHA-256 matches always group. Still-image pHashes match at Hamming
        distance <= ``distance``; frame-sequence hashes need at least
        ``min_frames`` corresponding frames within that distance, capped by
        either sequence's length. A still image can also match any sampled
        GIF/video frame within that distance.
        """
        if not 0 <= distance < 64:
            raise ValueError("Duplicate distance must be between 0 and 63 bits.")
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT path, sha256, perceptual_hash, media_type FROM media "
                "WHERE sha256 != '' ORDER BY path"
            ).fetchall()
            dismissed_group_keys = {
                row["group_key"]
                for row in connection.execute(
                    "SELECT group_key FROM dismissed_duplicate_groups"
                ).fetchall()
            }

        if not rows:
            return []
        parents = list(range(len(rows)))

        def find(index: int) -> int:
            """Find a group representative while compressing the search path."""
            while parents[index] != index:
                parents[index] = parents[parents[index]]
                index = parents[index]
            return index

        def union(left: int, right: int) -> None:
            """Merge the groups containing two matching records."""
            root_left = find(left)
            root_right = find(right)
            if root_left != root_right:
                parents[root_right] = root_left

        exact_hash_groups: dict[str, int] = {}
        still_hashes: dict[int, int] = {}
        frame_hashes: dict[int, tuple[int, ...]] = {}
        for index, row in enumerate(rows):
            exact_hash = row["sha256"]
            if exact_hash in exact_hash_groups:
                union(index, exact_hash_groups[exact_hash])
            else:
                exact_hash_groups[exact_hash] = index
            hashes = _perceptual_hash_frames(row["perceptual_hash"])
            if hashes is None:
                continue
            if len(hashes) == 1:
                still_hashes[index] = hashes[0]
            else:
                frame_hashes[index] = hashes

        hash_buckets: dict[tuple[int, int], list[int]] = {}
        chunk_ranges = _hash_chunks(distance)

        def nearby_still_indexes(value: int) -> set[int]:
            """Return likely nearby still-hash candidates from hash buckets."""
            candidate_indexes: set[int] = set()
            for chunk, (offset, width) in enumerate(chunk_ranges):
                key = (chunk, (value >> offset) & ((1 << width) - 1))
                candidate_indexes.update(hash_buckets.get(key, []))
            return candidate_indexes

        for index, value in still_hashes.items():
            candidate_indexes = nearby_still_indexes(value)
            for candidate in candidate_indexes:
                other = still_hashes[candidate]
                if (value ^ other).bit_count() <= distance:
                    union(index, candidate)
            for chunk, (offset, width) in enumerate(chunk_ranges):
                key = (chunk, (value >> offset) & ((1 << width) - 1))
                hash_buckets.setdefault(key, []).append(index)

        sequence_hash_buckets: dict[tuple[int, int, int], list[int]] = {}
        for index, hashes in frame_hashes.items():
            candidate_indexes: set[int] = set()
            for frame_index, value in enumerate(hashes):
                for chunk, (offset, width) in enumerate(chunk_ranges):
                    key = (frame_index, chunk, (value >> offset) & ((1 << width) - 1))
                    candidate_indexes.update(sequence_hash_buckets.get(key, []))
            for candidate in candidate_indexes:
                matching_frames = sum(
                    (left ^ right).bit_count() <= distance
                    for left, right in zip(hashes, frame_hashes[candidate])
                )
                required_matches = min(
                    min_frames,
                    len(hashes),
                    len(frame_hashes[candidate]),
                )
                if matching_frames >= required_matches:
                    union(index, candidate)
            for value in hashes:
                # A still image is a match if it resembles any sampled motion frame.
                for candidate in nearby_still_indexes(value):
                    if (value ^ still_hashes[candidate]).bit_count() <= distance:
                        union(index, candidate)
            for frame_index, value in enumerate(hashes):
                for chunk, (offset, width) in enumerate(chunk_ranges):
                    key = (frame_index, chunk, (value >> offset) & ((1 << width) - 1))
                    sequence_hash_buckets.setdefault(key, []).append(index)

        groups_by_root: dict[int, list[sqlite3.Row]] = {}
        for index, row in enumerate(rows):
            groups_by_root.setdefault(find(index), []).append(row)
        groups: list[tuple[str, list[Path]]] = []
        for group_rows in groups_by_root.values():
            if len(group_rows) < 2:
                continue
            group_key = self._duplicate_group_key(group_rows)
            if not include_dismissed and group_key in dismissed_group_keys:
                continue
            paths = [Path(row["path"]) for row in group_rows]
            groups.append((group_key, paths))
        return sorted(groups, key=lambda entry: str(entry[1][0]).casefold())

    @staticmethod
    def _duplicate_group_key(rows: list[sqlite3.Row]) -> str:
        """Hash sorted path/content-hash pairs to identify a duplicate group."""
        members = sorted((row["path"], row["sha256"]) for row in rows)
        encoded = json.dumps(members, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def set_duplicate_group_dismissed(self, group_key: str, dismissed: bool) -> None:
        """Persist whether a duplicate group should be hidden from review."""
        with self._connect() as connection:
            if dismissed:
                connection.execute(
                    "INSERT OR IGNORE INTO dismissed_duplicate_groups(group_key) VALUES (?)",
                    (group_key,),
                )
            else:
                connection.execute(
                    "DELETE FROM dismissed_duplicate_groups WHERE group_key = ?",
                    (group_key,),
                )

    def dismissed_duplicate_group_keys(self) -> set[str]:
        """Return keys of duplicate groups previously dismissed by the user."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT group_key FROM dismissed_duplicate_groups"
            ).fetchall()
        return {row["group_key"] for row in rows}

    def relocate_path(self, source: Path, destination: Path, *, copy: bool) -> None:
        """Copy or move catalog rows and tags below source to destination.

        Moved records keep pointing at the scan root they were indexed under
        (see _relocated_root), which remove_missing_media relies on.
        """
        source_text = str(source)
        destination_text = str(destination)
        prefix = source_text.rstrip("/") + "/"
        with self._connect() as connection:
            media_rows = connection.execute(
                """
                SELECT path, root, size, mtime_ns, sha256, perceptual_hash,
                       media_type, metadata_json
                FROM media
                WHERE path = ? OR substr(path, 1, ?) = ?
                """,
                (source_text, len(prefix), prefix),
            ).fetchall()
            tag_rows = connection.execute(
                """
                SELECT path, tag FROM media_tags
                WHERE path = ? OR substr(path, 1, ?) = ?
                """,
                (source_text, len(prefix), prefix),
            ).fetchall()
            if not copy:
                connection.execute(
                    """
                    DELETE FROM media
                    WHERE path = ? OR substr(path, 1, ?) = ?
                    """,
                    (destination_text, len(destination_text.rstrip("/") + "/"),
                     destination_text.rstrip("/") + "/"),
                )
                connection.execute(
                    """
                    DELETE FROM media_tags
                    WHERE path = ? OR substr(path, 1, ?) = ?
                    """,
                    (destination_text, len(destination_text.rstrip("/") + "/"),
                     destination_text.rstrip("/") + "/"),
                )
            path_map = {
                row["path"]: destination_text + row["path"][len(source_text) :]
                for row in media_rows
            }
            for row in tag_rows:
                new_path = destination_text + row["path"][len(source_text) :]
                if copy:
                    connection.execute(
                        "INSERT OR IGNORE INTO media_tags(path, tag) VALUES (?, ?)",
                        (new_path, row["tag"]),
                    )
                else:
                    connection.execute(
                        "DELETE FROM media_tags WHERE path = ? AND tag = ?",
                        (row["path"], row["tag"]),
                    )
                    connection.execute(
                        "INSERT OR IGNORE INTO media_tags(path, tag) VALUES (?, ?)",
                        (new_path, row["tag"]),
                    )
            if copy:
                return
            known_roots = [
                row["root"]
                for row in connection.execute("SELECT DISTINCT root FROM media")
            ]
            for row in media_rows:
                new_path = path_map[row["path"]]
                new_root = _relocated_root(
                    row["root"], new_path, source_text, destination_text, known_roots
                )
                connection.execute(
                    """
                    UPDATE media SET path = ?, root = ?
                    WHERE path = ?
                    """,
                    (new_path, new_root, row["path"]),
                )

    def remove_path(self, path: Path) -> None:
        """Remove catalog records and tags for a path and its descendants."""
        path_text = str(path)
        prefix = path_text.rstrip("/") + "/"
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM media WHERE path = ? OR substr(path, 1, ?) = ?",
                (path_text, len(prefix), prefix),
            )
            connection.execute(
                "DELETE FROM media_tags WHERE path = ? OR substr(path, 1, ?) = ?",
                (path_text, len(prefix), prefix),
            )

    def remove_missing_media(self) -> int:
        """Delete records for paths that no longer exist and return the count.

        Records under an unavailable scan root (e.g. an unmounted drive) are
        kept, as are paths whose existence cannot be checked, so a temporarily
        missing volume does not erase its catalog entries and tags.
        """
        with self._connect() as connection:
            rows = connection.execute("SELECT path, root FROM media").fetchall()
            missing_paths: list[str] = []
            root_available: dict[str, bool] = {}
            unavailable_records = 0
            for row in rows:
                root = row["root"]
                if root not in root_available:
                    root_available[root] = Path(root).is_dir()
                if not root_available[root]:
                    unavailable_records += 1
                    continue
                try:
                    Path(row["path"]).stat()
                except (FileNotFoundError, NotADirectoryError):
                    missing_paths.append(row["path"])
                except OSError:
                    LOGGER.warning(
                        "Keeping catalog record that could not be checked: %s",
                        row["path"],
                        exc_info=True,
                    )
            if unavailable_records:
                LOGGER.info(
                    "Kept %d record(s) under unavailable scan root(s): %s",
                    unavailable_records,
                    ", ".join(
                        sorted(root for root, ok in root_available.items() if not ok)
                    ),
                )

            connection.executemany(
                "DELETE FROM media_tags WHERE path = ?",
                [(path,) for path in missing_paths],
            )
            connection.executemany(
                "DELETE FROM media WHERE path = ?",
                [(path,) for path in missing_paths],
            )
        return len(missing_paths)

    def save_workflow(self, name: str, steps: list[dict[str, str]]) -> None:
        """Insert or replace a named processing workflow."""
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO workflows(name, steps_json)
                VALUES (?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    steps_json = excluded.steps_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, json.dumps(steps)),
            )

    def workflows(self) -> dict[str, list[dict[str, str]]]:
        """Return saved workflows keyed by name."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT name, steps_json FROM workflows ORDER BY name"
            ).fetchall()
        return {row["name"]: json.loads(row["steps_json"]) for row in rows}
