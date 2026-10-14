"""Data access for the companies table."""

from __future__ import annotations

import sqlite3

from ..normalize import normalize_company_name
from ..timeutil import now_iso


def get(conn: sqlite3.Connection, company_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM companies WHERE id = ?", (company_id,)).fetchone()


def get_by_ats(conn: sqlite3.Connection, ats_type: str, ats_token: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM companies WHERE ats_type = ? AND ats_token = ?",
        (ats_type, ats_token),
    ).fetchone()


def find_by_name(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    rows = conn.execute("SELECT * FROM companies").fetchall()
    target = normalize_company_name(name)
    for row in rows:
        if normalize_company_name(row["name"]) == target:
            return row
    return None


def boards_to_poll(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM companies WHERE ats_type != 'none' AND muted = 0 ORDER BY id"
    ).fetchall()


def add(
    conn: sqlite3.Connection,
    *,
    name: str,
    ats_type: str = "none",
    ats_token: str | None = None,
    origin: str = "manual",
    website: str | None = None,
) -> int:
    cursor = conn.execute(
        "INSERT INTO companies (name, website, ats_type, ats_token, origin, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (name, website, ats_type, ats_token, origin, now_iso()),
    )
    return int(cursor.lastrowid)


def set_ats_type(conn: sqlite3.Connection, company_id: int, ats_type: str) -> None:
    conn.execute(
        "UPDATE companies SET ats_type = ? WHERE id = ?",
        (ats_type, company_id),
    )
