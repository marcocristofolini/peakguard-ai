"""Autenticação API: modo local e modo token sem alteração de estado global."""
from fastapi.testclient import TestClient
from peakguard.api import app

client = TestClient(app)
TOKEN = "a" * 48


def test_default_local_allows_testclient(monkeypatch):
    monkeypatch.delenv("PEAKGUARD_AUTH_MODE", raising=False)
    monkeypatch.delenv("PEAKGUARD_API_TOKEN", raising=False)
    assert client.get("/scenarios").status_code == 200


def test_bearer_rejects_missing_and_wrong_credentials(monkeypatch):
    monkeypatch.setenv("PEAKGUARD_AUTH_MODE", "token")
    monkeypatch.setenv("PEAKGUARD_API_TOKEN", TOKEN)
    assert client.get("/scenarios").status_code == 401
    assert client.get("/docs").status_code == 401
    assert client.post("/comparisons", json={"scenario": "stable"}, headers={
        "Authorization": "Bearer wrong",
    }).status_code == 401
    assert client.get("/scenarios", headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401


def test_bearer_accepts_valid_token_for_api_and_docs(monkeypatch):
    monkeypatch.setenv("PEAKGUARD_AUTH_MODE", "token")
    monkeypatch.setenv("PEAKGUARD_API_TOKEN", TOKEN)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    assert client.get("/scenarios", headers=headers).status_code == 200
    assert client.get("/openapi.json", headers=headers).status_code == 200
    assert client.post("/comparisons", json={"scenario": "stable"}, headers=headers).status_code == 200


def test_token_mode_fails_closed_without_strong_secret(monkeypatch):
    monkeypatch.setenv("PEAKGUARD_AUTH_MODE", "token")
    monkeypatch.setenv("PEAKGUARD_API_TOKEN", "short")
    assert client.get("/scenarios").status_code == 503


def test_unknown_auth_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("PEAKGUARD_AUTH_MODE", "invalid")
    assert client.get("/scenarios").status_code == 503
