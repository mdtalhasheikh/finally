"""LLM service — calls OpenRouter/Cerebras via LiteLLM, retries on parse failure."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from litellm import completion

from app.llm.models import LLMResponse

logger = logging.getLogger(__name__)

_EXTRA_BODY: dict[str, Any] = {"provider": {"order": ["cerebras"]}}

_SYSTEM_PROMPT_TEMPLATE = """\
You are FinAlly, an AI trading assistant for a personal trading workstation.

Your responsibilities:
- Analyze portfolio composition, risk, and P&L
- Suggest and execute trades when the user requests them
- Manage the watchlist only when the user explicitly asks (do NOT implicitly add tickers)
- Always respond with valid structured JSON matching the required schema
- Be concise and data-driven; avoid filler text

Current portfolio context:
{portfolio_context}

Respond ONLY with valid JSON matching this schema:
{{
  "message": "<your reply to the user>",
  "trades": [
    {{"ticker": "<TICKER>", "side": "<buy|sell>", "quantity": <number>}}
  ],
  "watchlist_changes": [
    {{"ticker": "<TICKER>", "action": "<add|remove>"}}
  ]
}}
If there are no trades or watchlist changes, use empty lists.
"""


def _format_portfolio_context(portfolio_context: dict) -> str:
    """Render portfolio dict into a readable string for the system prompt."""
    lines = []
    cash = portfolio_context.get("cash", 0.0)
    total = portfolio_context.get("total_value", 0.0)
    lines.append(f"Cash: ${cash:,.2f}")
    lines.append(f"Total Value: ${total:,.2f}")

    positions = portfolio_context.get("positions", [])
    if positions:
        pos_parts = []
        for p in positions:
            ticker = p.get("ticker", "")
            qty = p.get("quantity", 0)
            avg = p.get("avg_cost", 0.0)
            current = p.get("current_price", avg)
            pnl_pct = ((current - avg) / avg * 100) if avg else 0.0
            sign = "+" if pnl_pct >= 0 else ""
            pos_parts.append(
                f"{ticker} x{qty} @ ${avg:.2f} avg, current ${current:.2f} ({sign}{pnl_pct:.2f}%)"
            )
        lines.append("Positions: " + ", ".join(pos_parts))
    else:
        lines.append("Positions: none")

    watchlist = portfolio_context.get("watchlist", [])
    if watchlist:
        lines.append("Watchlist: " + ", ".join(watchlist))
    else:
        lines.append("Watchlist: empty")

    return "\n".join(lines)


def _build_messages(
    user_message: str,
    portfolio_context: dict,
    history: list[dict],
) -> list[dict]:
    """Assemble the full messages list for the LLM call."""
    context_str = _format_portfolio_context(portfolio_context)
    system_content = _SYSTEM_PROMPT_TEMPLATE.format(portfolio_context=context_str)

    messages: list[dict] = [{"role": "system", "content": system_content}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_message})
    return messages


def _call_model(model: str, messages: list[dict]) -> str:
    """Blocking LiteLLM call; intended to run in a thread via asyncio.to_thread."""
    response = completion(
        model=model,
        messages=messages,
        response_format=LLMResponse,
        reasoning_effort="low",
        extra_body=_EXTRA_BODY,
    )
    return response.choices[0].message.content


async def _try_parse(model: str, messages: list[dict]) -> LLMResponse:
    """Call model and parse; raises ValueError on parse failure."""
    raw = await asyncio.to_thread(_call_model, model, messages)
    return LLMResponse.model_validate_json(raw)


class LLMService:
    def __init__(self, primary_model: str, fallback_model: str, max_history: int) -> None:
        self._primary = primary_model
        self._fallback = fallback_model
        self._max_history = max_history

    async def chat(
        self,
        user_message: str,
        portfolio_context: dict,
        history: list[dict],
    ) -> LLMResponse:
        """Call LLM, parse structured output. Retry once with same model, then try fallback."""
        messages = _build_messages(user_message, portfolio_context, history[-self._max_history :])

        # Attempt 1: primary model
        try:
            logger.info("LLM call: model=%s", self._primary)
            return await _try_parse(self._primary, messages)
        except Exception as exc:
            logger.warning("Primary model attempt 1 failed: %s", exc)

        # Attempt 2: primary model retry
        try:
            logger.info("LLM retry: model=%s", self._primary)
            return await _try_parse(self._primary, messages)
        except Exception as exc:
            logger.warning("Primary model attempt 2 failed: %s", exc)

        # Attempt 3: fallback model
        try:
            logger.info("LLM fallback: model=%s", self._fallback)
            return await _try_parse(self._fallback, messages)
        except Exception as exc:
            logger.error("Fallback model failed: %s", exc)
            raise RuntimeError(f"All LLM attempts failed. Last error: {exc}") from exc
