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
    assert body["configured"] == {"assemblyai": True, "deepgram": False, "gemini": False, "contributions": False}
    assert "secret-value" not in response.text


def test_database_url_gets_the_async_driver():
    from app.settings import Settings

    assert Settings(database_url="postgres://u:p@h:5432/d").database_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert Settings(database_url=' "postgresql://u:p@h/d" ').database_url == "postgresql+asyncpg://u:p@h/d"
