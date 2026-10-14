"""Apply versioned SQL migrations from the migrations folder, once each.

Each migration runs inside one begin/commit so a failure leaves nothing half
applied, and its bookkeeping row is written in the same transaction.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

log = logging.getLogger("jobbot.migrate")

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _ensure_bookkeeping(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "name TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )


def applied_names(conn: sqlite3.Connection) -> set[str]:
    _ensure_bookkeeping(conn)
    rows = conn.execute("SELECT name FROM schema_migrations").fetchall()
    return {row["name"] for row in rows}


def migrate(conn: sqlite3.Connection, migrations_dir: Path = MIGRATIONS_DIR) -> list[str]:
    from .timeutil import now_iso

    _ensure_bookkeeping(conn)
    done = applied_names(conn)
    newly_applied: list[str] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in done:
            continue
        sql = path.read_text(encoding="utf-8")
        name_literal = path.name.replace("'", "''")
        applied_literal = now_iso().replace("'", "''")
        script = (
            "BEGIN;\n"
            f"{sql}\n"
            "INSERT INTO schema_migrations (name, applied_at) "
            f"VALUES ('{name_literal}', '{applied_literal}');\n"
            "COMMIT;"
        )
        conn.executescript(script)
        newly_applied.append(path.name)
        log.info("migration applied", extra={"migration": path.name})
    return newly_applied
