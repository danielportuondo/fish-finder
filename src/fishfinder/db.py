"""SQLite connection and schema initialization."""

import sqlite3
from pathlib import Path

from . import config


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes. Idempotent (schema uses IF NOT EXISTS)."""
    conn.executescript(config.SCHEMA_PATH.read_text())
    conn.commit()
