"""Tests for LLM mock and structured output parsing."""

from __future__ import annotations

import pytest

from app.llm.client import ChatResponse, TradeAction, WatchlistAction
from app.llm.mock import mock_llm_response


class TestChatResponse:
    def test_valid_response(self):
        resp = ChatResponse(message="Hello", trades=[], watchlist_changes=[])
        assert resp.message == "Hello"
        assert resp.trades == []

    def test_with_trades(self):
        resp = ChatResponse.model_validate(
            {
                "message": "Buying AAPL",
                "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
            }
        )
        assert len(resp.trades) == 1
        assert resp.trades[0].ticker == "AAPL"
        assert resp.trades[0].side == "buy"
        assert resp.trades[0].quantity == 10

    def test_ticker_normalized_uppercase(self):
        trade = TradeAction(ticker="aapl", side="buy", quantity=1)
        assert trade.ticker == "AAPL"

    def test_invalid_side_raises(self):
        with pytest.raises(Exception):
            TradeAction(ticker="AAPL", side="hold", quantity=1)

    def test_invalid_quantity_raises(self):
        with pytest.raises(Exception):
            TradeAction(ticker="AAPL", side="buy", quantity=0)

    def test_negative_quantity_raises(self):
        with pytest.raises(Exception):
            TradeAction(ticker="AAPL", side="buy", quantity=-5)

    def test_watchlist_action_normalized(self):
        action = WatchlistAction(ticker="googl", action="add")
        assert action.ticker == "GOOGL"

    def test_invalid_watchlist_action_raises(self):
        with pytest.raises(Exception):
            WatchlistAction(ticker="AAPL", action="unknown")

    def test_no_trades_required(self):
        resp = ChatResponse.model_validate({"message": "Just chatting"})
        assert resp.trades == []
        assert resp.watchlist_changes == []


class TestMockLLM:
    def test_default_response(self):
        resp = mock_llm_response("Hello, how are you?")
        assert "Mock response" in resp.message
        assert resp.trades == []
        assert resp.watchlist_changes == []

    def test_trade_trigger(self):
        resp = mock_llm_response("Please mock-trade something")
        assert len(resp.trades) == 1
        assert resp.trades[0].ticker == "AAPL"
        assert resp.trades[0].side == "buy"
        assert resp.trades[0].quantity == 1

    def test_trade_trigger_case_insensitive(self):
        resp = mock_llm_response("MOCK-TRADE please")
        assert len(resp.trades) == 1

    def test_no_side_effects_on_default(self):
        resp = mock_llm_response("what's in my portfolio?")
        assert resp.trades == []
        assert resp.watchlist_changes == []
