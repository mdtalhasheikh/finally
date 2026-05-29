"""Database initialization and connection helpers."""

import sqlite3
from pathlib import Path


_SCHEMA_PATH = Path(__file__).parent / "schema.sql"
_SEED_PATH = Path(__file__).parent / "seed.sql"


def init_db(db_path: str) -> None:
    """Create the DB file, apply schema, and seed if tables are empty."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA_PATH.read_text())
        _seed_if_empty(conn)
        conn.commit()
    finally:
        conn.close()


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    """Run seed.sql only when users_profile has no rows."""
    row = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()
    if row[0] == 0:
        conn.executescript(_SEED_PATH.read_text())


def get_db(db_path: str) -> sqlite3.Connection:
    """Return a connection with row_factory set to sqlite3.Row."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn
