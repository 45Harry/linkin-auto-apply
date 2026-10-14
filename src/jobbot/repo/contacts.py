"""Data access for the contacts table.

Contacts only ever come from the source text (spec 0001, AC-9): a name, a profile
URL, and an email or phone only when they appear in the item. Nothing is guessed.
"""

from __future__ import annotations

import sqlite3


def _find(
    conn: sqlite3.Connection, job_id: int, name: str, linkedin_url: str | None
) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM contacts WHERE job_id = ? AND lower(name) = lower(?) "
        "AND COALESCE(linkedin_url, '') = COALESCE(?, '')",
        (job_id, name, linkedin_url),
    ).fetchone()


def ensure(
    conn: sqlite3.Connection,
    *,
    job_id: int,
    name: str,
    role: str,
    linkedin_url: str | None = None,
    email: str | None = None,
    phone: str | None = None,
) -> tuple[int, bool]:
    """Insert a contact if new, else fill any null detail. Returns `(id, created)`."""
    name = name.strip()
    if not name:
        raise ValueError("contact name is required")
    existing = _find(conn, job_id, name, linkedin_url)
    if existing is not None:
        conn.execute(
            "UPDATE contacts SET linkedin_url = COALESCE(linkedin_url, ?), "
            "email = COALESCE(email, ?), phone = COALESCE(phone, ?) WHERE id = ?",
            (linkedin_url, email, phone, existing["id"]),
        )
        return int(existing["id"]), False
    cursor = conn.execute(
        "INSERT INTO contacts (job_id, name, role, linkedin_url, email, phone) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (job_id, name, role, linkedin_url, email, phone),
    )
    return int(cursor.lastrowid), True


def list_for_job(conn: sqlite3.Connection, job_id: int) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM contacts WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
