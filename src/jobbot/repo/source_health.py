"""Data access for the source_health table."""

from __future__ import annotations

import sqlite3

_COLUMNS = (
    "source",
    "status",
    "last_success_at",
    "last_error_at",
    "last_error",
    "alerted_at",
    "consecutive_failures",
    "quota_used",
    "quota_period",
)


def get(conn: sqlite3.Connection, source: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM source_health WHERE source = ?", (source,)).fetchone()


def upsert(conn: sqlite3.Connection, source: str, **fields: object) -> None:
    data = {col: value for col, value in fields.items() if col in _COLUMNS and col != "source"}
    existing = get(conn, source)
    if existing is None:
        data.setdefault("status", "ok")
        columns = ["source", *data.keys()]
        placeholders = ", ".join("?" for _ in columns)
        conn.execute(
            f"INSERT INTO source_health ({', '.join(columns)}) VALUES ({placeholders})",
            [source, *data.values()],
        )
        return
    if not data:
        return
    assignments = ", ".join(f"{col} = ?" for col in data)
    conn.execute(
        f"UPDATE source_health SET {assignments} WHERE source = ?",
        [*data.values(), source],
    )
