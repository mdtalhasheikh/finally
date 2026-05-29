"""Tests for portfolio routes: GET /api/portfolio, POST /api/portfolio/trade, GET /api/portfolio/history."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.market import PriceCache
from app.routes.portfolio import router
from database import get_db, init_db


def _make_app(cache: PriceCache) -> FastAPI:
    app = FastAPI()
    app.state.price_cache = cache
    app.state.market_source = None
    app.include_router(router)
    return app


@pytest.fixture
def setup(tmp_path: Path):
    """Yields (TestClient, db_path, PriceCache) with config.db_path patched."""
    db = str(tmp_path / "test.db")
    init_db(db)

    c = PriceCache()
    c.update("AAPL", 150.0)
    c.update("GOOGL", 2800.0)

    app = _make_app(c)

    with patch("app.routes.portfolio.config") as mock_cfg, \
         patch("app.routes.portfolio.get_db", side_effect=lambda p: get_db(db)):
        mock_cfg.db_path = db
        yield TestClient(app), db, c


# --- GET /api/portfolio ---

def test_portfolio_no_positions(setup):
    client, db_path, _ = setup
    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert data["positions"] == []
    assert pytest.approx(data["cash_balance"], abs=0.01) == 10000.0
    assert pytest.approx(data["total_value"], abs=0.01) == 10000.0


def test_portfolio_with_position(setup):
    client, db_path, _ = setup
    db = get_db(db_path)
    try:
        db.execute(
            "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
            "VALUES (?, 'default', 'AAPL', 10, 140.0, datetime('now'))",
            (str(uuid.uuid4()),),
        )
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/portfolio")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["positions"]) == 1
    pos = data["positions"][0]
    assert pos["ticker"] == "AAPL"
    assert pytest.approx(pos["current_price"]) == 150.0
    assert pytest.approx(pos["unrealized_pnl"]) == (150.0 - 140.0) * 10


# --- POST /api/portfolio/trade (buy) ---

def test_trade_buy_happy_path(setup):
    client, db_path, _ = setup
    resp = client.post("/api/portfolio/trade", json={
        "ticker": "AAPL", "quantity": 5, "side": "buy"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["trade"]["ticker"] == "AAPL"
    assert data["trade"]["side"] == "buy"
    assert pytest.approx(data["trade"]["price"]) == 150.0
    assert pytest.approx(data["cash_balance"]) == 10000.0 - 5 * 150.0
    assert data["position"]["quantity"] == 5


def test_trade_sell_happy_path(setup):
    client, db_path, _ = setup
    client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 10, "side": "buy"})
    resp = client.post("/api/portfolio/trade", json={"ticker": "AAPL", "quantity": 4, "side": "sell"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["position"]["quantity"] == 6
    expected_cash = 10000.0 - 10 * 150.0 + 4 * 150.0
    assert pytest.approx(data["cash_balance"]) == expected_cash


def test_trade_insufficient_cash(setup):
    client, _, _ = setup
    resp = client.post("/api/portfolio/trade", json={
        "ticker": "AAPL", "quantity": 200, "side": "buy"
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "insufficient_cash"


def test_trade_insufficient_shares(setup):
    client, _, _ = setup
    resp = client.post("/api/portfolio/trade", json={
        "ticker": "AAPL", "quantity": 1, "side": "sell"
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "insufficient_shares"


def test_trade_unknown_ticker(setup):
    client, _, _ = setup
    resp = client.post("/api/portfolio/trade", json={
        "ticker": "ZZZZ", "quantity": 1, "side": "buy"
    })
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "unknown_ticker"


def test_trade_quantity_zero_rejected(setup):
    client, _, _ = setup
    resp = client.post("/api/portfolio/trade", json={
        "ticker": "AAPL", "quantity": 0, "side": "buy"
    })
    # Pydantic validation rejects quantity <= 0
    assert resp.status_code == 422


def test_trade_quantity_negative_rejected(setup):
    client, _, _ = setup
    resp = client.post("/api/portfolio/trade", json={
        "ticker": "AAPL", "quantity": -5, "side": "buy"
    })
    assert resp.status_code == 422


def test_trade_idempotency_replay(setup):
    client, _, _ = setup
    payload = {"ticker": "AAPL", "quantity": 2, "side": "buy", "idempotency_key": "key-abc-123"}

    resp1 = client.post("/api/portfolio/trade", json=payload)
    assert resp1.status_code == 201
    original = resp1.json()

    resp2 = client.post("/api/portfolio/trade", json=payload)
    assert resp2.status_code == 200  # idempotent replay
    replayed = resp2.json()

    assert pytest.approx(replayed["cash_balance"]) == original["cash_balance"]
    assert replayed["position"]["quantity"] == original["position"]["quantity"]


# --- GET /api/portfolio/history ---

def test_portfolio_history_empty(setup):
    client, _, _ = setup
    resp = client.get("/api/portfolio/history")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_portfolio_history_limit(setup):
    client, db_path, _ = setup
    db = get_db(db_path)
    try:
        for i in range(10):
            db.execute(
                "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
                "VALUES (?, 'default', ?, datetime('now'))",
                (str(uuid.uuid4()), 10000.0 + i),
            )
        db.commit()
    finally:
        db.close()

    resp = client.get("/api/portfolio/history?limit=5")
    assert resp.status_code == 200
    assert len(resp.json()) == 5
