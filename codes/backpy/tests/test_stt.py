import httpx
from fastapi.testclient import TestClient

from app import stt
from app.main import app
from app.settings import Settings, get_settings


def _client(key: str) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: Settings(assemblyai_api_key=key)
    return TestClient(app)


def _mock_upstream(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(stt.httpx, "AsyncClient", factory)


def teardown_function():
    app.dependency_overrides.clear()


def test_missing_key_is_503():
    assert _client("").post("/api/stt/token").status_code == 503


def test_token_returned_with_ws_url_and_key_not_leaked(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers.get("authorization")
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"token": "temp-token"})

    _mock_upstream(monkeypatch, handler)
    response = _client("perm-key").post("/api/stt/token")

    assert response.status_code == 200
    body = response.json()
    assert body["token"] == "temp-token"
    assert body["ws_url"].startswith("wss://streaming.assemblyai.com/v3/ws?")
    assert "speech_model=universal-3-6-pro" in body["ws_url"]
    # Recognition turns ordinary words into profanity nobody said ("park" as "Fuck"),
    # and the Speaker would be the one offering to say it aloud.
    assert "filter_profanity=true" in body["ws_url"]
    assert "token=" not in body["ws_url"]
    assert "perm-key" not in response.text
    assert seen["auth"] == "perm-key"
    assert seen["params"]["expires_in_seconds"] == "60"


def test_upstream_refusal_is_502_with_status(monkeypatch):
    _mock_upstream(monkeypatch, lambda request: httpx.Response(401, json={"error": "bad key"}))
    response = _client("perm-key").post("/api/stt/token")
    assert response.status_code == 502
    assert "401" in response.json()["detail"]
