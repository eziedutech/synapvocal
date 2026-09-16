"""Temporary AssemblyAI streaming tokens for the browser.

The browser streams audio straight to AssemblyAI (one network hop fewer), so it
needs a token. The permanent key stays here. The connection settings live here
too, so the product and the benchmark scripts use the same configuration.
"""

import logging
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.settings import Settings, get_settings

log = logging.getLogger("synapvocal.stt")

router = APIRouter(prefix="/api/stt")

TOKEN_URL = "https://streaming.assemblyai.com/v3/token"
WS_URL = "wss://streaming.assemblyai.com/v3/ws"
TOKEN_TTL_SECONDS = 60
MAX_SESSION_SECONDS = 1800

# Dysarthric speech has longer pauses inside a sentence than typical speech, so
# turn detection starts from the "patient" end of AssemblyAI's presets and goes
# further. These numbers are a starting assumption, not a measured optimum. The
# Speaker can also end a turn explicitly (ForceEndpoint), so a long silence
# window costs waiting time, not correctness.
STREAM_PARAMS = {
    "speech_model": "universal-3-5-pro",
    "sample_rate": 16000,
    "encoding": "pcm_s16le",
    "min_turn_silence": 400,
    "max_turn_silence": 3000,
    "inactivity_timeout": 120,
}


class SttToken(BaseModel):
    token: str
    expires_in_seconds: int
    # Full websocket URL without the token; the client appends &token=...
    ws_url: str
    sample_rate: int


@router.post("/token", response_model=SttToken)
async def create_token(settings: Settings = Depends(get_settings)) -> SttToken:
    if not settings.assemblyai_api_key:
        log.error("token requested but ASSEMBLYAI_API_KEY is not set")
        raise HTTPException(status_code=503, detail="Speech recognition is not configured")

    params = {"expires_in_seconds": TOKEN_TTL_SECONDS, "max_session_duration_seconds": MAX_SESSION_SECONDS}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                TOKEN_URL, params=params, headers={"Authorization": settings.assemblyai_api_key}
            )
    except httpx.HTTPError as exc:
        log.error("token request failed: %r", exc)
        raise HTTPException(status_code=502, detail="Speech recognition service unreachable") from exc

    if response.status_code != 200:
        # Body can explain the refusal (bad key, no balance); it never contains our key.
        log.error("token request returned %s: %s", response.status_code, response.text[:300])
        raise HTTPException(status_code=502, detail=f"Speech recognition refused the token request ({response.status_code})")

    token = response.json().get("token")
    if not token:
        log.error("token response had no token field: keys=%s", list(response.json().keys()))
        raise HTTPException(status_code=502, detail="Speech recognition returned no token")

    return SttToken(
        token=token,
        expires_in_seconds=TOKEN_TTL_SECONDS,
        ws_url=f"{WS_URL}?{urlencode(STREAM_PARAMS)}",
        sample_rate=STREAM_PARAMS["sample_rate"],
    )
