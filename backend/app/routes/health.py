"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health_check() -> dict:
    return {"status": "ok"}
