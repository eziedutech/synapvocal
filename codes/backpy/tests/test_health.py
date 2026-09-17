from fastapi.testclient import TestClient

from app.main import app
from app.settings import Settings, get_settings


def test_health_reports_sha_and_hides_keys():
    app.dependency_overrides[get_settings] = lambda: Settings(
        git_sha="abc1234", assemblyai_api_key="secret-value", deepgram_api_key=""
    )
    try:
        response = TestClient(app).get("/api/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["git_sha"] == "abc1234"
    assert body["configured"] == {"assemblyai": True, "deepgram": False, "gemini": False}
    assert "secret-value" not in response.text
