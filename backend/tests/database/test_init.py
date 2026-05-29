"""Tests for database.init — init_db and get_db."""

import sqlite3
from pathlib import Path

import pytest

from database.init import get_db, init_db


EXPECTED_TABLES = {
    "users_profile",
    "watchlist",
    "positions",
    "trades",
    "portfolio_snapshots",
    "chat_messages",
}

EXPECTED_WATCHLIST_TICKERS = {
    "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
    "NVDA", "META", "JPM", "V", "NFLX",
}


@pytest.fixture
def db_path(tmp_path: Path) -> str:
    return str(tmp_path / "test_finally.db")


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    return {r[0] for r in rows}


def test_db_file_created(db_path: str) -> None:
    init_db(db_path)
    assert Path(db_path).exists()


def test_db_created_in_nested_directory(tmp_path: Path) -> None:
    nested = str(tmp_path / "a" / "b" / "finally.db")
    init_db(nested)
    assert Path(nested).exists()


def test_all_tables_exist(db_path: str) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        assert EXPECTED_TABLES == _tables(conn)
    finally:
        conn.close()


def test_default_user_exists(db_path: str) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT id, cash_balance FROM users_profile WHERE id='default'"
        ).fetchone()
        assert row is not None
        assert row[0] == "default"
        assert row[1] == 10000.0
    finally:
        conn.close()


def test_default_watchlist_entries(db_path: str) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id='default'"
        ).fetchall()
        tickers = {r[0] for r in rows}
        assert tickers == EXPECTED_WATCHLIST_TICKERS
    finally:
        conn.close()


def test_init_db_is_idempotent(db_path: str) -> None:
    init_db(db_path)
    init_db(db_path)  # second call must not fail or duplicate data

    conn = sqlite3.connect(db_path)
    try:
        user_count = conn.execute("SELECT COUNT(*) FROM users_profile").fetchone()[0]
        watchlist_count = conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]
        assert user_count == 1
        assert watchlist_count == 10
    finally:
        conn.close()


def test_get_db_returns_row_factory(db_path: str) -> None:
    init_db(db_path)
    conn = get_db(db_path)
    try:
        assert conn.row_factory is sqlite3.Row
        row = conn.execute(
            "SELECT id, cash_balance FROM users_profile WHERE id='default'"
        ).fetchone()
        assert row is not None
        # sqlite3.Row supports column access by name
        assert row["id"] == "default"
        assert row["cash_balance"] == 10000.0
    finally:
        conn.close()
