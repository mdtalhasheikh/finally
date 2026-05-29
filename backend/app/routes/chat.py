"""Chat API endpoints.

POST /api/chat         - Send a message, receive AI response + executed actions
GET  /api/chat/history - Recent chat messages (for page reload replay)
"""

from __future__ import annotations

import json
import logging
import re
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from ..config import config, is_llm_mock
from ..db import (
    add_watchlist_ticker,
    delete_position,
    get_chat_history,
    get_position,
    get_positions,
    get_user,
    get_watchlist,
    insert_portfolio_snapshot,
    insert_trade,
    open_db,
    remove_watchlist_ticker,
    update_cash,
    upsert_position,
    watchlist_ticker_exists,
)
from ..llm import ChatResponse, call_llm, mock_llm_response
from ..llm.client import TradeAction
from ..market import MarketDataSource, PriceCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

TICKER_RE = re.compile(r"^[A-Z]{1,8}$")


def _error(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


class ChatRequest(BaseModel):
    message: str


@router.get("/history")
async def get_history() -> list[dict]:
    async with open_db() as db:
        return await get_chat_history(db, "default", config.LLM_MAX_HISTORY_MESSAGES)


@router.post("")
async def send_message(body: ChatRequest, request: Request) -> dict:
    user_message = body.message.strip()
    if not user_message:
        raise HTTPException(422, detail=_error("invalid_input", "Message cannot be empty"))

    price_cache: PriceCache = request.app.state.price_cache
    market_source: MarketDataSource = request.app.state.market_source

    # Load context for LLM
    async with open_db() as db:
        user = await get_user(db, "default")
        if not user:
            raise HTTPException(500, detail=_error("internal", "User not found"))
        positions = await get_positions(db, "default")
        history = await get_chat_history(db, "default", config.LLM_MAX_HISTORY_MESSAGES)
        watchlist_rows = await get_watchlist(db, "default")

    from ..routes.portfolio import _build_portfolio
    from ..routes.watchlist import _enrich_with_prices

    watchlist_enriched = _enrich_with_prices(watchlist_rows, price_cache)
    portfolio = _build_portfolio(positions, user["cash_balance"], price_cache)

    # Call LLM (or mock)
    try:
        if is_llm_mock():
            llm_response: ChatResponse = mock_llm_response(user_message)
        else:
            llm_response = await call_llm(
                user_message=user_message,
                history=history,
                portfolio=portfolio,
                watchlist=watchlist_enriched,
            )
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        raise HTTPException(502, detail=_error("llm_error", "AI assistant is temporarily unavailable"))

    # Determine if we're in Massive mode for ticker validation
    from ..market.massive_client import MassiveDataSource
    from ..routes.watchlist import _validate_massive_ticker

    massive_mode = isinstance(market_source, MassiveDataSource)

    trade_actions = list(llm_response.trades)
    wl_actions = list(llm_response.watchlist_changes)
    failed_actions: list[dict] = []

    # Phase 1 (Massive mode only): validate unknown tickers before any DB writes
    if massive_mode:
        async with open_db() as db:
            validated_trades: list[TradeAction] = []
            for trade in trade_actions:
                if not TICKER_RE.match(trade.ticker):
                    failed_actions.append(
                        {"type": "trade", "ticker": trade.ticker, "error": "invalid_symbol"}
                    )
                    continue
                on_watchlist = await watchlist_ticker_exists(db, "default", trade.ticker)
                in_cache = price_cache.get_price(trade.ticker) is not None
                if not on_watchlist and not in_cache:
                    valid = await _validate_massive_ticker(market_source, trade.ticker)
                    if not valid:
                        failed_actions.append(
                            {"type": "trade", "ticker": trade.ticker, "error": "unknown_ticker"}
                        )
                        continue
                validated_trades.append(trade)
            trade_actions = validated_trades

    # Phase 2: single DB transaction
    chat_message_id = str(uuid.uuid4())
    executed_trades: list[dict] = []
    executed_wl_changes: list[dict] = []

    async with open_db() as db:
        await db.execute("BEGIN")
        try:
            # Insert user message
            await db.execute(
                "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
                "VALUES (?, ?, ?, ?, NULL, datetime('now'))",
                (str(uuid.uuid4()), "default", "user", user_message),
            )

            # Reload fresh cash balance
            user_row = await get_user(db, "default")
            current_cash = user_row["cash_balance"]

            # Execute each trade (partial success allowed)
            for idx, trade in enumerate(trade_actions):
                ticker = trade.ticker
                current_price = price_cache.get_price(ticker)

                # In simulator mode, auto-add unknown but syntactically valid tickers
                if current_price is None and not massive_mode and TICKER_RE.match(ticker):
                    try:
                        await market_source.add_ticker(ticker)
                        current_price = price_cache.get_price(ticker)
                    except Exception:
                        pass

                if current_price is None:
                    failed_actions.append(
                        {"type": "trade", "ticker": ticker, "error": "unknown_ticker"}
                    )
                    continue

                position = await get_position(db, "default", ticker)
                idempotency_key = f"{chat_message_id}:{idx}"

                if trade.side == "buy":
                    cost = current_price * trade.quantity
                    if cost > current_cash:
                        failed_actions.append(
                            {
                                "type": "trade",
                                "ticker": ticker,
                                "side": trade.side,
                                "quantity": trade.quantity,
                                "error": "insufficient_cash",
                                "message": f"Need ${cost:.2f}, have ${current_cash:.2f}",
                            }
                        )
                        continue
                    current_cash -= cost
                    if position and position["quantity"] > 0:
                        old_qty = position["quantity"]
                        new_qty = old_qty + trade.quantity
                        new_avg_cost = (
                            old_qty * position["avg_cost"] + trade.quantity * current_price
                        ) / new_qty
                    else:
                        new_qty = trade.quantity
                        new_avg_cost = current_price
                else:  # sell
                    owned = position["quantity"] if position else 0.0
                    if owned < trade.quantity:
                        failed_actions.append(
                            {
                                "type": "trade",
                                "ticker": ticker,
                                "side": trade.side,
                                "quantity": trade.quantity,
                                "error": "insufficient_shares",
                                "message": f"Own {owned:.6f}, tried to sell {trade.quantity}",
                            }
                        )
                        continue
                    proceeds = current_price * trade.quantity
                    current_cash += proceeds
                    new_qty = owned - trade.quantity
                    new_avg_cost = position["avg_cost"] if new_qty > 0 else None

                await update_cash(db, "default", current_cash)

                if new_qty > 0:
                    await upsert_position(db, "default", ticker, new_qty, new_avg_cost)
                elif position:
                    await delete_position(db, "default", ticker)

                trade_record = await insert_trade(
                    db,
                    user_id="default",
                    ticker=ticker,
                    side=trade.side,
                    quantity=trade.quantity,
                    price=current_price,
                    cash_balance_after=current_cash,
                    position_qty_after=new_qty,
                    position_avg_cost_after=new_avg_cost,
                    idempotency_key=idempotency_key,
                )
                executed_trades.append(
                    {
                        **trade_record,
                        "position": (
                            {
                                "ticker": ticker,
                                "quantity": round(new_qty, 6),
                                "avg_cost": round(new_avg_cost, 4),
                            }
                            if new_qty > 0 and new_avg_cost is not None
                            else None
                        ),
                    }
                )

                # Auto-add to watchlist if not present (implicit add for traded tickers)
                if not await watchlist_ticker_exists(db, "default", ticker):
                    await add_watchlist_ticker(db, "default", ticker)
                    executed_wl_changes.append({"ticker": ticker, "action": "add"})

            # Execute explicit watchlist changes
            for wl in wl_actions:
                ticker = wl.ticker
                if not TICKER_RE.match(ticker):
                    failed_actions.append(
                        {"type": "watchlist", "ticker": ticker, "error": "invalid_symbol"}
                    )
                    continue
                try:
                    if wl.action == "add":
                        if not await watchlist_ticker_exists(db, "default", ticker):
                            await add_watchlist_ticker(db, "default", ticker)
                            executed_wl_changes.append({"ticker": ticker, "action": "add"})
                    elif wl.action == "remove":
                        removed = await remove_watchlist_ticker(db, "default", ticker)
                        if removed:
                            executed_wl_changes.append({"ticker": ticker, "action": "remove"})
                except Exception as exc:
                    logger.error("Watchlist change failed for %s: %s", ticker, exc)
                    failed_actions.append(
                        {"type": "watchlist", "ticker": ticker, "error": "execution_error"}
                    )

            # Portfolio snapshot after all actions
            all_positions = await get_positions(db, "default")
            total_value = current_cash + sum(
                (price_cache.get_price(p["ticker"]) or 0.0) * p["quantity"]
                for p in all_positions
            )
            await insert_portfolio_snapshot(db, "default", total_value)

            # Build actions summary for assistant message
            actions_payload = {
                "trades": executed_trades,
                "watchlist_changes": executed_wl_changes,
                "failed": failed_actions,
            }

            # Insert assistant message
            await db.execute(
                "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
                "VALUES (?, ?, ?, ?, ?, datetime('now'))",
                (
                    str(uuid.uuid4()),
                    "default",
                    "assistant",
                    llm_response.message,
                    json.dumps(actions_payload),
                ),
            )

            await db.commit()

        except Exception:
            await db.rollback()
            raise

    # Phase 3: activate market source for new tickers (after commit)
    added_tickers = {c["ticker"] for c in executed_wl_changes if c["action"] == "add"}
    added_tickers |= {t["ticker"] for t in executed_trades}
    for ticker in added_tickers:
        try:
            await market_source.add_ticker(ticker)
        except Exception:
            logger.exception("Failed to start tracking %s after chat action", ticker)

    # Stop tracking tickers removed from watchlist (if no open position)
    removed_tickers = {c["ticker"] for c in executed_wl_changes if c["action"] == "remove"}
    if removed_tickers:
        async with open_db() as db:
            for ticker in removed_tickers:
                position = await get_position(db, "default", ticker)
                has_open_pos = position is not None and position["quantity"] > 0
                if not has_open_pos:
                    try:
                        await market_source.remove_ticker(ticker)
                    except Exception:
                        logger.exception("Failed to stop tracking %s", ticker)

    return {
        "message": llm_response.message,
        "trades": executed_trades,
        "watchlist_changes": executed_wl_changes,
        "failed": failed_actions,
    }
