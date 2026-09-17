from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "production"] = "local"
    git_sha: str = "dev"

    assemblyai_api_key: str = ""
    deepgram_api_key: str = ""

    # Vertex AI. The GCP project is shared with CineMeridian because billing is only
    # active there; SynapVocal authenticates with its own service account.
    google_cloud_project: str = "cinemeridian"
    google_cloud_location: str = "global"
    # Decided by Zia on 17 Sep 2026: Flash, not Flash-Lite. 3.7 rather than 3.8 because
    # 3.8 hit 429 and one 38.7 s call in probing. Flash-Lite was faster (~1.2 s) but not chosen.
    gemini_model: str = "gemini-3.7-flash"
    google_application_credentials: str = ""

    @property
    def gemini_configured(self) -> bool:
        path = self.google_application_credentials
        return bool(path) and Path(path).is_file()


@lru_cache
def get_settings() -> Settings:
    return Settings()
