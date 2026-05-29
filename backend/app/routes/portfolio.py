"""Portfolio endpoints: GET positions, POST trade, GET history."""

from __future__ import annotations

import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.config import config
from app.market import PriceCache
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_TICKER_RE = re.compile(r"^[A-Z]{1,8}$")


# --- Pydantic models ---

class TradeRequest(BaseModel):
    ticker: str
    quantity: float
    side: str
    idempotency_key: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper().strip()
        if not _TICKER_RE.match(v):
            raise ValueError("ticker must be 1-8 uppercase letters")
        return v

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be greater than 0")
        return v


# --- Helpers ---

def _error(code: str, message: str, details: dict | None = None, status: int = 422) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_position_dict(
    ticker: str,
    quantity: float,
    avg_cost: float,
    current_price: float,
    session_open: float | None = None,
) -> dict:
    unrealized_pnl = round((current_price - avg_cost) * quantity, 2)
    unrealized_pnl_pct = round((current_price - avg_cost) / avg_cost * 100, 4) if avg_cost else 0.0
    # session_open not yet tracked in PriceUpdate; fall back to current_price (daily_change = 0)
    s_open = session_open if session_open is not None else current_price
    daily_change_pct = round((current_price - s_open) / s_open * 100, 4) if s_open else 0.0
    return {
        "ticker": ticker,
        "quantity": quantity,
        "avg_cost": round(avg_cost, 4),
        "current_price": round(current_price, 2),
        "session_open": round(s_open, 2),
        "daily_change_pct": daily_change_pct,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_pct": unrealized_pnl_pct,
    }


# --- Endpoints ---

@router.get("/api/portfolio")
async def get_portfolio(request: Request) -> dict:
    """Return all open positions with live prices, cash balance, and totals."""
    cache: PriceCache = request.app.state.price_cache

    db = get_db(config.db_path)
    try:
        pos_rows = db.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = 'default' AND quantity > 0"
        ).fetchall()
        cash_row = db.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ).fetchone()
    finally:
        db.close()

    cash = cash_row["cash_balance"] if cash_row else 0.0

    positions = []
    total_market_value = 0.0
    total_unrealized_pnl = 0.0

    for row in pos_rows:
        ticker = row["ticker"]
        qty = row["quantity"]
        avg_cost = row["avg_cost"]
        current_price = cache.get_price(ticker) or avg_cost
        session_open = getattr(cache.get(ticker), "session_open", None)
        pos = _build_position_dict(ticker, qty, avg_cost, current_price, session_open)
        positions.append(pos)
        total_market_value += pos["market_value"]
        total_unrealized_pnl += pos["unrealized_pnl"]

    total_value = round(cash + total_market_value, 2)

    return {
        "positions": positions,
        "cash_balance": round(cash, 2),
        "total_value": total_value,
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
    }


@router.post("/api/portfolio/trade", status_code=201)
async def execute_trade(body: TradeRequest, request: Request) -> JSONResponse:
    """Buy or sell a position. Supports idempotency via idempotency_key."""
    cache: PriceCache = request.app.state.price_cache

    current_price = cache.get_price(body.ticker)
    if current_price is None:
        return _error("unknown_ticker", f"No price data for {body.ticker}")

    db = get_db(config.db_path)
    try:
        return _run_trade(db, body, current_price)
    finally:
        db.close()


def _run_trade(db: sqlite3.Connection, body: TradeRequest, current_price: float) -> JSONResponse:
    """Execute the trade within the provided DB connection."""
    trade_cost = round(body.quantity * current_price, 2)

    cash_row = db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = 'default'"
    ).fetchone()
    cash = cash_row["cash_balance"] if cash_row else 0.0

    pos_row = db.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
        (body.ticker,),
    ).fetchone()
    current_qty = pos_row["quantity"] if pos_row else 0.0
    current_avg_cost = pos_row["avg_cost"] if pos_row else 0.0

    # Validate funds / shares
    if body.side == "buy":
        if cash < trade_cost:
            return _error(
                "insufficient_cash",
                f"Need {trade_cost:.2f} but cash balance is {cash:.2f}",
                {"required": trade_cost, "available": cash},
            )
    else:
        if current_qty < body.quantity:
            return _error(
                "insufficient_shares",
                f"Need {body.quantity} shares of {body.ticker} but only have {current_qty}",
                {"required": body.quantity, "available": current_qty},
            )

    # Compute new state
    if body.side == "buy":
        new_cash = round(cash - trade_cost, 2)
        new_qty = round(current_qty + body.quantity, 8)
        new_avg_cost = round(
            (current_avg_cost * current_qty + current_price * body.quantity) / new_qty, 4
        )
    else:
        new_cash = round(cash + trade_cost, 2)
        new_qty = round(current_qty - body.quantity, 8)
        new_avg_cost = current_avg_cost

    trade_id = str(uuid.uuid4())
    now = _now_iso()

    try:
        db.execute(
            """INSERT INTO trades
               (id, user_id, ticker, side, quantity, price, executed_at,
                idempotency_key, cash_balance_after, position_qty_after, position_avg_cost_after)
               VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                trade_id, body.ticker, body.side, body.quantity, current_price, now,
                body.idempotency_key, new_cash, new_qty,
                new_avg_cost if new_qty > 0 else None,
            ),
        )
    except sqlite3.IntegrityError:
        return _replay_idempotent_trade(db, body.idempotency_key)

    db.execute(
        "UPDATE users_profile SET cash_balance = ? WHERE id = 'default'",
        (new_cash,),
    )

    if new_qty > 0:
        db.execute(
            """INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at)
               VALUES (?, 'default', ?, ?, ?, ?)
               ON CONFLICT (user_id, ticker) DO UPDATE SET
                   quantity = excluded.quantity,
                   avg_cost = excluded.avg_cost,
                   updated_at = excluded.updated_at""",
            (str(uuid.uuid4()), body.ticker, new_qty, new_avg_cost, now),
        )
    else:
        db.execute(
            "UPDATE positions SET quantity = 0, updated_at = ? WHERE user_id = 'default' AND ticker = ?",
            (now, body.ticker),
        )

    _insert_snapshot(db, new_cash, body.ticker, new_qty, new_avg_cost, current_price, now)
    db.commit()

    trade = {
        "id": trade_id,
        "ticker": body.ticker,
        "side": body.side,
        "quantity": body.quantity,
        "price": current_price,
        "executed_at": now,
        "idempotency_key": body.idempotency_key,
        "cash_balance_after": new_cash,
        "position_qty_after": new_qty,
        "position_avg_cost_after": new_avg_cost if new_qty > 0 else None,
    }
    position = (
        {"ticker": body.ticker, "quantity": new_qty, "avg_cost": new_avg_cost}
        if new_qty > 0
        else None
    )

    return JSONResponse(
        status_code=201,
        content={"trade": trade, "cash_balance": new_cash, "position": position},
    )


def _replay_idempotent_trade(db: sqlite3.Connection, idempotency_key: str) -> JSONResponse:
    """Return the original response for a duplicate idempotency_key."""
    row = db.execute(
        """SELECT id, ticker, side, quantity, price, executed_at, idempotency_key,
                  cash_balance_after, position_qty_after, position_avg_cost_after
           FROM trades WHERE user_id = 'default' AND idempotency_key = ?""",
        (idempotency_key,),
    ).fetchone()

    if not row:
        return _error("idempotency_error", "Could not find original trade for key", status=500)

    trade = dict(row)
    qty_after = trade["position_qty_after"]
    avg_cost_after = trade["position_avg_cost_after"]
    position = (
        {"ticker": trade["ticker"], "quantity": qty_after, "avg_cost": avg_cost_after}
        if qty_after and qty_after > 0
        else None
    )

    return JSONResponse(
        status_code=200,
        content={"trade": trade, "cash_balance": trade["cash_balance_after"], "position": position},
    )


def _insert_snapshot(
    db: sqlite3.Connection,
    cash: float,
    changed_ticker: str,
    new_qty: float,
    new_avg_cost: float,
    current_price: float,
    now: str,
) -> None:
    """Insert a portfolio snapshot. Uses current_price for the traded ticker."""
    rows = db.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = 'default' AND quantity > 0"
    ).fetchall()

    total = cash
    for row in rows:
        ticker = row["ticker"]
        qty = row["quantity"]
        price = current_price if ticker == changed_ticker else row["avg_cost"]
        total += qty * price

    db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, 'default', ?, ?)",
        (str(uuid.uuid4()), round(total, 2), now),
    )


@router.get("/api/portfolio/history")
async def get_portfolio_history(request: Request, limit: int = 500) -> list:
    """Return portfolio value snapshots, newest first. Max 2000."""
    limit = min(limit, 2000)
    db = get_db(config.db_path)
    try:
        rows = db.execute(
            "SELECT id, total_value, recorded_at FROM portfolio_snapshots "
            "WHERE user_id = 'default' ORDER BY recorded_at ASC LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        db.close()

    return [{"id": row["id"], "total_value": row["total_value"], "recorded_at": row["recorded_at"]} for row in rows]
