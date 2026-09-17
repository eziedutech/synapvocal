from fastapi.testclient import TestClient

from app import interpret
from app.interpret import ModelReading, clean
from app.main import app
from app.settings import Settings, get_settings


def _client(tmp_path, configured=True) -> TestClient:
    key = tmp_path / "key.json"
    if configured:
        key.write_text("{}")
    app.dependency_overrides[get_settings] = lambda: Settings(google_application_credentials=str(key))
    return TestClient(app)


def _fake_model(monkeypatch, reading: ModelReading, seen: dict | None = None):
    monkeypatch.setattr(interpret, "get_client", lambda *args: object())

    async def fake_call(client, model, prompt):
        if seen is not None:
            seen["prompt"] = prompt
        return reading

    monkeypatch.setattr(interpret, "call_model", fake_call)


def teardown_function():
    app.dependency_overrides.clear()


def test_missing_credentials_is_503(tmp_path):
    response = _client(tmp_path, configured=False).post("/api/bridge/interpret", json={"transcript": "hello"})
    assert response.status_code == 503


def test_dashes_removed_and_duplicate_alternatives_dropped(tmp_path, monkeypatch):
    seen = {}
    _fake_model(
        monkeypatch,
        ModelReading(
            interpretation="I want to go home \u2014 now.",
            alternatives=["i want to go home, now", "I want a phone \u2013 now.", "I want a phone, now."],
            confidence=0.7,
        ),
        seen,
    )
    response = _client(tmp_path).post(
        "/api/bridge/interpret",
        json={"transcript": "i wan go hom now", "recent": ["Hi."], "phrase_book": ["Budi"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert "\u2014" not in response.text and "\u2013" not in response.text
    assert body["interpretation"] == "I want to go home, now."
    # The rephrasing of the interpretation is dropped, the dash variant is cleaned and deduplicated.
    assert body["alternatives"] == ["I want a phone, now."]
    assert body["unchanged"] is False
    assert "Budi" in seen["prompt"] and "Hi." in seen["prompt"]


def test_clean_transcript_is_marked_unchanged(tmp_path, monkeypatch):
    _fake_model(monkeypatch, ModelReading(interpretation="Up.", alternatives=[], confidence=0.9))
    body = _client(tmp_path).post("/api/bridge/interpret", json={"transcript": "up"}).json()
    assert body["unchanged"] is True


def test_clean_trailing_dash_before_stop():
    assert clean("Wait \u2014.") == "Wait."


class _FakeModels:
    def __init__(self, codes):
        self.codes = list(codes)
        self.calls = 0

    async def generate_content(self, **kwargs):
        from google.genai import errors

        self.calls += 1
        code = self.codes.pop(0)
        if code == 200:
            return "ok"
        raise errors.APIError(code, {"error": {"code": code, "message": "x", "status": "X"}})


class _FakeClient:
    def __init__(self, codes):
        self.aio = type("Aio", (), {})()
        self.aio.models = _FakeModels(codes)


def test_backoff_retries_transient_then_succeeds(monkeypatch):
    import asyncio

    async def no_sleep(_):
        return None

    monkeypatch.setattr(interpret.asyncio, "sleep", no_sleep)
    client = _FakeClient([429, 503, 200])
    response, retries = asyncio.run(interpret.generate_with_backoff(client, "m", "p", None, (1.0, 1.0)))
    assert (response, retries, client.aio.models.calls) == ("ok", 2, 3)


def test_backoff_does_not_retry_refusals(monkeypatch):
    import asyncio

    import pytest
    from google.genai import errors

    client = _FakeClient([404, 200])
    with pytest.raises(errors.APIError):
        asyncio.run(interpret.generate_with_backoff(client, "m", "p", None, (1.0, 1.0)))
    assert client.aio.models.calls == 1


def test_backoff_gives_up_after_delays(monkeypatch):
    import asyncio

    import pytest
    from google.genai import errors

    async def no_sleep(_):
        return None

    monkeypatch.setattr(interpret.asyncio, "sleep", no_sleep)
    client = _FakeClient([429, 429, 429, 200])
    with pytest.raises(errors.APIError):
        asyncio.run(interpret.generate_with_backoff(client, "m", "p", None, (1.0, 1.0)))
    assert client.aio.models.calls == 3
