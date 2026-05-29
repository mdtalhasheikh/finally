"""Watchlist API endpoints.

GET    /api/watchlist          - Current watchlist with live prices
POST   /api/watchlist          - Add a ticker
DELETE /api/watchlist/{ticker} - Remove a ticker
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, field_validator

from ..db import (
    add_watchlist_ticker,
    get_watchlist,
    open_db,
    remove_watchlist_ticker,
    watchlist_ticker_exists,
)
from ..market import MarketDataSource, PriceCache

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

TICKER_RE = re.compile(r"^[A-Z]{1,8}$")


def _error(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _enrich_with_prices(watchlist: list[dict], price_cache: PriceCache) -> list[dict]:
    """Add current_price, session_open, daily_change_pct to each watchlist entry."""
    result = []
    for entry in watchlist:
        ticker = entry["ticker"]
        update = price_cache.get(ticker)
        result.append(
            {
                "ticker": ticker,
                "added_at": entry["added_at"],
                "current_price": round(update.price, 2) if update else None,
                "session_open": round(update.session_open, 2) if update else None,
                "daily_change_pct": round(update.daily_change_pct, 4) if update else None,
            }
        )
    return result


@router.get("")
async def get_watchlist_route(request: Request) -> list[dict]:
    price_cache: PriceCache = request.app.state.price_cache
    async with open_db() as db:
        watchlist = await get_watchlist(db, "default")
    return _enrich_with_prices(watchlist, price_cache)


class AddTickerRequest(BaseModel):
    ticker: str

    @field_validator("ticker")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.upper().strip()


@router.post("", status_code=201)
async def add_ticker(body: AddTickerRequest, request: Request) -> dict:
    ticker = body.ticker
    if not TICKER_RE.match(ticker):
        raise HTTPException(
            422,
            detail=_error("invalid_symbol", f"Invalid ticker symbol: {ticker}", {"ticker": ticker}),
        )

    market_source: MarketDataSource = request.app.state.market_source
    price_cache: PriceCache = request.app.state.price_cache

    async with open_db() as db:
        if await watchlist_ticker_exists(db, "default", ticker):
            raise HTTPException(
                409,
                detail=_error(
                    "ticker_already_exists",
                    f"{ticker} is already on the watchlist",
                    {"ticker": ticker},
                ),
            )

        # Massive mode: validate ticker exists in Polygon (5s timeout)
        # Simulator mode: any syntactically valid symbol is accepted
        # The market source knows which mode it's in via its type
        from ..market.massive_client import MassiveDataSource

        if isinstance(market_source, MassiveDataSource):
            is_valid = await _validate_massive_ticker(market_source, ticker)
            if not is_valid:
                raise HTTPException(
                    422,
                    detail=_error(
                        "unknown_ticker",
                        f"Ticker {ticker} not found in market data",
                        {"ticker": ticker},
                    ),
                )

        entry = await add_watchlist_ticker(db, "default", ticker)
        await db.commit()

    # Start tracking the new ticker (non-blocking — errors are logged)
    try:
        await market_source.add_ticker(ticker)
    except Exception:
        logger.exception("Failed to start tracking %s after watchlist add", ticker)

    update = price_cache.get(ticker)
    return {
        "ticker": ticker,
        "added_at": entry["added_at"],
        "current_price": round(update.price, 2) if update else None,
        "session_open": round(update.session_open, 2) if update else None,
        "daily_change_pct": round(update.daily_change_pct, 4) if update else None,
    }


@router.delete("/{ticker}", status_code=204)
async def delete_ticker(ticker: str, request: Request) -> Response:
    ticker = ticker.upper().strip()
    market_source: MarketDataSource = request.app.state.market_source

    async with open_db() as db:
        removed = await remove_watchlist_ticker(db, "default", ticker)
        if not removed:
            raise HTTPException(
                404,
                detail=_error("ticker_not_found", f"{ticker} is not on the watchlist", {"ticker": ticker}),
            )

        # Only stop tracking if there's no open position in this ticker
        from ..db import get_position

        position = await get_position(db, "default", ticker)
        await db.commit()

    has_position = position and position["quantity"] > 0
    if not has_position:
        try:
            await market_source.remove_ticker(ticker)
        except Exception:
            logger.exception("Failed to stop tracking %s after watchlist remove", ticker)

    return Response(status_code=204)


async def _validate_massive_ticker(source, ticker: str) -> bool:
    """Check Polygon for the ticker. Returns False if symbol is unknown."""
    import asyncio

    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_probe_massive, source, ticker),
            timeout=5.0,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("Massive ticker validation timed out for %s", ticker)
        return False
    except Exception:
        logger.exception("Massive ticker validation failed for %s", ticker)
        return False


def _probe_massive(source, ticker: str) -> bool:
    """Synchronous Polygon probe. Runs in a thread."""
    from massive.rest.models import SnapshotMarketType

    try:
        snap = source._client.get_snapshot_ticker(
            market_type=SnapshotMarketType.STOCKS,
            ticker=ticker,
        )
        return snap is not None and snap.last_trade is not None
    except Exception:
        return False
