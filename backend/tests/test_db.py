"""Tests for database layer."""

from __future__ import annotations

import pytest
import aiosqlite

from app.db import (
    add_watchlist_ticker,
    get_chat_history,
    get_portfolio_history,
    get_positions,
    get_tracked_tickers,
    get_user,
    get_watchlist,
    init_db,
    insert_chat_message,
    insert_portfolio_snapshot,
    insert_trade,
    remove_watchlist_ticker,
    update_cash,
    upsert_position,
    watchlist_ticker_exists,
)


@pytest.fixture
async def db():
    """In-memory SQLite database, initialized with schema and seed data."""
    from pathlib import Path
    from app.db import now_iso

    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA journal_mode=WAL")

    schema_path = Path(__file__).parent.parent / "database" / "schema.sql"
    schema_sql = schema_path.read_text()
    await conn.executescript(schema_sql)
    await conn.commit()

    # Seed default user
    await conn.execute(
        "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        ("default", 10000.0, now_iso()),
    )
    await conn.commit()

    yield conn
    await conn.close()


class TestUserProfile:
    async def test_get_user(self, db):
        user = await get_user(db, "default")
        assert user is not None
        assert user["cash_balance"] == 10000.0

    async def test_update_cash(self, db):
        await update_cash(db, "default", 8500.0)
        await db.commit()
        user = await get_user(db, "default")
        assert pytest.approx(user["cash_balance"], abs=0.01) == 8500.0

    async def test_get_nonexistent_user(self, db):
        user = await get_user(db, "nobody")
        assert user is None


class TestWatchlist:
    async def test_add_ticker(self, db):
        await add_watchlist_ticker(db, "default", "AAPL")
        await db.commit()
        assert await watchlist_ticker_exists(db, "default", "AAPL")

    async def test_ticker_not_exists(self, db):
        assert not await watchlist_ticker_exists(db, "default", "ZZZZ")

    async def test_remove_ticker(self, db):
        await add_watchlist_ticker(db, "default", "AAPL")
        await db.commit()
        removed = await remove_watchlist_ticker(db, "default", "AAPL")
        await db.commit()
        assert removed
        assert not await watchlist_ticker_exists(db, "default", "AAPL")

    async def test_remove_nonexistent_returns_false(self, db):
        removed = await remove_watchlist_ticker(db, "default", "ZZZZ")
        assert not removed

    async def test_get_watchlist(self, db):
        await add_watchlist_ticker(db, "default", "AAPL")
        await add_watchlist_ticker(db, "default", "GOOGL")
        await db.commit()
        wl = await get_watchlist(db, "default")
        tickers = [w["ticker"] for w in wl]
        assert "AAPL" in tickers
        assert "GOOGL" in tickers


class TestPositions:
    async def test_upsert_new_position(self, db):
        await upsert_position(db, "default", "AAPL", 10.0, 190.0)
        await db.commit()
        positions = await get_positions(db, "default")
        assert len(positions) == 1
        assert positions[0]["ticker"] == "AAPL"
        assert pytest.approx(positions[0]["quantity"], abs=0.001) == 10.0

    async def test_upsert_updates_existing(self, db):
        await upsert_position(db, "default", "AAPL", 10.0, 190.0)
        await upsert_position(db, "default", "AAPL", 20.0, 185.0)
        await db.commit()
        positions = await get_positions(db, "default")
        assert len(positions) == 1
        assert pytest.approx(positions[0]["quantity"], abs=0.001) == 20.0


class TestTrades:
    async def test_insert_trade(self, db):
        trade = await insert_trade(
            db,
            user_id="default",
            ticker="AAPL",
            side="buy",
            quantity=10.0,
            price=190.0,
            cash_balance_after=8100.0,
            position_qty_after=10.0,
            position_avg_cost_after=190.0,
        )
        await db.commit()
        assert trade["ticker"] == "AAPL"
        assert trade["side"] == "buy"
        assert trade["id"] is not None

    async def test_idempotency_key_uniqueness(self, db):
        await insert_trade(
            db, "default", "AAPL", "buy", 10.0, 190.0, 8100.0, 10.0, 190.0, "key-1"
        )
        await db.commit()
        with pytest.raises(Exception):
            await insert_trade(
                db, "default", "AAPL", "buy", 5.0, 190.0, 7150.0, 15.0, 190.0, "key-1"
            )
            await db.commit()


class TestPortfolioSnapshots:
    async def test_insert_and_get(self, db):
        await insert_portfolio_snapshot(db, "default", 10500.0)
        await insert_portfolio_snapshot(db, "default", 10200.0)
        await db.commit()
        history = await get_portfolio_history(db, "default", limit=100)
        assert len(history) == 2
        # Oldest first
        assert pytest.approx(history[0]["total_value"], abs=0.01) == 10500.0
        assert pytest.approx(history[1]["total_value"], abs=0.01) == 10200.0

    async def test_limit(self, db):
        for v in range(10):
            await insert_portfolio_snapshot(db, "default", float(10000 + v))
        await db.commit()
        history = await get_portfolio_history(db, "default", limit=5)
        assert len(history) == 5


class TestChatMessages:
    async def test_insert_and_get_history(self, db):
        await insert_chat_message(db, "default", "user", "Hello!")
        await insert_chat_message(db, "default", "assistant", "Hi there!", actions={"trades": []})
        await db.commit()
        history = await get_chat_history(db, "default", limit=10)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
        assert history[1]["actions"] is not None

    async def test_history_limit(self, db):
        for i in range(5):
            await insert_chat_message(db, "default", "user", f"Message {i}")
        await db.commit()
        history = await get_chat_history(db, "default", limit=3)
        assert len(history) == 3


class TestTrackedTickers:
    async def test_union_of_watchlist_and_positions(self, db):
        await add_watchlist_ticker(db, "default", "AAPL")
        await add_watchlist_ticker(db, "default", "GOOGL")
        await upsert_position(db, "default", "TSLA", 5.0, 250.0)
        await db.commit()
        tickers = await get_tracked_tickers(db, "default")
        assert set(tickers) == {"AAPL", "GOOGL", "TSLA"}

    async def test_no_duplicates(self, db):
        await add_watchlist_ticker(db, "default", "AAPL")
        await upsert_position(db, "default", "AAPL", 10.0, 190.0)
        await db.commit()
        tickers = await get_tracked_tickers(db, "default")
        assert tickers.count("AAPL") == 1
