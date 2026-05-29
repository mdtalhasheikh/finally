"""Application configuration — single source of truth for tunable settings."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AppConfig:
    llm_primary_model: str = "openrouter/openai/gpt-oss-120b"
    llm_fallback_model: str = os.getenv("LLM_FALLBACK_MODEL", "openrouter/google/gemini-2.5-flash")
    llm_max_history_messages: int = 20
    portfolio_snapshot_interval_seconds: int = 30
    simulator_tick_interval_ms: int = 500
    massive_poll_interval_seconds: int = int(os.getenv("MASSIVE_POLL_INTERVAL_SECONDS", "15"))
    starting_cash: float = 10000.0
    db_path: str = os.getenv("DB_PATH", "/app/db/finally.db")


config = AppConfig()
