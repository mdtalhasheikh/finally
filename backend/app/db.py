"""Database layer — all SQLite queries for FinAlly.

Uses aiosqlite for async access. All functions accept an open connection so
callers control transaction scope (especially important for trade execution).
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from .config import config, get_db_path

_SCHEMA_PATH = Path(__file__).parent.parent / "database" / "schema.sql"


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@asynccontextmanager
async def open_db() -> AsyncIterator[aiosqlite.Connection]:
    """Open a database connection as an async context manager.

    Usage:
        async with open_db() as db:
            ...
    """
    db_path = get_db_path()
    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


async def init_db(db: aiosqlite.Connection) -> None:
    """Create tables and seed default data if the DB is empty."""
    schema_sql = _SCHEMA_PATH.read_text()
    await db.executescript(schema_sql)
    await db.commit()

    # Seed default user if not present
    async with db.execute(
        "SELECT id FROM users_profile WHERE id = ?", ("default",)
    ) as cur:
        row = await cur.fetchone()

    if row is None:
        await db.execute(
            "INSERT INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
            ("default", config.STARTING_CASH, now_iso()),
        )
        for ticker in config.DEFAULT_TICKERS:
            await db.execute(
                "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "default", ticker, now_iso()),
            )
        await db.commit()


# ---------------------------------------------------------------------------
# User / portfolio
# ---------------------------------------------------------------------------

async def get_user(db: aiosqlite.Connection, user_id: str = "default") -> dict | None:
    async with db.execute(
        "SELECT id, cash_balance FROM users_profile WHERE id = ?", (user_id,)
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def update_cash(
    db: aiosqlite.Connection, user_id: str, cash_balance: float
) -> None:
    await db.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = ?",
        (cash_balance, user_id),
    )


# ---------------------------------------------------------------------------
# Positions
# ---------------------------------------------------------------------------

async def get_positions(
    db: aiosqlite.Connection, user_id: str = "default"
) -> list[dict]:
    async with db.execute(
        "SELECT id, ticker, quantity, avg_cost, updated_at FROM positions WHERE user_id = ? AND quantity > 0",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_position(
    db: aiosqlite.Connection, user_id: str, ticker: str
) -> dict | None:
    async with db.execute(
        "SELECT id, ticker, quantity, avg_cost, updated_at FROM positions WHERE user_id = ? AND ticker = ?",
        (user_id, ticker),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_position(
    db: aiosqlite.Connection,
    user_id: str,
    ticker: str,
    quantity: float,
    avg_cost: float,
) -> None:
    ts = now_iso()
    await db.execute(
        """
        INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (user_id, ticker) DO UPDATE SET
            quantity = excluded.quantity,
            avg_cost = excluded.avg_cost,
            updated_at = excluded.updated_at
        """,
        (str(uuid.uuid4()), user_id, ticker, quantity, avg_cost, ts),
    )


async def delete_position(
    db: aiosqlite.Connection, user_id: str, ticker: str
) -> None:
    await db.execute(
        "DELETE FROM positions WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    )


# ---------------------------------------------------------------------------
# Trades
# ---------------------------------------------------------------------------

async def get_trade_by_idempotency_key(
    db: aiosqlite.Connection, user_id: str, idempotency_key: str
) -> dict | None:
    async with db.execute(
        """SELECT id, ticker, side, quantity, price, executed_at,
                  idempotency_key, cash_balance_after,
                  position_qty_after, position_avg_cost_after
           FROM trades
           WHERE user_id = ? AND idempotency_key = ?""",
        (user_id, idempotency_key),
    ) as cur:
        row = await cur.fetchone()
    return dict(row) if row else None


async def insert_trade(
    db: aiosqlite.Connection,
    user_id: str,
    ticker: str,
    side: str,
    quantity: float,
    price: float,
    cash_balance_after: float,
    position_qty_after: float,
    position_avg_cost_after: float | None,
    idempotency_key: str | None = None,
) -> dict:
    trade_id = str(uuid.uuid4())
    ts = now_iso()
    await db.execute(
        """
        INSERT INTO trades
            (id, user_id, ticker, side, quantity, price, executed_at,
             idempotency_key, cash_balance_after, position_qty_after, position_avg_cost_after)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade_id, user_id, ticker, side, quantity, price, ts,
            idempotency_key, cash_balance_after, position_qty_after, position_avg_cost_after,
        ),
    )
    return {
        "id": trade_id,
        "ticker": ticker,
        "side": side,
        "quantity": quantity,
        "price": price,
        "executed_at": ts,
    }


# ---------------------------------------------------------------------------
# Portfolio snapshots
# ---------------------------------------------------------------------------

async def insert_portfolio_snapshot(
    db: aiosqlite.Connection, user_id: str, total_value: float
) -> None:
    await db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
        (str(uuid.uuid4()), user_id, total_value, now_iso()),
    )


async def get_portfolio_history(
    db: aiosqlite.Connection,
    user_id: str = "default",
    limit: int = 500,
) -> list[dict]:
    limit = min(limit, 2000)
    async with db.execute(
        """
        SELECT total_value, recorded_at
        FROM portfolio_snapshots
        WHERE user_id = ?
        ORDER BY recorded_at ASC
        LIMIT ?
        """,
        (user_id, limit),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Watchlist
# ---------------------------------------------------------------------------

async def get_watchlist(
    db: aiosqlite.Connection, user_id: str = "default"
) -> list[dict]:
    async with db.execute(
        "SELECT id, ticker, added_at FROM watchlist WHERE user_id = ? ORDER BY added_at ASC",
        (user_id,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def add_watchlist_ticker(
    db: aiosqlite.Connection, user_id: str, ticker: str
) -> dict:
    entry_id = str(uuid.uuid4())
    ts = now_iso()
    await db.execute(
        "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
        (entry_id, user_id, ticker, ts),
    )
    return {"id": entry_id, "ticker": ticker, "added_at": ts}


async def remove_watchlist_ticker(
    db: aiosqlite.Connection, user_id: str, ticker: str
) -> bool:
    async with db.execute(
        "DELETE FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    ) as cur:
        return cur.rowcount > 0


async def watchlist_ticker_exists(
    db: aiosqlite.Connection, user_id: str, ticker: str
) -> bool:
    async with db.execute(
        "SELECT 1 FROM watchlist WHERE user_id = ? AND ticker = ?", (user_id, ticker)
    ) as cur:
        row = await cur.fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Tracked tickers (watchlist ∪ open positions)
# ---------------------------------------------------------------------------

async def get_tracked_tickers(
    db: aiosqlite.Connection, user_id: str = "default"
) -> list[str]:
    """Return union of watchlist tickers and tickers with open positions."""
    async with db.execute(
        "SELECT DISTINCT ticker FROM watchlist WHERE user_id = ?", (user_id,)
    ) as cur:
        wl_rows = await cur.fetchall()

    async with db.execute(
        "SELECT DISTINCT ticker FROM positions WHERE user_id = ? AND quantity > 0",
        (user_id,),
    ) as cur:
        pos_rows = await cur.fetchall()

    return list({r["ticker"] for r in wl_rows} | {r["ticker"] for r in pos_rows})


# ---------------------------------------------------------------------------
# Chat messages
# ---------------------------------------------------------------------------

async def insert_chat_message(
    db: aiosqlite.Connection,
    user_id: str,
    role: str,
    content: str,
    actions: Any = None,
) -> dict:
    msg_id = str(uuid.uuid4())
    ts = now_iso()
    actions_json = json.dumps(actions) if actions is not None else None
    await db.execute(
        "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (msg_id, user_id, role, content, actions_json, ts),
    )
    return {"id": msg_id, "role": role, "content": content, "actions": actions, "created_at": ts}


async def get_chat_history(
    db: aiosqlite.Connection,
    user_id: str = "default",
    limit: int | None = None,
) -> list[dict]:
    n = limit if limit is not None else config.LLM_MAX_HISTORY_MESSAGES
    async with db.execute(
        """
        SELECT id, role, content, actions, created_at
        FROM chat_messages
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (user_id, n),
    ) as cur:
        rows = await cur.fetchall()

    result = []
    for r in reversed(rows):  # oldest-first
        d = dict(r)
        if d["actions"]:
            try:
                d["actions"] = json.loads(d["actions"])
            except (json.JSONDecodeError, TypeError):
                d["actions"] = None
        result.append(d)
    return result
