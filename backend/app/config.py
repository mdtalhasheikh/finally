"""Backend configuration — code-tunable knobs that don't belong in .env.

Secrets and infra-shaped settings (API keys, DB path, poll intervals) live
in environment variables. Everything here is a safe default that can be
overridden by editing this file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    # LLM settings
    LLM_PRIMARY_MODEL: str = "openrouter/openai/gpt-oss-120b"
    LLM_MAX_HISTORY_MESSAGES: int = 20

    # Portfolio snapshot background task cadence (seconds)
    PORTFOLIO_SNAPSHOT_INTERVAL_SECONDS: int = 30

    # Simulator update rate (milliseconds) — Massive mode uses MASSIVE_POLL_INTERVAL_SECONDS
    SIMULATOR_TICK_INTERVAL_MS: int = 500

    # Starting cash balance for the default user
    STARTING_CASH: float = 10000.0

    # Default watchlist tickers
    DEFAULT_TICKERS: list[str] = field(
        default_factory=lambda: [
            "AAPL", "GOOGL", "MSFT", "AMZN", "TSLA",
            "NVDA", "META", "JPM", "V", "NFLX",
        ]
    )


# Singleton — import this everywhere
config = Config()


def get_db_path() -> Path:
    """Return the SQLite database file path, configurable via DB_PATH env var."""
    raw = os.environ.get("DB_PATH", "/app/db/finally.db")
    p = Path(raw)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def get_openrouter_api_key() -> str:
    """Return the OpenRouter API key. Raises on missing key (unless LLM_MOCK=true)."""
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    mock = os.environ.get("LLM_MOCK", "false").lower() == "true"
    if not key and not mock:
        raise RuntimeError(
            "OPENROUTER_API_KEY is not set. "
            "Add it to .env or set LLM_MOCK=true for testing."
        )
    return key


def get_llm_fallback_model() -> str:
    return os.environ.get("LLM_FALLBACK_MODEL", "openrouter/google/gemini-2.5-flash")


def is_llm_mock() -> bool:
    return os.environ.get("LLM_MOCK", "false").lower() == "true"
