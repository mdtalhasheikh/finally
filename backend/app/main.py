"""FinAlly FastAPI application — lifespan, global state, and router registration."""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

load_dotenv()  # Load .env from cwd (works when cwd is /app in Docker)

from app.config import config
from app.llm import create_llm_service
from app.market import PriceCache, create_market_data_source, create_stream_router
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router
from app.routes.portfolio import router as portfolio_router
from app.routes.watchlist import router as watchlist_router
from database import get_db, init_db

logger = logging.getLogger(__name__)

# Module-level cache so lifespan helpers can reference it
price_cache: PriceCache = PriceCache()


# --- Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Assert API key unless mock mode
    llm_mock = os.getenv("LLM_MOCK", "false").lower() == "true"
    if not llm_mock and not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. Add it to .env. Set LLM_MOCK=true to skip."
        )

    # 2. Init DB — creates tables and seeds on first run
    init_db(config.db_path)

    # 3. Collect tickers from watchlist + open positions
    db = get_db(config.db_path)
    try:
        watchlist_rows = db.execute(
            "SELECT ticker FROM watchlist WHERE user_id = 'default'"
        ).fetchall()
        position_rows = db.execute(
            "SELECT ticker FROM positions WHERE user_id = 'default' AND quantity > 0"
        ).fetchall()
        initial_tickers = list(
            {row["ticker"] for row in watchlist_rows} | {row["ticker"] for row in position_rows}
        )
    finally:
        db.close()

    # 4. Start market data source
    market_source = create_market_data_source(price_cache)
    await market_source.start(initial_tickers)
    app.state.market_source = market_source

    # 5. Create LLM service
    app.state.llm_service = create_llm_service()

    # 6. Record an immediate portfolio snapshot
    asyncio.create_task(_record_snapshot())

    # 7. Start periodic snapshot writer
    snapshot_task = asyncio.create_task(_snapshot_loop())

    yield

    # Shutdown
    snapshot_task.cancel()
    try:
        await snapshot_task
    except asyncio.CancelledError:
        pass
    await market_source.stop()


# --- Background helpers ---

async def _record_snapshot() -> None:
    """Write one portfolio total-value snapshot to the DB."""
    db = get_db(config.db_path)
    try:
        rows = db.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = 'default' AND quantity > 0"
        ).fetchall()
        cash_row = db.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ).fetchone()
        cash = cash_row["cash_balance"] if cash_row else 0.0
        total = cash + sum(
            row["quantity"] * (price_cache.get_price(row["ticker"]) or row["avg_cost"])
            for row in rows
        )
        db.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), round(total, 2), datetime.now(timezone.utc).isoformat()),
        )
        db.commit()
    finally:
        db.close()


async def _snapshot_loop() -> None:
    """Periodically record portfolio snapshots."""
    while True:
        await asyncio.sleep(config.portfolio_snapshot_interval_seconds)
        try:
            await _record_snapshot()
        except Exception as exc:
            logger.error("Snapshot error: %s", exc)


# --- App assembly ---

app = FastAPI(title="FinAlly API", lifespan=lifespan)

app.state.price_cache = price_cache
app.state.market_source = None  # Set during lifespan after source starts

stream_router = create_stream_router(price_cache)
app.include_router(health_router)
app.include_router(stream_router)
app.include_router(portfolio_router)
app.include_router(watchlist_router)
app.include_router(chat_router)

# Serve static Next.js export — must be last so API routes take precedence
_static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_static_dir):
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
