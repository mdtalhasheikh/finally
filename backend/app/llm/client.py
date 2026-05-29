"""LLM client — LiteLLM → OpenRouter (Cerebras inference).

Uses structured JSON output + pydantic validation. Falls back to
LLM_FALLBACK_MODEL if the primary model fails or returns invalid JSON.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import litellm
from pydantic import BaseModel, ValidationError, field_validator

from ..config import config, get_llm_fallback_model, get_openrouter_api_key

logger = logging.getLogger(__name__)

litellm.suppress_debug_info = True


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class TradeAction(BaseModel):
    ticker: str
    side: str
    quantity: float

    @field_validator("ticker")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("side")
    @classmethod
    def validate_side(cls, v: str) -> str:
        if v not in ("buy", "sell"):
            raise ValueError("side must be 'buy' or 'sell'")
        return v

    @field_validator("quantity")
    @classmethod
    def validate_qty(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("quantity must be positive")
        return v


class WatchlistAction(BaseModel):
    ticker: str
    action: str

    @field_validator("ticker")
    @classmethod
    def normalize(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        if v not in ("add", "remove"):
            raise ValueError("action must be 'add' or 'remove'")
        return v


class ChatResponse(BaseModel):
    message: str
    trades: list[TradeAction] = []
    watchlist_changes: list[WatchlistAction] = []


# JSON schema for LLM structured output
_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "message": {"type": "string"},
        "trades": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "side": {"type": "string", "enum": ["buy", "sell"]},
                    "quantity": {"type": "number"},
                },
                "required": ["ticker", "side", "quantity"],
            },
        },
        "watchlist_changes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string"},
                    "action": {"type": "string", "enum": ["add", "remove"]},
                },
                "required": ["ticker", "action"],
            },
        },
    },
    "required": ["message"],
}

_SYSTEM_PROMPT = """You are FinAlly, an AI trading assistant for a simulated investment platform.
The user has a virtual portfolio with real-time simulated stock prices.

Your role:
- Analyze the user's portfolio composition, risk concentration, and P&L
- Suggest and execute trades when asked (or when the user agrees to your suggestion)
- Modify the watchlist ONLY when the user explicitly asks you to add/remove a ticker
- Be concise, data-driven, and helpful
- Always respond with valid JSON matching the required schema

CRITICAL: You must ALWAYS respond with valid JSON in this exact format:
{
  "message": "Your conversational response",
  "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
  "watchlist_changes": [{"ticker": "PYPL", "action": "add"}]
}

The "trades" and "watchlist_changes" arrays should be empty [] if no actions are needed.
Do not include trades or watchlist changes unless the user explicitly asks for them."""


def _build_portfolio_context(portfolio: dict, watchlist: list[dict]) -> str:
    cash = portfolio.get("cash_balance", 0)
    total = portfolio.get("total_value", 0)
    positions = portfolio.get("positions", [])

    lines = [
        f"PORTFOLIO SUMMARY:",
        f"  Cash: ${cash:,.2f}",
        f"  Total Value: ${total:,.2f}",
        f"  Unrealized P&L: ${portfolio.get('total_unrealized_pnl', 0):,.2f}",
        "",
    ]

    if positions:
        lines.append("CURRENT POSITIONS:")
        for pos in positions:
            pnl = pos.get("unrealized_pnl", 0)
            pnl_pct = pos.get("unrealized_pnl_pct", 0)
            lines.append(
                f"  {pos['ticker']}: {pos['quantity']} shares @ "
                f"${pos['avg_cost']:.2f} avg, "
                f"current ${pos.get('current_price', 0):.2f}, "
                f"P&L ${pnl:+.2f} ({pnl_pct:+.2f}%)"
            )
    else:
        lines.append("No open positions.")

    lines.append("")
    lines.append("WATCHLIST PRICES:")
    for item in watchlist:
        price = item.get("current_price")
        chg = item.get("daily_change_pct", 0)
        if price is not None:
            lines.append(f"  {item['ticker']}: ${price:.2f} ({chg:+.2f}% today)")

    return "\n".join(lines)


async def call_llm(
    user_message: str,
    history: list[dict],
    portfolio: dict,
    watchlist: list[dict],
) -> ChatResponse:
    """Call the LLM and return a validated ChatResponse.

    Tries primary model first, then falls back to LLM_FALLBACK_MODEL on failure.
    Raises RuntimeError if both models fail.
    """
    api_key = get_openrouter_api_key()
    portfolio_context = _build_portfolio_context(portfolio, watchlist)

    system_message = f"{_SYSTEM_PROMPT}\n\nCURRENT PORTFOLIO STATE:\n{portfolio_context}"

    messages: list[dict[str, str]] = [{"role": "system", "content": system_message}]

    for msg in history:
        role = msg["role"]
        content = msg["content"]
        if role in ("user", "assistant"):
            messages.append({"role": role, "content": content})

    messages.append({"role": "user", "content": user_message})

    primary = config.LLM_PRIMARY_MODEL
    fallback = get_llm_fallback_model()

    for attempt, model in enumerate([(primary, True), (fallback, False)]):
        model_name, is_primary = model
        try:
            response = await _call_model(model_name, messages, api_key)
            return response
        except Exception as exc:
            label = "primary" if is_primary else "fallback"
            logger.error("LLM %s model %s failed: %s", label, model_name, exc)
            if not is_primary:
                raise RuntimeError(f"Both LLM models failed. Last error: {exc}") from exc

    raise RuntimeError("LLM call failed unexpectedly")


async def _call_model(model: str, messages: list[dict], api_key: str) -> ChatResponse:
    """Call a specific model and parse the structured response."""
    import asyncio

    def _sync_call() -> str:
        resp = litellm.completion(
            model=model,
            messages=messages,
            api_key=api_key,
            response_format={"type": "json_object"},
            temperature=0.7,
            max_tokens=1000,
            extra_headers={
                "HTTP-Referer": "https://finally.app",
                "X-Title": "FinAlly AI Trading Assistant",
            },
        )
        return resp.choices[0].message.content or ""

    content = await asyncio.to_thread(_sync_call)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM returned non-JSON content: {content[:200]}") from exc

    try:
        return ChatResponse.model_validate(data)
    except ValidationError as exc:
        raise ValueError(f"LLM response failed validation: {exc}") from exc
