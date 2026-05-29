"""Tests for GET /api/health."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routes.health import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_health_returns_200(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
