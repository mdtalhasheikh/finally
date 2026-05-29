"""Factory for creating the appropriate LLM service based on environment config."""

from __future__ import annotations

import os

from app.config import config
from app.llm.mock import MockLLMService
from app.llm.service import LLMService


def create_llm_service() -> LLMService | MockLLMService:
    if os.getenv("LLM_MOCK", "false").lower() == "true":
        return MockLLMService()
    return LLMService(
        primary_model=config.llm_primary_model,
        fallback_model=config.llm_fallback_model,
        max_history=config.llm_max_history_messages,
    )
