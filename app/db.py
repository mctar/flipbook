"""SQLite database layer.

One file, three tables, no ORM. Using sqlite3 directly keeps dependencies
minimal and the schema obvious to anyone reading.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

# Database lives in the user's home directory under .tools-crm/.
# Override with TOOLS_CRM_DB env var (used in tests and the demo).
DEFAULT_DB_DIR = Path.home() / ".tools-crm"
DB_PATH = Path(os.environ.get("TOOLS_CRM_DB", str(DEFAULT_DB_DIR / "crm.db")))


SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    company     TEXT,
    role        TEXT,
    phone       TEXT,
    email       TEXT,
    tags        TEXT DEFAULT '',
    notes       TEXT DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_contacts_name    ON contacts(name);
CREATE INDEX IF NOT EXISTS idx_contacts_company ON contacts(company);

CREATE TABLE IF NOT EXISTS interactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id      INTEGER NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    occurred_at     TEXT NOT NULL,
    channel         TEXT NOT NULL,
    summary         TEXT NOT NULL,
    follow_up_date  TEXT,
    completed_at    TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_interactions_contact   ON interactions(contact_id);
CREATE INDEX IF NOT EXISTS idx_interactions_followup  ON interactions(follow_up_date);
CREATE INDEX IF NOT EXISTS idx_interactions_occurred  ON interactions(occurred_at);

CREATE TABLE IF NOT EXISTS import_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    row_hash    TEXT NOT NULL UNIQUE,
    contact_id  INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
    source      TEXT,
    imported_at TEXT NOT NULL
);
"""


def now_iso() -> str:
    """UTC ISO-8601 timestamp without microseconds."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db(db_path: Path = DB_PATH) -> None:
    """Create the database file and schema if missing. Idempotent.

    Also runs in-place migrations for columns added after v1 ship — e.g.
    `interactions.completed_at` was added when follow-up completion shipped.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(interactions)").fetchall()}
    if "completed_at" not in cols:
        conn.execute("ALTER TABLE interactions ADD COLUMN completed_at TEXT")


@contextmanager
def get_conn(db_path: Path = DB_PATH) -> Iterator[sqlite3.Connection]:
    """Yield a connection with row factory set and foreign keys enforced."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
