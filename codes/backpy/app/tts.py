"""Speak a confirmed sentence aloud with Deepgram Aura-2.

Audio is streamed straight through as it arrives, so playback can start before the
whole file exists. The voice is limited to an allowlist: the browser picks from
these, it never passes an arbitrary model name to Deepgram.
"""

import logging
import re
import time
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.settings import Settings, get_settings

log = logging.getLogger("synapvocal.tts")

router = APIRouter(prefix="/api/tts")

SPEAK_URL = "https://api.deepgram.com/v1/speak"
# Deepgram's featured Aura-2 English voices (docs, 17 Sep 2026).
VOICES = {
    "aura-2-thalia-en": "Thalia, feminine, clear",
    "aura-2-helena-en": "Helena, feminine, caring",
    "aura-2-andromeda-en": "Andromeda, feminine, casual",
    "aura-2-arcas-en": "Arcas, masculine, natural",
    "aura-2-apollo-en": "Apollo, masculine, confident",
    "aura-2-aries-en": "Aries, masculine, warm",
}
DEFAULT_VOICE = "aura-2-thalia-en"
DASHES = re.compile(r"\s*[‒–—―]\s*")


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    voice: str = DEFAULT_VOICE


class Voice(BaseModel):
    id: str
    label: str


@router.get("/voices", response_model=list[Voice])
def voices() -> list[Voice]:
    return [Voice(id=voice_id, label=label) for voice_id, label in VOICES.items()]


@router.post("/speak")
async def speak(request: SpeakRequest, settings: Settings = Depends(get_settings)) -> StreamingResponse:
    if not settings.deepgram_api_key:
        log.error("speak requested but DEEPGRAM_API_KEY is not set")
        raise HTTPException(status_code=503, detail="Voice output is not configured")
    if request.voice not in VOICES:
        raise HTTPException(status_code=422, detail="Unknown voice")

    text = DASHES.sub(", ", request.text).strip()
    client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
    started = time.perf_counter()
    try:
        upstream_request = client.build_request(
            "POST",
            SPEAK_URL,
            params={"model": request.voice, "encoding": "mp3"},
            headers={"Authorization": f"Token {settings.deepgram_api_key}"},
            json={"text": text},
        )
        upstream = await client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        log.error("deepgram request failed: %r", exc)
        raise HTTPException(status_code=502, detail="Voice output service unreachable") from exc

    if upstream.status_code != 200:
        body = (await upstream.aread()).decode(errors="replace")[:300]
        await upstream.aclose()
        await client.aclose()
        log.error("deepgram returned %s: %s", upstream.status_code, body)
        raise HTTPException(status_code=502, detail=f"Voice output service refused the request ({upstream.status_code})")

    async def relay() -> AsyncIterator[bytes]:
        first = True
        size = 0
        try:
            async for chunk in upstream.aiter_bytes():
                if first:
                    log.info("tts first byte after %d ms (voice=%s, chars=%d)", (time.perf_counter() - started) * 1000, request.voice, len(text))
                    first = False
                size += len(chunk)
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()
            log.info("tts done after %d ms, %d bytes", (time.perf_counter() - started) * 1000, size)

    return StreamingResponse(relay(), media_type="audio/mpeg", headers={"Cache-Control": "no-store"})
