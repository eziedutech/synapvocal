"""Turn a raw transcript into the sentence the Speaker most likely meant.

This is a proposal, never a decision: the Speaker confirms, edits, or picks an
alternative before anything is spoken. So the model is asked for a best reading,
two distinct alternatives, and an honest confidence, and it is told not to add
anything the Speaker did not say.
"""

import asyncio
import base64
import binascii
import io
import logging
import random

import httpx
import re
import time
import wave
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
# rather than the SDK's so every wait is logged, never hidden. Kept short in the
# product because a person is waiting; the transcript is always shown meanwhile.
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
# A dropped connection (for example httpx.ReadError mid-response) is transient too; it
# stopped a benchmark run on 17 Sep 2026. Timeouts are not retried: they already cost
# the full CALL_TIMEOUT_MS and a person is waiting.
# The primary model gets one retry, then the fallback model gets one attempt. Worst case
# is about 12 + 1.5 + 12 + 12 = 38 s, inside the 45 s the web server waits.
PRIMARY_BACKOFF = (1.0,)
FALLBACK_BACKOFF = ()


async def generate_with_backoff(client, model: str, contents: str, config, delays: tuple[float, ...]):
    """Returns (response, retries). Raises the last error once the delays are used up."""
    for retries in range(len(delays) + 1):
        try:
            return await client.aio.models.generate_content(model=model, contents=contents, config=config), retries
        except (genai_errors.APIError, httpx.NetworkError) as exc:
            reason = exc.code if isinstance(exc, genai_errors.APIError) else type(exc).__name__
            transient = isinstance(exc, httpx.NetworkError) or exc.code in TRANSIENT_STATUS
            if not transient or retries == len(delays):
                raise
            wait = delays[retries] * (1 + random.uniform(0, 0.5))
            log.warning("gemini %s failed with %s, retry %d of %d in %.1f s", model, reason, retries + 1, len(delays), wait)
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")

# Prompt v1 (17 Sep 2026): measured in rounds C0 to C2. Kept for comparison runs.
SYSTEM_PROMPT_V1 = """You help a person whose speech is hard to understand communicate. This can be dysarthria or the speech of someone with Parkinson's disease, ALS, cerebral palsy, Down syndrome or a stroke. Their speech may be slurred, slow, strained or broken, so speech recognition often mishears them.
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

# Prompt v2 (18 Sep 2026): adds AssemblyAI's word confidences, keeps word forms, and
# allows three alternatives. Tuned on one half of the pilot and reported on the other.
SYSTEM_PROMPT_V2 = """You help a person whose speech is hard to understand communicate. This can be dysarthria or the speech of someone with Parkinson's disease, ALS, cerebral palsy, Down syndrome or a stroke. Their speech may be slurred, slow, strained or broken, so speech recognition often mishears them.
You receive what speech recognition heard. Propose the English sentence the person most likely meant, so they can confirm it before it is spoken aloud to someone else.

Rules:
- Stay faithful. Fix mishearings, grammar and missing words, but never add facts, requests, names, or feelings the person did not express.
- Keep their voice and their point of view. Never change who is speaking or who is being talked about: keep I, you, he, she, we and they exactly as heard. Keep their register and length. Do not make it more polite or more formal than they were.
- If the transcript already reads as a clear sentence, return it unchanged apart from capitalisation and punctuation.
- Use the phrase book and the recent conversation only to resolve what the words probably were.
- Keep each word's form as heard (tense, singular or plural, contractions) unless the audio clearly says otherwise. Do not correct grammar that already makes sense.
- When word confidences from speech recognition are given, low-confidence words are the likeliest to be misheard and high-confidence words are usually right.
- alternatives: up to three other plausible readings that differ in meaning from the interpretation, not rephrasings of it, most likely first. Prefer readings that change the words recognition was least sure of. If no other reading is plausible, return an empty list.
- confidence: how likely the interpretation is what they meant, from 0 to 1. Be honest; unclear input deserves a low number.
- Never use an em dash or en dash. Use commas or full stops.
- Plain text only. No quotation marks around sentences, no markdown."""

PROMPTS = {"v1": SYSTEM_PROMPT_V1, "v2": SYSTEM_PROMPT_V2}
# The product keeps v1 until v2 wins on the report half of the pilot. Word confidences
# are only sent to the model with a prompt that says how to use them.
PRODUCT_PROMPT = "v1"
SYSTEM_PROMPT = PROMPTS[PRODUCT_PROMPT]


# Measured on TORGO (17 Sep 2026, 681 dysarthric sentences): hearing the audio and seeing
# earlier heard/confirmed pairs from the same person lowered the suggestion WER from
# 0.337 (text only) to 0.231. Both come from the benchmark (round C2) unchanged.
AUDIO_ADDENDUM = """

You also receive the audio recording of what the person said. The transcript is only
speech recognition's attempt and may be badly wrong for speech like theirs. Listen to
the audio and use the rhythm, number of words, and the sounds you can make out to
decide what they meant. The same rules apply: stay faithful and never add content."""

# "Say it again": the Speaker repeats a sentence that went wrong, and the model gets both.
RETAKE_ADDENDUM = """

You receive two recordings of the same sentence: the person said it twice, and you get
what recognition heard each time, first then second. Use both. A part that is unclear in
one recording is often clear in the other. They meant one sentence; propose that sentence."""

MAX_AUDIO_BYTES = 2_500_000  # about 78 s of 16 kHz mono 16-bit, as for contributions


class WordConfidence(BaseModel):
    text: str = Field(max_length=100)
    confidence: float = Field(ge=0, le=1)


class HistoryPair(BaseModel):
    heard: str = Field(min_length=1, max_length=1000)
    confirmed: str = Field(min_length=1, max_length=1000)


class Retake(BaseModel):
    """The same sentence said a second time."""

    transcript: str = Field(min_length=1, max_length=1000)
    audio_wav_base64: str | None = Field(default=None, max_length=MAX_AUDIO_BYTES * 4 // 3 + 4)
    words: list[WordConfidence] = Field(default_factory=list, max_length=200)


class InterpretRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=1000)
    recent: list[str] = Field(default_factory=list, max_length=5)
    # Earlier sentences from this person this session: what was heard and what they confirmed.
    history: list[HistoryPair] = Field(default_factory=list, max_length=5)
    # AssemblyAI's confidence for each word it heard, in order.
    words: list[WordConfidence] = Field(default_factory=list, max_length=200)
    phrase_book: list[str] = Field(default_factory=list, max_length=100)
    # The sentence as 16 kHz mono 16-bit WAV, base64. Sent to Gemini, never stored.
    audio_wav_base64: str | None = Field(default=None, max_length=MAX_AUDIO_BYTES * 4 // 3 + 4)
    retake: Retake | None = None


def history_block(pairs: list[HistoryPair]) -> str:
    if not pairs:
        return ""
    lines = [f'- Recognition heard: "{p.heard}" The person meant: "{p.confirmed}"' for p in pairs]
    header = "Earlier sentences from this same person, to learn how recognition mishears them:"
    return "\n\n" + header + "\n" + "\n".join(lines)


def decode_audio(encoded: str | None) -> bytes | None:
    """The WAV bytes, or None. Refuses anything but 16 kHz mono 16-bit up to 60 s."""
    if not encoded:
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
        with wave.open(io.BytesIO(data)) as wav:
            shape = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
            seconds = wav.getnframes() / 16000
    except (binascii.Error, wave.Error, EOFError) as exc:
        raise HTTPException(status_code=422, detail="Sentence audio is not a WAV file") from exc
    if shape != (16000, 1, 2) or not 0 < seconds <= 60:
        raise HTTPException(status_code=422, detail="Sentence audio must be 16 kHz mono 16-bit, up to 60 s")
    return data


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
    """No em or en dash reaches a person, even when a model writes one (house style)."""
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
    if request.words:
        parts.append("Speech recognition confidence per word, 0 to 1: " + ", ".join(f"{w.text} {w.confidence:.2f}" for w in request.words))
    if request.retake:
        parts.append(f"The second time, speech recognition heard: {request.retake.transcript}")
        if request.retake.words:
            parts.append("Confidence per word, second time: " + ", ".join(f"{w.text} {w.confidence:.2f}" for w in request.retake.words))
    if request.recent:
        parts.append("Recent sentences the person confirmed, oldest first:\n" + "\n".join(f"- {s}" for s in request.recent))
    if request.phrase_book:
        parts.append("Phrase book (names and words this person uses): " + ", ".join(request.phrase_book))
    return "\n\n".join(parts) + history_block(request.history)


async def call_model(
    client: genai.Client,
    model: str,
    prompt: str,
    delays: tuple[float, ...],
    thinking_low: bool,
    audios: list[bytes] | None = None,
    retake: bool = False,
) -> ModelReading:
    audios = audios or []
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT + (AUDIO_ADDENDUM if audios else "") + (RETAKE_ADDENDUM if retake else ""),
        response_mime_type="application/json",
        response_schema=ModelReading,
        # temperature is ignored by Gemini 3.7 (CineMeridian finding, 2 Sep 2026); consistency
        # comes from thinking_level and response_schema, so it is not set.
        # Gemini 3.7 Flash thinks by default (446 to 750 thought tokens, median 6.7 s in a
        # 3-call probe on 17 Sep 2026). LOW cut that to 264 to 351 tokens, median 4.2 s.
        # MINIMAL is refused for 3.7, and thinking_budget=0 is ignored (still ~300 tokens).
        # The fallback runs with its default, as measured in round C1.
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW) if thinking_low else None,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    contents = [*(types.Part.from_bytes(data=a, mime_type="audio/wav") for a in audios), prompt] if audios else prompt
    response, retries = await generate_with_backoff(client, model, contents, config, delays)
    if retries:
        log.info("gemini %s succeeded after %d retries", model, retries)
    return ModelReading.model_validate_json(response.text)


def describe_failure(model: str, exc: Exception) -> str:
    if isinstance(exc, genai_errors.APIError):
        log.error("gemini %s failed with %s: %s", model, exc.code, str(exc)[:300])
        return f"Interpretation service refused the request ({exc.code})"
    if isinstance(exc, ValueError):
        log.error("gemini %s returned unparseable output: %s", model, exc)
        return "Interpretation service returned an unreadable answer"
    log.error("gemini %s call failed: %r", model, exc)
    return "Interpretation service unreachable"


async def read_with_fallback(
    client: genai.Client, settings: Settings, prompt: str, audios: list[bytes] | None = None, retake: bool = False
) -> tuple[ModelReading, str]:
    """Returns (reading, model that answered). Raises HTTPException 502 when every model failed."""
    try:
        return await call_model(client, settings.gemini_model, prompt, PRIMARY_BACKOFF, True, audios, retake), settings.gemini_model
    except Exception as exc:
        detail = describe_failure(settings.gemini_model, exc)
        fallback = settings.gemini_fallback_model
        if not fallback:
            raise HTTPException(status_code=502, detail=detail) from exc
    log.warning("falling back from %s to %s", settings.gemini_model, fallback)
    try:
        return await call_model(client, fallback, prompt, FALLBACK_BACKOFF, False, audios, retake), fallback
    except Exception as exc:
        raise HTTPException(status_code=502, detail=describe_failure(fallback, exc)) from exc


@router.post("/interpret", response_model=Interpretation)
async def interpret(request: InterpretRequest, settings: Settings = Depends(get_settings)) -> Interpretation:
    if not settings.gemini_configured:
        log.error("interpret requested but Google credentials are missing: %r", settings.google_application_credentials)
        raise HTTPException(status_code=503, detail="Interpretation is not configured")

    client = get_client(settings.google_cloud_project, settings.google_cloud_location, settings.google_application_credentials)
    started = time.perf_counter()
    if PRODUCT_PROMPT == "v1":
        request = request.model_copy(update={"words": []})
        if request.retake:
            request.retake = request.retake.model_copy(update={"words": []})
    audios = [a for a in (decode_audio(request.audio_wav_base64), decode_audio(request.retake.audio_wav_base64 if request.retake else None)) if a]
    reading, model = await read_with_fallback(client, settings, build_prompt(request), audios, request.retake is not None)
    latency_ms = round((time.perf_counter() - started) * 1000)

    interpretation = clean(reading.interpretation)
    alternatives = []
    for alternative in (clean(a) for a in reading.alternatives):
        if alternative and normalise(alternative) != normalise(interpretation) and alternative not in alternatives:
            alternatives.append(alternative)

    log.info(
        "interpret model=%s audios=%d retake=%s history=%d latency_ms=%d confidence=%.2f",
        model, len(audios), request.retake is not None, len(request.history), latency_ms, reading.confidence,
    )
    return Interpretation(
        transcript=request.transcript,
        interpretation=interpretation,
        alternatives=alternatives[:3],
        confidence=reading.confidence,
        unchanged=normalise(interpretation) == normalise(request.transcript),
        model=model,
        latency_ms=latency_ms,
    )
