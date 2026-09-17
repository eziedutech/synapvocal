import logging
from typing import Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel

from app import interpret, stt, tts
from app.settings import Settings, get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="SynapVocal backpy", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.include_router(stt.router)
app.include_router(interpret.router)
app.include_router(tts.router)


class Configured(BaseModel):
    # Whether each key is present, never the key itself.
    assemblyai: bool
    deepgram: bool
    gemini: bool


class Health(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["backpy"] = "backpy"
    env: str
    git_sha: str
    configured: Configured


@app.get("/api/health", response_model=Health)
def health(settings: Settings = Depends(get_settings)) -> Health:
    return Health(
        env=settings.app_env,
        git_sha=settings.git_sha,
        configured=Configured(
            assemblyai=bool(settings.assemblyai_api_key),
            deepgram=bool(settings.deepgram_api_key),
            gemini=settings.gemini_configured,
        ),
    )
