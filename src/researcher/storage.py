"""SQLite research history. One row per job; the job is stored as validated JSON."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from .models import Job, JobSummary


class Store:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
            "data TEXT NOT NULL)"
        )
        self._db.commit()

    def save(self, job: Job) -> None:
        with self._lock:
            self._db.execute(
                "INSERT INTO jobs (id, created_at, data) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET data = excluded.data",
                (job.id, job.created_at.isoformat(), job.model_dump_json()),
            )
            self._db.commit()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            row = self._db.execute("SELECT data FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return Job.model_validate_json(row[0]) if row else None

    def list(self) -> list[Job]:
        with self._lock:
            rows = self._db.execute("SELECT data FROM jobs ORDER BY created_at DESC").fetchall()
        return [Job.model_validate_json(r[0]) for r in rows]

    def delete(self, job_id: str) -> bool:
        with self._lock:
            cur = self._db.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
            self._db.commit()
        return cur.rowcount > 0

    def close(self) -> None:
        with self._lock:
            self._db.close()


def summarize(job: Job) -> JobSummary:
    return JobSummary(
        id=job.id,
        question=job.question,
        status=job.status,
        mode=job.mode,
        created_at=job.created_at,
        updated_at=job.updated_at,
        source_count=len(job.sources),
        claim_count=len(job.claims),
        has_report=job.report is not None,
    )
