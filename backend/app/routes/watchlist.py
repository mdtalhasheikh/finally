"""Watchlist endpoints: list, add, remove tickers."""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from app.config import config
from app.market import PriceCache
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

_TICKER_RE = re.compile(r"^[A-Z]{1,8}$")


class AddTickerRequest(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def validate_ticker(cls, v: str) -> str:
        v = v.upper().strip()
        if not _TICKER_RE.match(v):
            raise ValueError("ticker must be 1-8 uppercase letters")
        return v


def _error(code: str, message: str, details: dict | None = None, status: int = 422) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or {}}},
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@router.get("/api/watchlist")
async def get_watchlist(request: Request) -> list:
    """Return watchlist items with live prices and daily change."""
    cache: PriceCache = request.app.state.price_cache

    db = get_db(config.db_path)
    try:
        rows = db.execute(
            "SELECT ticker, added_at FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
        ).fetchall()
    finally:
        db.close()

    result = []
    for row in rows:
        ticker = row["ticker"]
        update = cache.get(ticker)
        current_price = update.price if update else None
        # session_open not yet tracked in PriceUpdate; use current price so daily_change starts at 0
        session_open = getattr(update, "session_open", current_price)
        daily_change_pct = (
            round((current_price - session_open) / session_open * 100, 4)
            if current_price and session_open
            else 0.0
        )
        result.append(
            {
                "ticker": ticker,
                "added_at": row["added_at"],
                "current_price": current_price,
                "session_open": session_open,
                "daily_change_pct": daily_change_pct,
            }
        )
    return result


@router.post("/api/watchlist", status_code=201)
async def add_to_watchlist(body: AddTickerRequest, request: Request) -> JSONResponse:
    """Add a ticker to the watchlist. Returns 409 if already present."""
    ticker = body.ticker  # already validated + uppercased
    cache: PriceCache = request.app.state.price_cache
    market_source = request.app.state.market_source

    db = get_db(config.db_path)
    try:
        existing = db.execute(
            "SELECT id FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        ).fetchone()
        if existing:
            return _error("ticker_already_exists", f"{ticker} is already on the watchlist", status=409)

        db.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), ticker, _now_iso()),
        )
        db.commit()
    finally:
        db.close()

    if market_source is not None:
        try:
            await market_source.add_ticker(ticker)
        except Exception:
            logger.warning("Failed to add %s to market source", ticker)

    price_update = cache.get(ticker)
    return JSONResponse(
        status_code=201,
        content={
            "ticker": ticker,
            "price": price_update.price if price_update else None,
            "daily_change_pct": price_update.change_percent if price_update else None,
        },
    )


@router.delete("/api/watchlist/{ticker}", status_code=204)
async def remove_from_watchlist(ticker: str, request: Request) -> JSONResponse:
    """Remove a ticker from the watchlist. Returns 404 if not present."""
    ticker = ticker.upper().strip()
    market_source = request.app.state.market_source

    db = get_db(config.db_path)
    try:
        row = db.execute(
            "SELECT id FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        ).fetchone()
        if not row:
            return _error("not_found", f"{ticker} is not on the watchlist", status=404)

        db.execute(
            "DELETE FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        )
        db.commit()
    finally:
        db.close()

    # Only remove from market source if no open position in this ticker
    db2 = get_db(config.db_path)
    try:
        pos = db2.execute(
            "SELECT quantity FROM positions WHERE user_id = 'default' AND ticker = ? AND quantity > 0",
            (ticker,),
        ).fetchone()
    finally:
        db2.close()

    if pos is None and market_source is not None:
        try:
            await market_source.remove_ticker(ticker)
        except Exception:
            logger.warning("Failed to remove %s from market source", ticker)

    return JSONResponse(status_code=204, content=None)
