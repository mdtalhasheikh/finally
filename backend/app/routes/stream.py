"""SSE stream route that reads price_cache from app.state."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stream", tags=["streaming"])


@router.get("/prices")
async def stream_prices(request: Request) -> StreamingResponse:
    """SSE endpoint: live price updates for all tracked tickers.

    Streams every ~500ms. Uses EventSource on the client side (auto-reconnects).
    Payload: {"AAPL": {ticker, price, previous_price, ...}, ...}
    """
    price_cache = request.app.state.price_cache
    return StreamingResponse(
        _generate_events(price_cache, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


async def _generate_events(
    price_cache, request: Request, interval: float = 0.5
) -> AsyncGenerator[str, None]:
    yield "retry: 1000\n\n"

    last_version = -1
    client_ip = request.client.host if request.client else "unknown"
    logger.info("SSE client connected: %s", client_ip)

    try:
        while True:
            if await request.is_disconnected():
                logger.info("SSE client disconnected: %s", client_ip)
                break

            current_version = price_cache.version
            if current_version != last_version:
                last_version = current_version
                prices = price_cache.get_all()
                if prices:
                    data = {ticker: update.to_dict() for ticker, update in prices.items()}
                    yield f"data: {json.dumps(data)}\n\n"

            await asyncio.sleep(interval)
    except asyncio.CancelledError:
        logger.info("SSE stream cancelled for: %s", client_ip)
