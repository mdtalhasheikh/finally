"""Portfolio API endpoints.

GET  /api/portfolio         - Positions, cash balance, total value, P&L
POST /api/portfolio/trade   - Execute a market order
GET  /api/portfolio/history - Portfolio value snapshots (for P&L chart)
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from ..db import (
    delete_position,
    get_portfolio_history,
    get_position,
    get_positions,
    get_trade_by_idempotency_key,
    get_user,
    insert_portfolio_snapshot,
    insert_trade,
    open_db,
    update_cash,
    upsert_position,
)
from ..market import PriceCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

TICKER_RE = re.compile(r"^[A-Z]{1,8}$")


def _error(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _build_portfolio(
    positions: list[dict],
    cash_balance: float,
    price_cache: PriceCache,
) -> dict:
    """Compute portfolio response from DB positions + live prices."""
    position_rows = []
    total_unrealized_pnl = 0.0
    total_positions_value = 0.0

    for pos in positions:
        ticker = pos["ticker"]
        qty = pos["quantity"]
        avg_cost = pos["avg_cost"]

        update = price_cache.get(ticker)
        current_price = update.price if update else 0.0
        session_open = update.session_open if update else 0.0
        daily_change_pct = update.daily_change_pct if update else 0.0

        unrealized_pnl = (current_price - avg_cost) * qty
        unrealized_pnl_pct = (
            (current_price - avg_cost) / avg_cost * 100 if avg_cost else 0.0
        )
        position_value = current_price * qty
        total_positions_value += position_value
        total_unrealized_pnl += unrealized_pnl

        position_rows.append(
            {
                "ticker": ticker,
                "quantity": round(qty, 6),
                "avg_cost": round(avg_cost, 4),
                "current_price": round(current_price, 2),
                "session_open": round(session_open, 2),
                "daily_change_pct": round(daily_change_pct, 4),
                "unrealized_pnl": round(unrealized_pnl, 2),
                "unrealized_pnl_pct": round(unrealized_pnl_pct, 4),
            }
        )

    return {
        "cash_balance": round(cash_balance, 2),
        "total_value": round(cash_balance + total_positions_value, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "positions": position_rows,
    }


@router.get("")
async def get_portfolio(request: Request) -> dict:
    price_cache: PriceCache = request.app.state.price_cache
    async with open_db() as db:
        user = await get_user(db, "default")
        if not user:
            raise HTTPException(500, detail=_error("internal", "User not found"))
        positions = await get_positions(db, "default")
    return _build_portfolio(positions, user["cash_balance"], price_cache)


# ---------------------------------------------------------------------------
# Trade execution
# ---------------------------------------------------------------------------

class TradeRequest(BaseModel):
    ticker: str
    side: str
    quantity: float
    idempotency_key: str | None = None

    @field_validator("ticker")
    @classmethod
    def normalize_ticker(cls, v: str) -> str:
        return v.upper().strip()

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
            raise ValueError("quantity must be positive")
        return v


@router.post("/trade")
async def execute_trade(trade_req: TradeRequest, request: Request) -> JSONResponse:
    ticker = trade_req.ticker
    if not TICKER_RE.match(ticker):
        raise HTTPException(
            422,
            detail=_error("invalid_symbol", f"Invalid ticker symbol: {ticker}", {"ticker": ticker}),
        )

    price_cache: PriceCache = request.app.state.price_cache
    current_price = price_cache.get_price(ticker)
    if current_price is None:
        raise HTTPException(
            422,
            detail=_error("unknown_ticker", f"No price data for {ticker}", {"ticker": ticker}),
        )

    async with open_db() as db:
        # Idempotency check
        if trade_req.idempotency_key:
            existing = await get_trade_by_idempotency_key(db, "default", trade_req.idempotency_key)
            if existing:
                pos_qty = existing["position_qty_after"]
                pos_cost = existing["position_avg_cost_after"]
                return JSONResponse(
                    status_code=200,
                    content={
                        "trade": {
                            "id": existing["id"],
                            "ticker": existing["ticker"],
                            "side": existing["side"],
                            "quantity": existing["quantity"],
                            "price": existing["price"],
                            "executed_at": existing["executed_at"],
                        },
                        "cash_balance": existing["cash_balance_after"],
                        "position": (
                            {
                                "ticker": existing["ticker"],
                                "quantity": pos_qty,
                                "avg_cost": pos_cost,
                            }
                            if pos_qty > 0
                            else None
                        ),
                    },
                )

        user = await get_user(db, "default")
        if not user:
            raise HTTPException(500, detail=_error("internal", "User not found"))
        cash = user["cash_balance"]
        position = await get_position(db, "default", ticker)

        # Business logic
        if trade_req.side == "buy":
            cost = current_price * trade_req.quantity
            if cost > cash:
                raise HTTPException(
                    400,
                    detail=_error(
                        "insufficient_cash",
                        f"Need ${cost:.2f} but only ${cash:.2f} available",
                        {"required": round(cost, 2), "available": round(cash, 2)},
                    ),
                )
            new_cash = cash - cost
            if position:
                old_qty = position["quantity"]
                old_cost = position["avg_cost"]
                new_qty = old_qty + trade_req.quantity
                new_avg_cost = (old_qty * old_cost + trade_req.quantity * current_price) / new_qty
            else:
                new_qty = trade_req.quantity
                new_avg_cost = current_price

        else:  # sell
            if not position or position["quantity"] < trade_req.quantity:
                owned = position["quantity"] if position else 0.0
                raise HTTPException(
                    400,
                    detail=_error(
                        "insufficient_shares",
                        f"Trying to sell {trade_req.quantity} but only {owned:.6f} owned",
                        {"requested": trade_req.quantity, "owned": owned},
                    ),
                )
            proceeds = current_price * trade_req.quantity
            new_cash = cash + proceeds
            new_qty = position["quantity"] - trade_req.quantity
            new_avg_cost = position["avg_cost"] if new_qty > 0 else None

        # Persist within a transaction
        await db.execute("BEGIN")
        try:
            await update_cash(db, "default", new_cash)

            if new_qty > 0:
                await upsert_position(db, "default", ticker, new_qty, new_avg_cost)
            elif position:
                await delete_position(db, "default", ticker)

            trade = await insert_trade(
                db,
                user_id="default",
                ticker=ticker,
                side=trade_req.side,
                quantity=trade_req.quantity,
                price=current_price,
                cash_balance_after=new_cash,
                position_qty_after=new_qty,
                position_avg_cost_after=new_avg_cost,
                idempotency_key=trade_req.idempotency_key,
            )

            # Snapshot immediately after trade
            positions_all = await get_positions(db, "default")
            total_value = new_cash + sum(
                (price_cache.get_price(p["ticker"]) or 0.0) * p["quantity"]
                for p in positions_all
            )
            await insert_portfolio_snapshot(db, "default", total_value)

            await db.commit()
        except Exception:
            await db.rollback()
            raise

    return JSONResponse(
        status_code=201,
        content={
            "trade": trade,
            "cash_balance": round(new_cash, 2),
            "position": (
                {
                    "ticker": ticker,
                    "quantity": round(new_qty, 6),
                    "avg_cost": round(new_avg_cost, 4) if new_avg_cost else None,
                }
                if new_qty > 0
                else None
            ),
        },
    )


# ---------------------------------------------------------------------------
# Portfolio history
# ---------------------------------------------------------------------------

@router.get("/history")
async def get_history(limit: int = 500) -> list[dict]:
    limit = max(1, min(limit, 2000))
    async with open_db() as db:
        return await get_portfolio_history(db, "default", limit)
