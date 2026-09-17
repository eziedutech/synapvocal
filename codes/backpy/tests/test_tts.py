import httpx
from fastapi.testclient import TestClient

from app import tts
from app.main import app
from app.settings import Settings, get_settings


def _client(key: str) -> TestClient:
    app.dependency_overrides[get_settings] = lambda: Settings(deepgram_api_key=key)
    return TestClient(app)


def _mock_upstream(monkeypatch, handler):
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    monkeypatch.setattr(tts.httpx, "AsyncClient", factory)


def teardown_function():
    app.dependency_overrides.clear()


def test_missing_key_is_503():
    assert _client("").post("/api/tts/speak", json={"text": "Hi."}).status_code == 503


def test_unknown_voice_is_rejected():
    assert _client("k").post("/api/tts/speak", json={"text": "Hi.", "voice": "evil-model"}).status_code == 422


def test_audio_streams_through_and_dashes_are_removed(monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = request.content.decode()
        seen["auth"] = request.headers["authorization"]
        seen["model"] = request.url.params["model"]
        return httpx.Response(200, content=b"ID3fake-mp3", headers={"content-type": "audio/mpeg"})

    _mock_upstream(monkeypatch, handler)
    response = _client("secret").post("/api/tts/speak", json={"text": "Wait \u2014 please."})

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"ID3fake-mp3"
    assert "\u2014" not in seen["body"] and "Wait, please." in seen["body"]
    assert seen["auth"] == "Token secret"
    assert seen["model"] == tts.DEFAULT_VOICE


def test_upstream_refusal_is_502(monkeypatch):
    _mock_upstream(monkeypatch, lambda request: httpx.Response(401, json={"err_msg": "bad key"}))
    response = _client("secret").post("/api/tts/speak", json={"text": "Hi."})
    assert response.status_code == 502
    assert "401" in response.json()["detail"]
