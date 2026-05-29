"""Chat endpoints: POST /api/chat, GET /api/chat/history."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import config
from app.llm.models import LLMResponse, TradeAction, WatchlistAction
from app.market import PriceCache
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class ChatRequest(BaseModel):
    message: str


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- Portfolio context loader ---

def _load_portfolio_context(db: sqlite3.Connection, cache: PriceCache) -> dict:
    """Build a portfolio context dict from DB + price cache."""
    cash_row = db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = 'default'"
    ).fetchone()
    cash = cash_row["cash_balance"] if cash_row else 0.0

    pos_rows = db.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = 'default' AND quantity > 0"
    ).fetchall()

    positions = []
    total_market_value = 0.0
    for row in pos_rows:
        ticker = row["ticker"]
        qty = row["quantity"]
        avg_cost = row["avg_cost"]
        current_price = cache.get_price(ticker) or avg_cost
        market_value = qty * current_price
        total_market_value += market_value
        positions.append({
            "ticker": ticker,
            "quantity": qty,
            "avg_cost": avg_cost,
            "current_price": current_price,
        })

    watchlist_rows = db.execute(
        "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
    ).fetchall()
    watchlist = [row["ticker"] for row in watchlist_rows]

    return {
        "cash": round(cash, 2),
        "total_value": round(cash + total_market_value, 2),
        "positions": positions,
        "watchlist": watchlist,
    }


# --- Ticker pre-validation ---

async def _validate_tickers(
    tickers: list[str],
    cache: PriceCache,
    market_source: Any,
) -> tuple[set[str], set[str]]:
    """
    Returns (known_tickers, new_tickers_to_subscribe).
    A ticker is 'known' if it is already in the price cache.
    Unknown tickers are probed via market_source; confirmed ones are in new_tickers.
    """
    known: set[str] = set()
    unknown: set[str] = set()

    for ticker in tickers:
        if cache.get_price(ticker) is not None:
            known.add(ticker)
        else:
            unknown.add(ticker)

    new_confirmed: set[str] = set()
    for ticker in unknown:
        if market_source is not None:
            try:
                await market_source.add_ticker(ticker)
                # If add_ticker doesn't raise, treat as valid
                new_confirmed.add(ticker)
            except Exception:
                logger.warning("Ticker not recognized by market source: %s", ticker)
        # If no market_source, ticker stays unresolved (failed)

    return known | new_confirmed, new_confirmed


# --- Trade execution (within a DB transaction) ---

def _execute_trade(
    db: sqlite3.Connection,
    trade: TradeAction,
    trade_index: int,
    chat_message_id: str,
    cache: PriceCache,
    valid_tickers: set[str],
) -> dict:
    """Execute a single trade. Returns a result dict with status/error."""
    ticker = trade.ticker.upper().strip()
    idempotency_key = f"{chat_message_id}:{trade_index}"

    if ticker not in valid_tickers:
        return {
            "ticker": ticker,
            "side": trade.side,
            "quantity": trade.quantity,
            "price": None,
            "status": "failed",
            "error": "unknown_ticker",
        }

    current_price = cache.get_price(ticker)
    if current_price is None:
        return {
            "ticker": ticker,
            "side": trade.side,
            "quantity": trade.quantity,
            "price": None,
            "status": "failed",
            "error": "unknown_ticker",
        }

    trade_cost = round(trade.quantity * current_price, 2)

    cash_row = db.execute(
        "SELECT cash_balance FROM users_profile WHERE id = 'default'"
    ).fetchone()
    cash = cash_row["cash_balance"] if cash_row else 0.0

    pos_row = db.execute(
        "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
        (ticker,),
    ).fetchone()
    current_qty = pos_row["quantity"] if pos_row else 0.0
    current_avg_cost = pos_row["avg_cost"] if pos_row else 0.0

    if trade.side == "buy":
        if cash < trade_cost:
            return {
                "ticker": ticker,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": current_price,
                "status": "failed",
                "error": "insufficient_cash",
            }
        new_cash = round(cash - trade_cost, 2)
        new_qty = round(current_qty + trade.quantity, 8)
        new_avg_cost = round(
            (current_avg_cost * current_qty + current_price * trade.quantity) / new_qty, 4
        )
    else:  # sell
        if current_qty < trade.quantity:
            return {
                "ticker": ticker,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": current_price,
                "status": "failed",
                "error": "insufficient_shares",
            }
        new_cash = round(cash + trade_cost, 2)
        new_qty = round(current_qty - trade.quantity, 8)
        new_avg_cost = current_avg_cost

    now = _now_iso()
    trade_id = str(uuid.uuid4())

    db.execute(
        """INSERT INTO trades
           (id, user_id, ticker, side, quantity, price, executed_at,
            idempotency_key, cash_balance_after, position_qty_after, position_avg_cost_after)
           VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            trade_id, ticker, trade.side, trade.quantity, current_price, now,
            idempotency_key, new_cash, new_qty,
            new_avg_cost if new_qty > 0 else None,
        ),
    )

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
            (str(uuid.uuid4()), ticker, new_qty, new_avg_cost, now),
        )
    else:
        db.execute(
            "UPDATE positions SET quantity = 0, updated_at = ? WHERE user_id = 'default' AND ticker = ?",
            (now, ticker),
        )

    # Portfolio snapshot after trade
    all_pos = db.execute(
        "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = 'default' AND quantity > 0"
    ).fetchall()
    total = new_cash
    for row in all_pos:
        t = row["ticker"]
        price = current_price if t == ticker else row["avg_cost"]
        total += row["quantity"] * price
    db.execute(
        "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, 'default', ?, ?)",
        (str(uuid.uuid4()), round(total, 2), now),
    )

    return {
        "ticker": ticker,
        "side": trade.side,
        "quantity": trade.quantity,
        "price": current_price,
        "status": "executed",
        "error": None,
    }


# --- Watchlist change execution ---

def _execute_watchlist_change(db: sqlite3.Connection, change: WatchlistAction) -> dict:
    """Apply a watchlist add/remove. Ignores duplicate adds and missing removes."""
    ticker = change.ticker.upper().strip()
    action = change.action

    if action == "add":
        db.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), ticker, _now_iso()),
        )
    elif action == "remove":
        db.execute(
            "DELETE FROM watchlist WHERE user_id = 'default' AND ticker = ?",
            (ticker,),
        )

    return {"ticker": ticker, "action": action, "status": "executed"}


# --- POST /api/chat ---

@router.post("/api/chat")
async def chat(body: ChatRequest, request: Request) -> JSONResponse:
    """Process a chat message: call LLM, execute actions, persist messages."""
    cache: PriceCache = request.app.state.price_cache
    market_source = request.app.state.market_source
    llm_service = request.app.state.llm_service

    db = get_db(config.db_path)
    try:
        # 1. Load portfolio context
        portfolio_context = _load_portfolio_context(db, cache)

        # 2. Load chat history (oldest first, capped at max_history)
        history_rows = db.execute(
            """SELECT role, content FROM chat_messages
               WHERE user_id = 'default'
               ORDER BY created_at DESC LIMIT ?""",
            (config.llm_max_history_messages,),
        ).fetchall()
        # fetchall gives newest-first; reverse to oldest-first for LLM
        history = [{"role": r["role"], "content": r["content"]} for r in reversed(history_rows)]
    finally:
        db.close()

    # 3. Call LLM
    try:
        llm_response: LLMResponse = await llm_service.chat(
            body.message, portfolio_context, history
        )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        return JSONResponse(
            status_code=502,
            content={"error": "LLM unavailable", "detail": str(exc)},
        )

    # 4. Pre-validate tickers (Massive mode: probe unknown ones)
    all_tickers = {t.ticker.upper().strip() for t in llm_response.trades} | {
        w.ticker.upper().strip() for w in llm_response.watchlist_changes if w.action == "add"
    }
    valid_tickers, new_tickers = await _validate_tickers(
        list(all_tickers), cache, market_source
    )

    # 5. DB transaction: insert messages + execute actions
    chat_message_id = str(uuid.uuid4())
    trade_results: list[dict] = []
    watchlist_results: list[dict] = []

    db = get_db(config.db_path)
    try:
        # 5a. Insert user message
        db.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, 'default', 'user', ?, NULL, ?)",
            (str(uuid.uuid4()), body.message, _now_iso()),
        )

        # 5b. Execute trades (partial failure is ok — continue on each)
        for idx, trade in enumerate(llm_response.trades):
            result = _execute_trade(
                db, trade, idx, chat_message_id, cache, valid_tickers
            )
            trade_results.append(result)

        # 5c. Execute watchlist changes
        for change in llm_response.watchlist_changes:
            result = _execute_watchlist_change(db, change)
            watchlist_results.append(result)

        # 5d. Insert assistant message with actions JSON
        actions_payload = {
            "trades": trade_results,
            "watchlist_changes": watchlist_results,
        }
        db.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, 'default', 'assistant', ?, ?, ?)",
            (
                chat_message_id,
                llm_response.message,
                json.dumps(actions_payload),
                _now_iso(),
            ),
        )

        db.commit()
    except Exception as exc:
        logger.error("DB transaction failed: %s", exc)
        db.rollback()
        raise
    finally:
        db.close()

    # 6. Post-commit: subscribe new valid tickers to market source
    if new_tickers and market_source is not None:
        for ticker in new_tickers:
            try:
                await market_source.add_ticker(ticker)
            except Exception:
                logger.warning("Failed to subscribe new ticker post-commit: %s", ticker)

    return JSONResponse(
        status_code=200,
        content={
            "message": llm_response.message,
            "trades": trade_results,
            "watchlist_changes": watchlist_results,
        },
    )


# --- GET /api/chat/history ---

@router.get("/api/chat/history")
async def chat_history() -> list:
    """Return the last N chat messages, oldest first."""
    db = get_db(config.db_path)
    try:
        rows = db.execute(
            """SELECT id, role, content, actions, created_at
               FROM chat_messages
               WHERE user_id = 'default'
               ORDER BY created_at ASC
               LIMIT ?""",
            (config.llm_max_history_messages,),
        ).fetchall()
    finally:
        db.close()

    result = []
    for row in rows:
        actions_raw = row["actions"]
        actions = json.loads(actions_raw) if actions_raw else None
        result.append({
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "actions": actions,
            "created_at": row["created_at"],
        })
    return result
