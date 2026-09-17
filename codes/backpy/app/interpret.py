"""Turn a raw transcript into the sentence the Speaker most likely meant.

This is a proposal, never a decision: the Speaker confirms, edits, or picks an
alternative before anything is spoken. So the model is asked for a best reading,
two distinct alternatives, and an honest confidence, and it is told not to add
anything the Speaker did not say.
"""

import asyncio
import logging
import random
import re
import time
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import BaseModel, Field

from app.settings import Settings, get_settings

log = logging.getLogger("synapvocal.interpret")

router = APIRouter(prefix="/api/bridge")

# A Speaker is waiting. One probe call to 3.8 took 38.7 s; better to fail visibly and let
# them retry or type than to hang.
CALL_TIMEOUT_MS = 12000
# Gemini on Vertex answers 429 when shared per-minute capacity is busy; it is transient.
# Solved in CineMeridian with exponential backoff and jitter. Done here in our own loop
# rather than the SDK's so every wait is logged (global rule 21). Kept short in the
# product because a person is waiting; the transcript is always shown meanwhile.
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
PRODUCT_BACKOFF = (1.0, 2.0)  # two retries, about 3 s of waiting at most


async def generate_with_backoff(client, model: str, contents: str, config, delays: tuple[float, ...]):
    """Returns (response, retries). Raises the last error once the delays are used up."""
    for retries in range(len(delays) + 1):
        try:
            return await client.aio.models.generate_content(model=model, contents=contents, config=config), retries
        except genai_errors.APIError as exc:
            if exc.code not in TRANSIENT_STATUS or retries == len(delays):
                raise
            wait = delays[retries] * (1 + random.uniform(0, 0.5))
            log.warning("gemini %s returned %s, retry %d of %d in %.1f s", model, exc.code, retries + 1, len(delays), wait)
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")

SYSTEM_PROMPT = """You help a person with dysarthria communicate. Their speech is slurred or slow, so speech recognition often mishears them.
You receive what speech recognition heard. Propose the English sentence the person most likely meant, so they can confirm it before it is spoken aloud to someone else.

Rules:
- Stay faithful. Fix mishearings, grammar and missing words, but never add facts, requests, names, or feelings the person did not express.
- Keep their voice and their point of view. Never change who is speaking or who is being talked about: keep I, you, he, she, we and they exactly as heard. Keep their register and length. Do not make it more polite or more formal than they were.
- If the transcript already reads as a clear sentence, return it unchanged apart from capitalisation and punctuation.
- Use the phrase book and the recent conversation only to resolve what the words probably were.
- alternatives: exactly two other plausible readings that differ in meaning from the interpretation, not rephrasings of it. If no other reading is plausible, return an empty list.
- confidence: how likely the interpretation is what they meant, from 0 to 1. Be honest; unclear input deserves a low number.
- Never use an em dash or en dash. Use commas or full stops.
- Plain text only. No quotation marks around sentences, no markdown."""


class InterpretRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)
    recent: list[str] = Field(default_factory=list, max_length=5)
    phrase_book: list[str] = Field(default_factory=list, max_length=100)


class ModelReading(BaseModel):
    interpretation: str
    alternatives: list[str]
    confidence: float = Field(ge=0, le=1)


class Interpretation(ModelReading):
    transcript: str
    unchanged: bool
    model: str
    latency_ms: int


DASHES = re.compile(r"\s*[\u2012\u2013\u2014\u2015]\s*")


def clean(text: str) -> str:
    """Global rule 38: no em or en dashes reach a person, even from a model."""
    text = DASHES.sub(", ", text).strip().strip('"').strip()
    return re.sub(r",\s*([.!?])$", r"\1", text)


def normalise(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9' ]+", " ", text.lower()).split())


@lru_cache
def get_client(project: str, location: str, credentials_path: str) -> genai.Client:
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(
        credentials_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    return genai.Client(
        vertexai=True,
        project=project,
        location=location,
        credentials=credentials,
        http_options=types.HttpOptions(timeout=CALL_TIMEOUT_MS),
    )


def build_prompt(request: InterpretRequest) -> str:
    parts = [f"Speech recognition heard: {request.transcript}"]
    if request.recent:
        parts.append("Recent sentences the person confirmed, oldest first:\n" + "\n".join(f"- {s}" for s in request.recent))
    if request.phrase_book:
        parts.append("Phrase book (names and words this person uses): " + ", ".join(request.phrase_book))
    return "\n\n".join(parts)


async def call_model(client: genai.Client, model: str, prompt: str) -> ModelReading:
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ModelReading,
        # temperature is ignored by Gemini 3.7 (CineMeridian finding, 2 Sep 2026); consistency
        # comes from thinking_level and response_schema, so it is not set.
        # Gemini 3.7 Flash thinks by default (446 to 750 thought tokens, median 6.7 s in a
        # 3-call probe on 17 Sep 2026). LOW cut that to 264 to 351 tokens, median 4.2 s.
        # MINIMAL is refused for 3.7, and thinking_budget=0 is ignored (still ~300 tokens).
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    response, retries = await generate_with_backoff(client, model, prompt, config, PRODUCT_BACKOFF)
    if retries:
        log.info("gemini %s succeeded after %d retries", model, retries)
    return ModelReading.model_validate_json(response.text)


@router.post("/interpret", response_model=Interpretation)
async def interpret(request: InterpretRequest, settings: Settings = Depends(get_settings)) -> Interpretation:
    if not settings.gemini_configured:
        log.error("interpret requested but Google credentials are missing: %r", settings.google_application_credentials)
        raise HTTPException(status_code=503, detail="Interpretation is not configured")

    client = get_client(settings.google_cloud_project, settings.google_cloud_location, settings.google_application_credentials)
    started = time.perf_counter()
    try:
        reading = await call_model(client, settings.gemini_model, build_prompt(request))
    except genai_errors.APIError as exc:
        log.error("gemini %s failed with %s: %s", settings.gemini_model, exc.code, str(exc)[:300])
        raise HTTPException(status_code=502, detail=f"Interpretation service refused the request ({exc.code})") from exc
    except ValueError as exc:
        log.error("gemini %s returned unparseable output: %s", settings.gemini_model, exc)
        raise HTTPException(status_code=502, detail="Interpretation service returned an unreadable answer") from exc
    except Exception as exc:
        log.error("gemini %s call failed: %r", settings.gemini_model, exc)
        raise HTTPException(status_code=502, detail="Interpretation service unreachable") from exc
    latency_ms = round((time.perf_counter() - started) * 1000)

    interpretation = clean(reading.interpretation)
    alternatives = []
    for alternative in (clean(a) for a in reading.alternatives):
        if alternative and normalise(alternative) != normalise(interpretation) and alternative not in alternatives:
            alternatives.append(alternative)

    log.info("interpret model=%s latency_ms=%d confidence=%.2f", settings.gemini_model, latency_ms, reading.confidence)
    return Interpretation(
        transcript=request.transcript,
        interpretation=interpretation,
        alternatives=alternatives[:2],
        confidence=reading.confidence,
        unchanged=normalise(interpretation) == normalise(request.transcript),
        model=settings.gemini_model,
        latency_ms=latency_ms,
    )
