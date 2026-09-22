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


def test_transient_refusal_is_retried(monkeypatch):
    """Deepgram answers 503 on a busy moment; the Speaker has already confirmed."""
    attempts = []

    def handler(request: httpx.Request):
        attempts.append(request)
        if len(attempts) < 3:
            return httpx.Response(503, json={"err_msg": "Please try again later"})
        return httpx.Response(200, content=b"ID3fake-mp3", headers={"content-type": "audio/mpeg"})

    _mock_upstream(monkeypatch, handler)
    monkeypatch.setattr(tts, "RETRY_DELAYS", (0.0, 0.0))
    response = _client("secret").post("/api/tts/speak", json={"text": "Hi."})

    assert response.status_code == 200
    assert response.content == b"ID3fake-mp3"
    assert len(attempts) == 3


def test_retries_are_bounded(monkeypatch):
    attempts = []

    def handler(request: httpx.Request):
        attempts.append(request)
        return httpx.Response(503, json={"err_msg": "Please try again later"})

    _mock_upstream(monkeypatch, handler)
    monkeypatch.setattr(tts, "RETRY_DELAYS", (0.0, 0.0))
    response = _client("secret").post("/api/tts/speak", json={"text": "Hi."})

    assert response.status_code == 502
    assert "503" in response.json()["detail"]
    assert len(attempts) == len(tts.RETRY_DELAYS) + 1


def test_a_refusal_that_will_not_pass_is_not_retried(monkeypatch):
    """401 is an answer, not a hiccup: repeating it only repeats it."""
    attempts = []

    def handler(request: httpx.Request):
        attempts.append(request)
        return httpx.Response(401, json={"err_msg": "bad key"})

    _mock_upstream(monkeypatch, handler)
    response = _client("secret").post("/api/tts/speak", json={"text": "Hi."})

    assert response.status_code == 502
    assert len(attempts) == 1
