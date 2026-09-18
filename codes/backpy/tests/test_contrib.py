import asyncio
import io
import json
import wave

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event

from app.contrib import api
from app.contrib.db import Base, get_engine
from app.main import app
from app.settings import Settings, get_settings

TOKEN = "test-internal-token"


def wav(ms: int, rate: int = 16000, channels: int = 1) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(b"\x00\x00" * channels * (rate * ms // 1000))
    return buffer.getvalue()


META = {
    "heard_text": "she is nearly ninety three",
    "confirmed_text": "She is nearly ninety-three.",
    "label_source": "suggestion",
    "exact": True,
    "stt_model": "universal-3-5-pro",
    "interpret_model": "gemini-3.7-flash",
}


@pytest.fixture
def env(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"
    engine = get_engine(url)

    @event.listens_for(engine.sync_engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    async def create():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create())
    storage_dir = tmp_path / "audio"
    settings = Settings(
        database_url=url,
        internal_api_token=TOKEN,
        storage_backend="local",
        storage_local_dir=str(storage_dir),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    yield TestClient(app), storage_dir
    app.dependency_overrides.clear()


def sign_in(client: TestClient, sub: str = "google-1") -> dict:
    response = client.post(
        "/api/users/sync",
        json={"google_sub": sub, "email": f"{sub}@example.com", "name": "Test"},
        headers={"X-Internal-Token": TOKEN},
    )
    assert response.status_code == 200
    body = response.json()
    body["headers"] = {"X-Internal-Token": TOKEN, "X-User-Id": body["id"]}
    return body


def consent(client: TestClient, headers: dict) -> dict:
    body = {"version": api.CONSENT_VERSION, "adult_confirmed": True, "agreed": True}
    return client.post("/api/me/consent", json=body, headers=headers).json()


def upload(client: TestClient, headers: dict, audio: bytes, meta: dict = META):
    return client.post(
        "/api/contributions",
        files={"audio": ("sentence.wav", audio, "audio/wav")},
        data={"meta": json.dumps(meta)},
        headers=headers,
    )


def test_off_until_configured():
    app.dependency_overrides[get_settings] = lambda: Settings()
    response = TestClient(app).post("/api/users/sync", json={"google_sub": "x", "email": "a@b.c"})
    app.dependency_overrides.clear()
    assert response.status_code == 503


def test_wrong_internal_token_refused(env):
    client, _ = env
    response = client.post("/api/users/sync", json={"google_sub": "x", "email": "a@b.c"}, headers={"X-Internal-Token": "nope"})
    assert response.status_code == 401


def test_sign_in_twice_is_one_user(env):
    client, _ = env
    assert sign_in(client)["id"] == sign_in(client)["id"]


def test_contribution_needs_consent(env):
    client, _ = env
    user = sign_in(client)
    assert upload(client, user["headers"], wav(1500)).status_code == 403


def test_consent_for_an_old_text_is_refused(env):
    client, _ = env
    user = sign_in(client)
    body = {"version": "2020-01-01", "adult_confirmed": True, "agreed": True}
    assert client.post("/api/me/consent", json=body, headers=user["headers"]).status_code == 409


def test_contribute_list_and_delete(env):
    client, storage_dir = env
    user = sign_in(client)
    assert consent(client, user["headers"])["consent"]["version"] == api.CONSENT_VERSION

    saved = upload(client, user["headers"], wav(1500))
    assert saved.status_code == 201
    assert saved.json()["duration_ms"] == 1500
    assert len(list(storage_dir.rglob("*.wav"))) == 1

    listed = client.get("/api/contributions", headers=user["headers"]).json()
    assert [c["confirmed_text"] for c in listed] == ["She is nearly ninety-three."]

    assert client.delete(f"/api/contributions/{listed[0]['id']}", headers=user["headers"]).status_code == 204
    assert list(storage_dir.rglob("*.wav")) == []


def test_someone_else_cannot_delete_a_contribution(env):
    client, _ = env
    owner, other = sign_in(client, "owner"), sign_in(client, "other")
    consent(client, owner["headers"])
    contribution = upload(client, owner["headers"], wav(1000)).json()
    assert client.delete(f"/api/contributions/{contribution['id']}", headers=other["headers"]).status_code == 404


@pytest.mark.parametrize(
    ("audio", "status"),
    [(wav(1000, rate=44100), 422), (wav(1000, channels=2), 422), (wav(100), 422), (b"not audio", 422)],
    ids=["44k", "stereo", "too-short", "not-wav"],
)
def test_bad_recordings_refused(env, audio, status):
    client, storage_dir = env
    user = sign_in(client)
    consent(client, user["headers"])
    assert upload(client, user["headers"], audio).status_code == status
    assert list(storage_dir.rglob("*.wav")) == []


def test_withdraw_with_deletion_stops_contributions(env):
    client, storage_dir = env
    user = sign_in(client)
    consent(client, user["headers"])
    upload(client, user["headers"], wav(1000))
    me = client.post("/api/me/consent/withdraw", json={"delete_contributions": True}, headers=user["headers"]).json()
    assert me["consent"] is None and me["contributions"] == 0
    assert list(storage_dir.rglob("*.wav")) == []
    assert upload(client, user["headers"], wav(1000)).status_code == 403


def test_delete_account_removes_everything(env):
    client, storage_dir = env
    user = sign_in(client)
    consent(client, user["headers"])
    upload(client, user["headers"], wav(1000))
    assert client.delete("/api/me", headers=user["headers"]).status_code == 204
    assert list(storage_dir.rglob("*.wav")) == []
    assert client.get("/api/me", headers=user["headers"]).status_code == 401


def test_only_the_contributor_can_hear_a_recording(env):
    client, _ = env
    owner, other = sign_in(client, "owner"), sign_in(client, "other")
    consent(client, owner["headers"])
    audio = wav(1200)
    contribution = upload(client, owner["headers"], audio).json()
    heard = client.get(f"/api/contributions/{contribution['id']}/audio", headers=owner["headers"])
    assert heard.status_code == 200 and heard.content == audio and heard.headers["content-type"] == "audio/wav"
    assert client.get(f"/api/contributions/{contribution['id']}/audio", headers=other["headers"]).status_code == 404
