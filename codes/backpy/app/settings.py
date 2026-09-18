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
    # Used when gemini_model fails (Zia, 17 Sep 2026): 3.7 Flash answered 504 and 429 in
    # bursts during testing. Flash-Lite has its own capacity and was fast (p50 1.8 s) in
    # round C1; empty disables the fallback.
    gemini_fallback_model: str = "gemini-3.5-flash-lite"
    google_application_credentials: str = ""

    # Voluntary contributions (Zia, 18 Sep 2026). Everything below is off until set;
    # the Bridge itself never needs it.
    database_url: str = ""  # postgresql+asyncpg://user:password@host:5432/synapvocal
    # Shared with frontrouter, which alone talks to backpy and vouches for the signed-in user.
    internal_api_token: str = ""
    storage_backend: Literal["s3", "local"] = "s3"
    storage_local_dir: str = "/data/contributions"  # local development only
    # Zia, 18 Sep 2026: the bucket already used for fine-tuning, under its own prefix, so
    # contributed recordings sit next to the training data they are meant for.
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_prefix: str = "synapvocal/contributions/"

    @property
    def contributions_configured(self) -> bool:
        storage = bool(self.s3_bucket) if self.storage_backend == "s3" else bool(self.storage_local_dir)
        return bool(self.database_url and self.internal_api_token) and storage

    @property
    def gemini_configured(self) -> bool:
        path = self.google_application_credentials
        return bool(path) and Path(path).is_file()


@lru_cache
def get_settings() -> Settings:
    return Settings()
