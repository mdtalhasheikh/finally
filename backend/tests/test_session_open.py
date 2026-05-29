"""Tests for session_open extension to the market data subsystem."""

from __future__ import annotations

import pytest

from app.market.cache import PriceCache
from app.market.models import PriceUpdate


class TestPriceUpdateSessionOpen:
    def test_default_session_open_is_zero(self):
        u = PriceUpdate(ticker="AAPL", price=190.0, previous_price=189.0)
        assert u.session_open == 0.0

    def test_daily_change_pct_zero_when_session_open_zero(self):
        u = PriceUpdate(ticker="AAPL", price=190.0, previous_price=189.0, session_open=0.0)
        assert u.daily_change_pct == 0.0

    def test_daily_change_pct_positive(self):
        u = PriceUpdate(ticker="AAPL", price=200.0, previous_price=195.0, session_open=190.0)
        expected = (200.0 - 190.0) / 190.0 * 100
        assert pytest.approx(u.daily_change_pct, abs=0.001) == expected

    def test_daily_change_pct_negative(self):
        u = PriceUpdate(ticker="AAPL", price=180.0, previous_price=185.0, session_open=190.0)
        assert u.daily_change_pct < 0

    def test_to_dict_includes_session_open(self):
        u = PriceUpdate(ticker="AAPL", price=190.0, previous_price=189.0, session_open=185.0)
        d = u.to_dict()
        assert "session_open" in d
        assert d["session_open"] == 185.0
        assert "daily_change_pct" in d


class TestPriceCacheSessionOpen:
    def test_first_update_captures_session_open(self):
        cache = PriceCache()
        update = cache.update("AAPL", 190.0)
        assert update.session_open == 190.0

    def test_subsequent_updates_hold_session_open(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        update2 = cache.update("AAPL", 200.0)
        assert update2.session_open == 190.0  # held from first observation

    def test_provided_session_open_overrides(self):
        cache = PriceCache()
        update = cache.update("AAPL", 190.0, session_open=185.0)
        assert update.session_open == 185.0

    def test_provided_session_open_persists(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0, session_open=185.0)
        update2 = cache.update("AAPL", 195.0)  # no new session_open
        assert update2.session_open == 185.0

    def test_remove_clears_session_open(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.remove("AAPL")
        # Re-adding should capture a new session_open
        update = cache.update("AAPL", 200.0)
        assert update.session_open == 200.0

    def test_different_tickers_independent_session_opens(self):
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("GOOGL", 175.0)
        cache.update("AAPL", 200.0)

        aapl = cache.get("AAPL")
        googl = cache.get("GOOGL")
        assert aapl.session_open == 190.0
        assert googl.session_open == 175.0

    def test_session_open_rounded_to_2dp(self):
        cache = PriceCache()
        update = cache.update("AAPL", 190.12345)
        assert update.session_open == round(190.12345, 2)
