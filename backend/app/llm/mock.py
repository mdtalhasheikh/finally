"""Mock LLM service for testing and development (LLM_MOCK=true)."""

from __future__ import annotations

from app.llm.models import LLMResponse, TradeAction


class MockLLMService:
    async def chat(
        self,
        user_message: str,
        portfolio_context: dict,
        history: list[dict],
    ) -> LLMResponse:
        if "mock-trade" in user_message.lower():
            return LLMResponse(
                message="Mock response: buying 1 share of AAPL.",
                trades=[TradeAction(ticker="AAPL", side="buy", quantity=1)],
                watchlist_changes=[],
            )
        return LLMResponse(
            message="Mock response: I'm here to help. Tell me what you'd like to do.",
            trades=[],
            watchlist_changes=[],
        )
