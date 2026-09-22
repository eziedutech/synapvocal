"""Speak a confirmed sentence aloud with Deepgram Aura-2.

Audio is streamed straight through as it arrives, so playback can start before the
whole file exists. The voice is limited to an allowlist: the browser picks from
these, it never passes an arbitrary model name to Deepgram.
"""

import asyncio
import logging
import random
import re
import time
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.interpret import TRANSIENT_STATUS
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
# Deepgram documents 503 as the server not being ready, "please try again later".
# Measured against production on 22 Sep 2026: 5 of 8 calls came back 200 while the same
# key called directly from elsewhere succeeded 4 of 4, so the hiccup is real and it lands
# on the last step of the product, after the Speaker has already confirmed the sentence.
# The delays are short on purpose: someone is waiting to be heard, so a late voice beats
# a refusal, but only by a little.
RETRY_DELAYS = (0.4, 1.2)
DASHES = re.compile(r"\s*[\u2012\u2013\u2014\u2015]\s*")


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    voice: str = DEFAULT_VOICE


class Voice(BaseModel):
    id: str
    label: str


@router.get("/voices", response_model=list[Voice])
def voices() -> list[Voice]:
    return [Voice(id=voice_id, label=label) for voice_id, label in VOICES.items()]


async def _open_stream(client: httpx.AsyncClient, voice: str, text: str, key: str) -> httpx.Response:
    """A streaming Deepgram response, retried while the refusal is a transient one.

    Every wait is logged, and the number of them is bounded, so a slow answer can
    never be mistaken for a hung one.
    """
    for retries in range(len(RETRY_DELAYS) + 1):
        last = retries == len(RETRY_DELAYS)
        try:
            upstream_request = client.build_request(
                "POST",
                SPEAK_URL,
                params={"model": voice, "encoding": "mp3"},
                headers={"Authorization": f"Token {key}"},
                json={"text": text},
            )
            upstream = await client.send(upstream_request, stream=True)
        except httpx.HTTPError as exc:
            if last or not isinstance(exc, httpx.NetworkError):
                log.error("deepgram request failed: %r", exc)
                raise HTTPException(status_code=502, detail="Voice output service unreachable") from exc
            reason = type(exc).__name__
        else:
            if upstream.status_code == 200:
                if retries:
                    log.info("deepgram speak succeeded on attempt %d", retries + 1)
                return upstream
            body = (await upstream.aread()).decode(errors="replace")[:300]
            await upstream.aclose()
            if last or upstream.status_code not in TRANSIENT_STATUS:
                log.error("deepgram returned %s: %s", upstream.status_code, body)
                raise HTTPException(
                    status_code=502,
                    detail=f"Voice output service refused the request ({upstream.status_code})",
                )
            reason = f"{upstream.status_code} {body[:120]}"
        wait = RETRY_DELAYS[retries] * (1 + random.uniform(0, 0.5))
        log.warning("deepgram speak failed with %s, retry %d of %d in %.1f s", reason, retries + 1, len(RETRY_DELAYS), wait)
        await asyncio.sleep(wait)
    raise AssertionError("unreachable")


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
        upstream = await _open_stream(client, request.voice, text, settings.deepgram_api_key)
    except BaseException:
        await client.aclose()
        raise

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
