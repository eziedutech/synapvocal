"""Round C0: interpret round A transcripts with one Gemini model, to choose a model.

Uses backpy's own prompt, schema and cleaning (codes/backpy/app/interpret.py), so
what is measured is what the product would do. Only the model and its thinking
setting vary per run. No speech recognition calls are made.

Guard rails (retry only what is transient, log every wait, spare shared quota):
  * Calls are paced at --calls-per-minute (default 10). The GCP project is shared
    with CineMeridian.
  * One model per run. Nothing is chained.
  * 429 and 5xx are transient on Vertex (shared capacity). They are retried with
    backoff in the spirit of CineMeridian's settings (4 s doubling up to 90 s, with
    jitter, 5 retries). Every wait is logged and each record stores its retry count.
  * Any error left after those retries, and any 400/403/404, aborts the run; nothing
    after it is attempted.
  * Every utterance is written, including failures and those left unattempted.

    uv run python run_interpret.py --source results/round-a-run5.jsonl --model gemini-3.7-flash --thinking low --run 2

Round C1 adds --with-audio: the model also hears the utterance audio (16 kHz WAV)
alongside the transcript, with AUDIO_ADDENDUM appended to the product prompt. The
addendum was fixed on 17 Sep 2026 before any C1 result existed.

Round C2 adds --history K: K earlier pairs from the same speaker ("recognition heard
X, the person confirmed Y") go into the prompt, the way a Speaker's confirmed history
would. Leakage guard: examples come from the same speaker's other utterances in the
source file, never the utterance under test and never one with the same reference
text. Chosen with a fixed seed per utterance.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import logging
import wave
import sys
import time
from pathlib import Path

from torgo import ROOT, load_pcm

REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO / "codes" / "backpy"))

from google.genai import types  # noqa: E402

from app.interpret import (  # noqa: E402
    PROMPTS,
    WordConfidence,
    InterpretRequest,
    ModelReading,
    build_prompt,
    clean,
    generate_with_backoff,
    normalise,
)

BENCHMARK_BACKOFF = (4.0, 8.0, 16.0, 32.0, 64.0)

AUDIO_ADDENDUM = """

You also receive the audio recording of what the person said. The transcript is only
speech recognition's attempt and may be badly wrong for speech like theirs. Listen to
the audio and use the rhythm, number of words, and the sounds you can make out to
decide what they meant. The same rules apply: stay faithful and never add content."""

THINKING = {"low": "LOW", "medium": "MEDIUM"}


def wav_bytes(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(pcm)
    return buffer.getvalue()


def history_for(item: dict, pool: list[dict], k: int) -> list[dict]:
    reference = normalise(item["reference"])
    candidates = [
        r for r in pool
        if r["speaker"] == item["speaker"] and r["id"] != item["id"] and normalise(r["reference"]) != reference and r["hypothesis"].strip()
    ]
    # Deterministic per utterance, independent of run order.
    candidates.sort(key=lambda r: hashlib.sha256(f"{item['id']}|{r['id']}".encode()).hexdigest())
    return candidates[:k]


def history_block(examples: list[dict]) -> str:
    if not examples:
        return ""
    lines = [f'- Recognition heard: "{e["hypothesis"]}" The person meant: "{e["reference"]}"' for e in examples]
    header = "Earlier sentences from this same person, to learn how recognition mishears them:"
    return "\n\n" + header + "\n" + "\n".join(lines)

KEY = REPO / "credentials" / "gcp-synapvocal-backpy.json"
log = logging.getLogger("round-c0")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--thinking", choices=["default", "low", "medium"], default="default")
    parser.add_argument("--with-audio", action="store_true", help="round C1: send the utterance audio too")
    parser.add_argument("--history", type=int, default=0, help="round C2: this many earlier pairs from the same speaker")
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--calls-per-minute", type=float, default=10.0)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--prompt", choices=["v1", "v2"], default="v1")
    parser.add_argument("--words", action="store_true", help="send AssemblyAI's word confidences")
    parser.add_argument("--split", choices=["all", "tune", "report"], default="all",
                        help="tune: ids whose sha256 is even; report: odd. Tune changes on one, report the other.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    rows = [json.loads(line) for line in (ROOT / args.source).read_text(encoding="utf-8").splitlines()]
    pool = [r for r in rows if "meta" not in r and not r.get("error")]
    items = [r for r in pool if r["status"] == "dysarthria" and r["kind"] == "sentence"]
    if args.split != "all":
        parity = 0 if args.split == "tune" else 1
        items = [r for r in items if int(hashlib.sha256(r["id"].encode()).hexdigest(), 16) % 2 == parity]
    if args.limit:
        items = items[: args.limit]

    out_path = ROOT / "results" / f"round-{'c2' if args.history else 'c1' if args.with_audio else 'c0'}-{args.model}{'-audio' if args.with_audio and args.history else ''}{f'-h{args.history}' if args.history else ''}-{args.thinking}{'-' + args.prompt if args.prompt != 'v1' else ''}{'-words' if args.words else ''}{'-' + args.split if args.split != 'all' else ''}-run{args.run}{f'-smoke{args.limit}' if args.limit else ''}.jsonl"
    if out_path.exists():
        raise SystemExit(f"{out_path.name} already exists; pick a new --run")

    from google import genai
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(str(KEY), scopes=["https://www.googleapis.com/auth/cloud-platform"])
    client = genai.Client(vertexai=True, project="cinemeridian", location="global", credentials=credentials,
                          http_options=types.HttpOptions(timeout=120_000))
    thinking = types.ThinkingConfig(thinking_level=getattr(types.ThinkingLevel, THINKING[args.thinking])) if args.thinking in THINKING else None
    audio = load_pcm({item["id"] for item in items}) if args.with_audio else {}
    config = types.GenerateContentConfig(
        system_instruction=PROMPTS[args.prompt] + (AUDIO_ADDENDUM if args.with_audio else ""),
        response_mime_type="application/json",
        response_schema=ModelReading,
        thinking_config=thinking,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    interval = 60.0 / args.calls_per_minute
    log.info("%d transcripts, %s thinking=%s, %.0f calls/min: about %.0f min", len(items), args.model, args.thinking, args.calls_per_minute, len(items) * interval / 60)

    aborted = None
    with out_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"meta": {"source": str(args.source), "model": args.model, "thinking": args.thinking, "with_audio": args.with_audio, "history": args.history, "prompt": args.prompt, "words": args.words, "split": args.split, "calls_per_minute": args.calls_per_minute, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}}) + "\n")
        next_at = 0.0
        for n, item in enumerate(items, 1):
            record = {k: item[k] for k in ("id", "speaker", "status", "kind", "reference", "hypothesis")}
            if aborted:
                record["error"] = "not attempted: run aborted after a refusal"
                out.write(json.dumps(record) + "\n")
                continue
            wait = next_at - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            next_at = time.monotonic() + interval
            if not item["hypothesis"].strip():
                record.update(interpretation="", alternatives=[], confidence=None, latency_ms=None, error="skipped: empty transcript")
                out.write(json.dumps(record) + "\n")
                continue
            started = time.perf_counter()
            try:
                words = [WordConfidence(text=w["text"], confidence=w["confidence"]) for w in item.get("words") or []] if args.words else []
                prompt = build_prompt(InterpretRequest(transcript=item["hypothesis"], words=words)) + history_block(history_for(item, pool, args.history))
                contents = (
                    [types.Part.from_bytes(data=wav_bytes(audio[item["id"]]), mime_type="audio/wav"), prompt]
                    if args.with_audio
                    else prompt
                )
                response, retries = await generate_with_backoff(client, args.model, contents, config, BENCHMARK_BACKOFF)
                reading = ModelReading.model_validate_json(response.text)
                interpretation = clean(reading.interpretation)
                record.update(
                    interpretation=interpretation,
                    alternatives=[clean(a) for a in reading.alternatives],
                    confidence=reading.confidence,
                    unchanged=normalise(interpretation) == normalise(item["hypothesis"]),
                    thought_tokens=response.usage_metadata.thoughts_token_count or 0,
                    # Includes any backoff waits; retries says how many there were.
                    latency_ms=round((time.perf_counter() - started) * 1000),
                    retries=retries,
                    error=None,
                )
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
                aborted = record["error"]
                log.error("REFUSED or failed on %s, aborting: %s", item["id"], aborted)
            out.write(json.dumps(record) + "\n")
            out.flush()
            if n % 25 == 0:
                log.info("%d/%d", n, len(items))

    if aborted:
        log.error("ABORTED. %s is incomplete and must not be quoted.", out_path.name)
        raise SystemExit(2)
    log.info("finished -> %s", out_path.name)


if __name__ == "__main__":
    asyncio.run(main())
