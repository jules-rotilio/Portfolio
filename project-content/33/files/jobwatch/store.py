"""Historique SQLite : une offre (ou un avertissement) n'est notifiée qu'une seule fois."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import Job

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    key TEXT PRIMARY KEY,
    fingerprint TEXT,
    source TEXT,
    title TEXT,
    company TEXT,
    location TEXT,
    url TEXT,
    categories TEXT,
    first_seen TEXT,
    notified INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_fp ON jobs(fingerprint);
CREATE TABLE IF NOT EXISTS notices (
    key TEXT PRIMARY KEY,
    first_seen TEXT
);
"""


class Store:
    def __init__(self, path: str):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def is_empty(self) -> bool:
        return self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0

    def is_known(self, job: Job) -> bool:
        if self.db.execute("SELECT 1 FROM jobs WHERE key = ?", (job.key,)).fetchone():
            return True
        fp = job.fingerprint
        return bool(fp and self.db.execute("SELECT 1 FROM jobs WHERE fingerprint = ?", (fp,)).fetchone())

    def add(self, job: Job, notified: bool) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?)",
            (job.key, job.fingerprint or None, job.source, job.title, job.company, job.location,
             job.url, ",".join(job.categories), datetime.now(timezone.utc).isoformat(), int(notified)),
        )
        self.db.commit()

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    def is_notice_known(self, key: str) -> bool:
        return bool(self.db.execute("SELECT 1 FROM notices WHERE key = ?", (key,)).fetchone())

    def add_notice(self, key: str) -> None:
        self.db.execute("INSERT OR IGNORE INTO notices VALUES (?,?)",
                        (key, datetime.now(timezone.utc).isoformat()))
        self.db.commit()
