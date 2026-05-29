"""Unit tests for LLM models, mock service, and factory."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.llm.factory import create_llm_service
from app.llm.mock import MockLLMService
from app.llm.models import LLMResponse, TradeAction, WatchlistAction
from app.llm.service import LLMService


# --- Model tests ---

def test_llm_response_defaults():
    r = LLMResponse(message="hello")
    assert r.message == "hello"
    assert r.trades == []
    assert r.watchlist_changes == []


def test_llm_response_parses_json():
    raw = '{"message": "ok", "trades": [], "watchlist_changes": []}'
    r = LLMResponse.model_validate_json(raw)
    assert r.message == "ok"
    assert r.trades == []
    assert r.watchlist_changes == []


def test_trade_action_fields():
    t = TradeAction(ticker="AAPL", side="buy", quantity=5.0)
    assert t.ticker == "AAPL"
    assert t.side == "buy"
    assert t.quantity == pytest.approx(5.0)


def test_watchlist_action_fields():
    w = WatchlistAction(ticker="TSLA", action="add")
    assert w.ticker == "TSLA"
    assert w.action == "add"


def test_llm_response_with_trades_and_watchlist():
    r = LLMResponse(
        message="Buying AAPL and adding TSLA to watchlist.",
        trades=[TradeAction(ticker="AAPL", side="buy", quantity=2.0)],
        watchlist_changes=[WatchlistAction(ticker="TSLA", action="add")],
    )
    assert len(r.trades) == 1
    assert len(r.watchlist_changes) == 1


def test_llm_response_parses_json_with_trades():
    raw = (
        '{"message": "done", '
        '"trades": [{"ticker": "AAPL", "side": "buy", "quantity": 3}], '
        '"watchlist_changes": []}'
    )
    r = LLMResponse.model_validate_json(raw)
    assert len(r.trades) == 1
    assert r.trades[0].ticker == "AAPL"
    assert r.trades[0].quantity == pytest.approx(3.0)


# --- MockLLMService tests ---

@pytest.mark.asyncio
async def test_mock_default_response():
    svc = MockLLMService()
    result = await svc.chat("how are you?", {}, [])
    assert isinstance(result, LLMResponse)
    assert result.trades == []
    assert result.watchlist_changes == []
    assert "Mock response" in result.message


@pytest.mark.asyncio
async def test_mock_trade_response():
    svc = MockLLMService()
    result = await svc.chat("please mock-trade for me", {}, [])
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.ticker == "AAPL"
    assert trade.side == "buy"
    assert trade.quantity == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_mock_trade_response_case_insensitive():
    svc = MockLLMService()
    result = await svc.chat("MOCK-TRADE please", {}, [])
    assert len(result.trades) == 1


# --- Factory tests ---

def test_create_llm_service_returns_mock_when_env_true():
    with patch.dict(os.environ, {"LLM_MOCK": "true"}):
        svc = create_llm_service()
    assert isinstance(svc, MockLLMService)


def test_create_llm_service_returns_llm_service_when_not_mock():
    env = {k: v for k, v in os.environ.items() if k != "LLM_MOCK"}
    env["LLM_MOCK"] = "false"
    with patch.dict(os.environ, env, clear=True):
        svc = create_llm_service()
    assert isinstance(svc, LLMService)


def test_create_llm_service_mock_false_string():
    with patch.dict(os.environ, {"LLM_MOCK": "false"}):
        svc = create_llm_service()
    assert isinstance(svc, LLMService)


def test_create_llm_service_mock_missing_env():
    env = {k: v for k, v in os.environ.items() if k != "LLM_MOCK"}
    with patch.dict(os.environ, env, clear=True):
        svc = create_llm_service()
    assert isinstance(svc, LLMService)
