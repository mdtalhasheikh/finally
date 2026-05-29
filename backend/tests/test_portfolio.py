"""Tests for portfolio business logic and API routes."""

from __future__ import annotations

import pytest

from app.market.cache import PriceCache
from app.routes.portfolio import _build_portfolio


@pytest.fixture
def price_cache() -> PriceCache:
    cache = PriceCache()
    cache.update("AAPL", 190.0)
    cache.update("GOOGL", 175.0)
    return cache


class TestBuildPortfolio:
    def test_empty_positions(self, price_cache):
        result = _build_portfolio([], 10000.0, price_cache)
        assert result["cash_balance"] == 10000.0
        assert result["total_value"] == 10000.0
        assert result["total_unrealized_pnl"] == 0.0
        assert result["positions"] == []

    def test_single_position_profit(self, price_cache):
        positions = [{"ticker": "AAPL", "quantity": 10.0, "avg_cost": 180.0}]
        result = _build_portfolio(positions, 1000.0, price_cache)

        assert len(result["positions"]) == 1
        pos = result["positions"][0]
        assert pos["ticker"] == "AAPL"
        assert pos["quantity"] == 10.0
        assert pos["avg_cost"] == 180.0
        assert pos["current_price"] == 190.0
        assert pytest.approx(pos["unrealized_pnl"], abs=0.01) == 100.0  # (190-180)*10
        assert pos["unrealized_pnl_pct"] > 0

    def test_single_position_loss(self, price_cache):
        positions = [{"ticker": "AAPL", "quantity": 5.0, "avg_cost": 200.0}]
        result = _build_portfolio(positions, 0.0, price_cache)

        pos = result["positions"][0]
        assert pos["unrealized_pnl"] < 0
        assert pos["unrealized_pnl_pct"] < 0

    def test_total_value_calculation(self, price_cache):
        positions = [
            {"ticker": "AAPL", "quantity": 10.0, "avg_cost": 180.0},
            {"ticker": "GOOGL", "quantity": 5.0, "avg_cost": 160.0},
        ]
        cash = 2000.0
        result = _build_portfolio(positions, cash, price_cache)

        expected_value = cash + (190.0 * 10) + (175.0 * 5)
        assert pytest.approx(result["total_value"], abs=0.01) == expected_value

    def test_unknown_ticker_has_zero_price(self):
        cache = PriceCache()
        positions = [{"ticker": "UNKNOWN", "quantity": 10.0, "avg_cost": 100.0}]
        result = _build_portfolio(positions, 1000.0, cache)

        pos = result["positions"][0]
        assert pos["current_price"] == 0.0

    def test_session_open_daily_change(self):
        cache = PriceCache()
        # First update sets session_open
        cache.update("AAPL", 190.0)
        # Second update changes price but holds session_open
        cache.update("AAPL", 200.0)

        positions = [{"ticker": "AAPL", "quantity": 1.0, "avg_cost": 190.0}]
        result = _build_portfolio(positions, 0.0, cache)

        pos = result["positions"][0]
        assert pos["session_open"] == 190.0
        assert pos["current_price"] == 200.0
        assert pos["daily_change_pct"] > 0  # price went up from session_open

    def test_fractional_quantity_rounding(self, price_cache):
        positions = [{"ticker": "AAPL", "quantity": 1.123456789, "avg_cost": 190.0}]
        result = _build_portfolio(positions, 0.0, price_cache)
        pos = result["positions"][0]
        assert pos["quantity"] == round(1.123456789, 6)
