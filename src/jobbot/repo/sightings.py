"""Data access for the sightings table. A sighting is one source seeing one job."""

from __future__ import annotations

import sqlite3


def ensure(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    source: str,
    source_ref: str,
    seen_at: str,
    raw_item_id: int | None = None,
) -> bool:
    """Insert a sighting if new. Returns True when a row was actually created."""
    cursor = conn.execute(
        "INSERT OR IGNORE INTO sightings (job_id, source, source_ref, raw_item_id, seen_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (job_id, source, source_ref, raw_item_id, seen_at),
    )
    return cursor.rowcount == 1


def list_for_job(conn: sqlite3.Connection, job_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM sightings WHERE job_id = ? ORDER BY id", (job_id,)
    ).fetchall()
