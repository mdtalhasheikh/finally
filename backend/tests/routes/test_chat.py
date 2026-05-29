"""Tests for chat routes: POST /api/chat, GET /api/chat/history."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.llm.factory import create_llm_service
from app.market import PriceCache
from app.routes.chat import router
from database import get_db, init_db


def _make_mock_source() -> MagicMock:
    src = MagicMock()
    src.add_ticker = AsyncMock()
    src.remove_ticker = AsyncMock()
    return src


@pytest.fixture
def setup(tmp_path: Path):
    """
    Yields (TestClient, db_path, PriceCache, mock_source) with LLM_MOCK=true.
    AAPL and MSFT are seeded into the price cache.
    """
    db = str(tmp_path / "test.db")
    init_db(db)

    cache = PriceCache()
    cache.update("AAPL", 150.0)
    cache.update("MSFT", 300.0)

    mock_source = _make_mock_source()

    with patch.dict(os.environ, {"LLM_MOCK": "true"}):
        llm_service = create_llm_service()

    app = FastAPI()
    app.state.price_cache = cache
    app.state.market_source = mock_source
    app.state.llm_service = llm_service
    app.include_router(router)

    with (
        patch("app.routes.chat.config") as mock_cfg,
        patch("app.routes.chat.get_db", side_effect=lambda p: get_db(db)),
    ):
        mock_cfg.db_path = db
        mock_cfg.llm_max_history_messages = 20
        yield TestClient(app), db, cache, mock_source


# --- GET /api/chat/history ---

def test_chat_history_empty_initially(setup):
    client, *_ = setup
    resp = client.get("/api/chat/history")
    assert resp.status_code == 200
    assert resp.json() == []


# --- POST /api/chat basic ---

def test_chat_returns_mock_response(setup):
    client, *_ = setup
    resp = client.post("/api/chat", json={"message": "hello"})
    assert resp.status_code == 200
    data = resp.json()
    assert "message" in data
    assert "Mock response" in data["message"]
    assert data["trades"] == []
    assert data["watchlist_changes"] == []


def test_chat_stores_user_and_assistant_messages(setup):
    client, db_path, *_ = setup
    client.post("/api/chat", json={"message": "hello"})

    db = get_db(db_path)
    try:
        rows = db.execute(
            "SELECT role FROM chat_messages WHERE user_id = 'default' ORDER BY created_at"
        ).fetchall()
    finally:
        db.close()

    roles = [r["role"] for r in rows]
    assert "user" in roles
    assert "assistant" in roles


# --- POST /api/chat with mock-trade ---

def test_chat_mock_trade_executes_aapl_buy(setup):
    client, db_path, cache, _ = setup

    resp = client.post("/api/chat", json={"message": "mock-trade"})
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["trades"]) == 1
    trade = data["trades"][0]
    assert trade["ticker"] == "AAPL"
    assert trade["side"] == "buy"
    assert trade["quantity"] == pytest.approx(1.0)
    assert trade["status"] == "executed"
    assert trade["price"] == pytest.approx(150.0)


def test_chat_mock_trade_deducts_cash(setup):
    client, db_path, *_ = setup
    client.post("/api/chat", json={"message": "mock-trade"})

    db = get_db(db_path)
    try:
        row = db.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ).fetchone()
    finally:
        db.close()

    expected_cash = 10000.0 - 150.0
    assert pytest.approx(row["cash_balance"], abs=0.01) == expected_cash


# --- GET /api/chat/history after messages ---

def test_chat_history_returns_messages_after_chat(setup):
    client, *_ = setup
    client.post("/api/chat", json={"message": "hello"})

    resp = client.get("/api/chat/history")
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) >= 2  # user + assistant

    roles = [m["role"] for m in messages]
    assert "user" in roles
    assert "assistant" in roles


def test_chat_history_oldest_first(setup):
    client, *_ = setup
    client.post("/api/chat", json={"message": "first"})
    client.post("/api/chat", json={"message": "second"})

    resp = client.get("/api/chat/history")
    messages = resp.json()
    user_messages = [m for m in messages if m["role"] == "user"]
    assert user_messages[0]["content"] == "first"
    assert user_messages[1]["content"] == "second"


def test_chat_history_actions_parsed(setup):
    client, *_ = setup
    client.post("/api/chat", json={"message": "mock-trade"})

    resp = client.get("/api/chat/history")
    messages = resp.json()
    assistant_msgs = [m for m in messages if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    actions = assistant_msgs[0]["actions"]
    assert actions is not None
    assert "trades" in actions
    assert "watchlist_changes" in actions


# --- Failed trade does not block other trades ---

def test_failed_trade_does_not_break_sibling_trades(setup):
    """
    If the first trade fails (insufficient cash), the second should still be evaluated.
    We patch the LLM to return two trades: one impossible buy and one normal one.
    """
    from app.llm.models import LLMResponse, TradeAction

    async def mock_chat(user_message, portfolio_context, history):
        return LLMResponse(
            message="Trying two trades.",
            trades=[
                TradeAction(ticker="AAPL", side="buy", quantity=99999),  # will fail
                TradeAction(ticker="AAPL", side="buy", quantity=1),       # should succeed
            ],
            watchlist_changes=[],
        )

    client, db_path, _, _ = setup
    # Replace llm_service on the app
    app = client.app
    app.state.llm_service = MagicMock()
    app.state.llm_service.chat = mock_chat

    resp = client.post("/api/chat", json={"message": "two trades"})
    assert resp.status_code == 200
    data = resp.json()

    assert len(data["trades"]) == 2
    # First trade fails
    assert data["trades"][0]["status"] == "failed"
    assert data["trades"][0]["error"] == "insufficient_cash"
    # Second trade executes
    assert data["trades"][1]["status"] == "executed"


# --- Unknown ticker is reported as failed ---

def test_unknown_ticker_reported_as_failed(setup):
    from app.llm.models import LLMResponse, TradeAction

    async def mock_chat(user_message, portfolio_context, history):
        return LLMResponse(
            message="Buy unknown ticker.",
            trades=[TradeAction(ticker="ZZZZ", side="buy", quantity=1)],
            watchlist_changes=[],
        )

    client, *_ = setup
    app = client.app
    app.state.llm_service = MagicMock()
    app.state.llm_service.chat = mock_chat

    # Mock source raises on unknown ticker so it stays unresolved
    app.state.market_source.add_ticker.side_effect = Exception("not found")

    resp = client.post("/api/chat", json={"message": "buy zzzz"})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["trades"]) == 1
    assert data["trades"][0]["status"] == "failed"
    assert data["trades"][0]["error"] == "unknown_ticker"
