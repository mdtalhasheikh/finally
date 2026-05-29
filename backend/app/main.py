"""FinAlly FastAPI application.

Entry point: uvicorn app.main:app --host 0.0.0.0 --port 8000

Serves:
  /api/*           REST endpoints
  /api/stream/*    SSE streaming
  /*               Static files (Next.js export, production only)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .config import config, get_openrouter_api_key
from .db import get_positions, get_tracked_tickers, get_user, init_db, insert_portfolio_snapshot, open_db
from .market import PriceCache, create_market_data_source
from .routes.chat import router as chat_router
from .routes.health import router as health_router
from .routes.portfolio import router as portfolio_router
from .routes.stream import router as stream_router
from .routes.watchlist import router as watchlist_router

# Load .env from project root (two levels above app/)
_ENV_PATH = Path(__file__).parent.parent.parent / ".env"
if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup initialization and graceful shutdown."""
    # 1. Assert required env vars (fast boot failure if missing)
    try:
        get_openrouter_api_key()
    except RuntimeError as exc:
        logger.critical("Boot failure: %s", exc)
        raise SystemExit(1) from exc

    # 2. Initialize database (idempotent: creates tables + seeds if empty)
    async with open_db() as db:
        await init_db(db)
        initial_tickers = await get_tracked_tickers(db)

    logger.info(
        "DB initialized. Tracking %d tickers: %s", len(initial_tickers), sorted(initial_tickers)
    )

    # 3. Start market data source (simulator or Massive); seeds price cache
    price_cache = PriceCache()
    market_source = create_market_data_source(price_cache)
    await market_source.start(initial_tickers or config.DEFAULT_TICKERS)
    logger.info("Market data source started")

    # 4. Initial portfolio snapshot (price cache is warm, valuation is valid)
    async with open_db() as db:
        user = await get_user(db, "default")
        positions = await get_positions(db, "default")
        if user:
            total_value = user["cash_balance"] + sum(
                (price_cache.get_price(p["ticker"]) or 0.0) * p["quantity"]
                for p in positions
            )
            await insert_portfolio_snapshot(db, "default", total_value)
            await db.commit()

    # 5. Background portfolio snapshot writer
    snapshot_task = asyncio.create_task(
        _portfolio_snapshot_loop(price_cache), name="portfolio-snapshot"
    )

    # 6. Expose shared state to route handlers via app.state
    app.state.price_cache = price_cache
    app.state.market_source = market_source

    logger.info("FinAlly backend ready on port 8000")
    yield

    # Shutdown — cancel background tasks, stop market source
    snapshot_task.cancel()
    try:
        await snapshot_task
    except asyncio.CancelledError:
        pass
    await market_source.stop()
    logger.info("FinAlly backend shut down cleanly")


async def _portfolio_snapshot_loop(price_cache: PriceCache) -> None:
    """Record portfolio total value every PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS."""
    interval = config.PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS
    while True:
        await asyncio.sleep(interval)
        try:
            async with open_db() as db:
                user = await get_user(db, "default")
                positions = await get_positions(db, "default")
                if user:
                    total_value = user["cash_balance"] + sum(
                        (price_cache.get_price(p["ticker"]) or 0.0) * p["quantity"]
                        for p in positions
                    )
                    await insert_portfolio_snapshot(db, "default", total_value)
                    await db.commit()
        except Exception:
            logger.exception("Portfolio snapshot loop error")


def create_app() -> FastAPI:
    application = FastAPI(
        title="FinAlly API",
        description="AI-powered trading workstation backend",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS: allow Next.js dev server (port 3000) and same-origin in production
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://localhost:8000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    application.include_router(health_router)
    application.include_router(stream_router)
    application.include_router(portfolio_router)
    application.include_router(watchlist_router)
    application.include_router(chat_router)

    return application


app = create_app()

# Static file serving (production: Next.js export built into static/)
_STATIC_DIR = Path(__file__).parent.parent.parent / "static"
if _STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_STATIC_DIR), html=True), name="static")
