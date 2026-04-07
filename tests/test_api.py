"""Tests for the FastAPI endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create a TestClient with mocked startup (no real vector store needed)."""
    with patch("src.api.load_chunks", return_value=[]):
        from src.api import app

        with TestClient(app) as c:
            yield c


def test_healthz_returns_status(client: TestClient):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in ("ok", "degraded")
    assert "chunks_loaded" in body
    # With empty mock chunks, should be degraded
    assert body["status"] == "degraded"
    assert body["chunks_loaded"] == 0


def test_ask_returns_response(client: TestClient):
    fake_response = {
        "answer": "Test answer.",
        "citations": [{"text": "cited text", "source": "TEST_10K_2024-01-01_full.txt"}],
        "confidence": "high",
        "refusal_reason": None,
    }
    with patch("src.api.ask", return_value=fake_response):
        resp = client.post("/v1/ask", json={"question": "What is test?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["answer"] == "Test answer."
    assert len(body["citations"]) == 1
    assert body["confidence"] == "high"


def test_ask_missing_question_returns_422(client: TestClient):
    resp = client.post("/v1/ask", json={})
    assert resp.status_code == 422


def test_telemetry_endpoint(client: TestClient):
    resp = client.get("/v1/telemetry")
    assert resp.status_code == 200
    body = resp.json()
    assert "calls" in body
    assert isinstance(body["calls"], list)
