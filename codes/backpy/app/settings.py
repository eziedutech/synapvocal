from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["local", "production"] = "local"
    git_sha: str = "dev"

    assemblyai_api_key: str = ""
    deepgram_api_key: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
