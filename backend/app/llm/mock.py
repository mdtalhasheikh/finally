"""Mock LLM responses for testing (LLM_MOCK=true).

Two deterministic fixtures:
- Default: a plain conversational reply, no trades or watchlist changes.
- Trade-trigger: triggered by "mock-trade" in the user message. Buys 1 share of AAPL.
"""

from __future__ import annotations

from .client import ChatResponse, TradeAction, WatchlistAction


def mock_llm_response(user_message: str) -> ChatResponse:
    """Return a deterministic ChatResponse based on a simple substring match."""
    if "mock-trade" in user_message.lower():
        return ChatResponse(
            message="Mock response: buying 1 share of AAPL.",
            trades=[TradeAction(ticker="AAPL", side="buy", quantity=1)],
            watchlist_changes=[],
        )
    return ChatResponse(
        message="Mock response: I'm here to help. Tell me what you'd like to do.",
        trades=[],
        watchlist_changes=[],
    )
