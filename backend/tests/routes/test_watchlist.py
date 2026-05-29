"""Tests for watchlist routes: GET, POST, DELETE /api/watchlist."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.market import PriceCache
from app.routes.watchlist import router
from database import get_db, init_db


def _make_mock_source() -> MagicMock:
    src = MagicMock()
    src.add_ticker = AsyncMock()
    src.remove_ticker = AsyncMock()
    return src


@pytest.fixture
def setup(tmp_path: Path):
    """Yields (TestClient, db_path, PriceCache, mock_source) with seed watchlist cleared."""
    db = str(tmp_path / "test.db")
    init_db(db)

    # Clear seed data so tests start with an empty watchlist
    conn = get_db(db)
    try:
        conn.execute("DELETE FROM watchlist WHERE user_id = 'default'")
        conn.commit()
    finally:
        conn.close()

    c = PriceCache()
    c.update("AAPL", 150.0)
    c.update("MSFT", 300.0)

    mock_source = _make_mock_source()

    app = FastAPI()
    app.state.price_cache = c
    app.state.market_source = mock_source
    app.include_router(router)

    with patch("app.routes.watchlist.config") as mock_cfg, \
         patch("app.routes.watchlist.get_db", side_effect=lambda p: get_db(db)):
        mock_cfg.db_path = db
        yield TestClient(app), db, c, mock_source


# --- GET ---

def test_get_watchlist_empty(setup):
    client, *_ = setup
    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_watchlist_returns_items_with_prices(setup):
    client, db_path, cache, _ = setup
    conn = get_db(db_path)
    try:
        conn.execute(
            "INSERT INTO watchlist (id, user_id, ticker, added_at) "
            "VALUES (?, 'default', 'AAPL', datetime('now'))",
            (str(uuid.uuid4()),),
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.get("/api/watchlist")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["ticker"] == "AAPL"
    assert pytest.approx(items[0]["price"]) == 150.0


# --- POST ---

def test_add_ticker_201(setup):
    client, *_ = setup
    resp = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["ticker"] == "AAPL"
    assert pytest.approx(data["price"]) == 150.0


def test_add_ticker_lowercase_normalized(setup):
    client, *_ = setup
    resp = client.post("/api/watchlist", json={"ticker": "aapl"})
    assert resp.status_code == 201
    assert resp.json()["ticker"] == "AAPL"


def test_add_ticker_duplicate_409(setup):
    client, *_ = setup
    client.post("/api/watchlist", json={"ticker": "AAPL"})
    resp = client.post("/api/watchlist", json={"ticker": "AAPL"})
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "ticker_already_exists"


def test_add_ticker_invalid_symbol_422(setup):
    client, *_ = setup
    resp = client.post("/api/watchlist", json={"ticker": "123"})
    assert resp.status_code == 422


def test_add_ticker_too_long_422(setup):
    client, *_ = setup
    resp = client.post("/api/watchlist", json={"ticker": "ABCDEFGHI"})  # 9 chars
    assert resp.status_code == 422


def test_add_ticker_calls_market_source(setup):
    client, _, _, mock_source = setup
    client.post("/api/watchlist", json={"ticker": "MSFT"})
    mock_source.add_ticker.assert_called_once_with("MSFT")


# --- DELETE ---

def test_delete_ticker_204(setup):
    client, *_ = setup
    client.post("/api/watchlist", json={"ticker": "AAPL"})
    resp = client.delete("/api/watchlist/AAPL")
    assert resp.status_code == 204


def test_delete_ticker_not_found_404(setup):
    client, *_ = setup
    resp = client.delete("/api/watchlist/ZZZZ")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_delete_ticker_lowercase_normalized(setup):
    client, *_ = setup
    client.post("/api/watchlist", json={"ticker": "AAPL"})
    resp = client.delete("/api/watchlist/aapl")
    assert resp.status_code == 204


def test_delete_removes_from_db(setup):
    client, db_path, _, _ = setup
    client.post("/api/watchlist", json={"ticker": "AAPL"})
    client.delete("/api/watchlist/AAPL")
    resp = client.get("/api/watchlist")
    tickers = [item["ticker"] for item in resp.json()]
    assert "AAPL" not in tickers
