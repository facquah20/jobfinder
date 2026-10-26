"""SQLite persistence with dedupe by canonical URL and dedupe hash."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from job_finder.models import JobPosting

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_url TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    payload TEXT NOT NULL,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_canonical ON jobs(canonical_url);
CREATE TABLE IF NOT EXISTS run_stats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finished_at TEXT NOT NULL,
    payload TEXT NOT NULL
);
"""


class JobRepository:
    def __init__(self, path: str) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def upsert_many(self, jobs: list[JobPosting]) -> tuple[int, int]:
        """Return (inserted, updated)."""
        inserted = updated = 0
        for job in jobs:
            payload = job.model_dump_json()
            key = job.dedupe_key()
            cur = self.conn.execute(
                "SELECT id FROM jobs WHERE dedupe_key = ?", (key,),
            ).fetchone()
            if cur:
                self.conn.execute(
                    "UPDATE jobs SET payload=?, last_seen=? WHERE id=?",
                    (payload, job.discovered_at.isoformat(), cur[0]),
                )
                updated += 1
            else:
                self.conn.execute(
                    "INSERT INTO jobs(canonical_url, dedupe_key, payload,"
                    " first_seen, last_seen) VALUES (?,?,?,?,?)",
                    (job.canonical_url, key, payload,
                     job.discovered_at.isoformat(), job.discovered_at.isoformat()),
                )
                inserted += 1
        self.conn.commit()
        return inserted, updated

    def all(self) -> list[JobPosting]:
        rows = self.conn.execute("SELECT payload FROM jobs").fetchall()
        return [JobPosting.model_validate_json(r[0]) for r in rows]

    def record_stats(self, payload: dict) -> None:
        from datetime import datetime, timezone
        self.conn.execute(
            "INSERT INTO run_stats(finished_at, payload) VALUES (?, ?)",
            (datetime.now(timezone.utc).isoformat(), json.dumps(payload)),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()