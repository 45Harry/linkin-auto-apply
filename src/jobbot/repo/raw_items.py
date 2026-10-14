"""Data access for the raw_items table.

One row per source item (an email, a post, a search result). `UNIQUE (source,
external_id)` makes every fetch safe to rerun (spec 0001 invariants).
"""

from __future__ import annotations

import sqlite3


def upsert(
    conn: sqlite3.Connection,
    *,
    source: str,
    external_id: str,
    content: str,
    fetched_at: str,
) -> tuple[int, bool]:
    """Insert a raw item if new, else return the existing one. Returns `(id, created)`."""
    existing = conn.execute(
        "SELECT id FROM raw_items WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()
    if existing is not None:
        return int(existing["id"]), False
    cursor = conn.execute(
        "INSERT INTO raw_items (source, external_id, content, fetched_at, parse_status) "
        "VALUES (?, ?, ?, ?, 'pending')",
        (source, external_id, content, fetched_at),
    )
    return int(cursor.lastrowid), True


def get(conn: sqlite3.Connection, raw_item_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM raw_items WHERE id = ?", (raw_item_id,)).fetchone()


def get_by_external(conn: sqlite3.Connection, source: str, external_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM raw_items WHERE source = ? AND external_id = ?",
        (source, external_id),
    ).fetchone()


def set_status(
    conn: sqlite3.Connection,
    raw_item_id: int,
    status: str,
    *,
    parsed_by: str | None = None,
    error: str | None = None,
) -> None:
    conn.execute(
        "UPDATE raw_items SET parse_status = ?, parsed_by = ?, error = ? WHERE id = ?",
        (status, parsed_by, error, raw_item_id),
    )


def list_pending(
    conn: sqlite3.Connection,
    *,
    source: str | None = None,
    min_fetched_at: str | None = None,
) -> list[sqlite3.Row]:
    clauses = ["parse_status = 'pending'"]
    params: list[object] = []
    if source is not None:
        clauses.append("source = ?")
        params.append(source)
    if min_fetched_at is not None:
        clauses.append("fetched_at >= ?")
        params.append(min_fetched_at)
    rows = conn.execute(
        f"SELECT * FROM raw_items WHERE {' AND '.join(clauses)} ORDER BY id", params
    ).fetchall()
    return list(rows)


def fail_too_old(conn: sqlite3.Connection, *, cutoff_iso: str) -> int:
    """Mark still pending items older than the cutoff as `failed` (AC-10)."""
    cursor = conn.execute(
        "UPDATE raw_items SET parse_status = 'failed', error = 'aged out pending' "
        "WHERE parse_status = 'pending' AND fetched_at < ?",
        (cutoff_iso,),
    )
    return cursor.rowcount


def counts_by_status(conn: sqlite3.Connection, source: str | None = None) -> dict[str, int]:
    if source is None:
        rows = conn.execute(
            "SELECT parse_status AS s, COUNT(*) AS n FROM raw_items GROUP BY parse_status"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT parse_status AS s, COUNT(*) AS n FROM raw_items WHERE source = ? "
            "GROUP BY parse_status",
            (source,),
        ).fetchall()
    return {row["s"]: int(row["n"]) for row in rows}
