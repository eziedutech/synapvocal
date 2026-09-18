"""Round D: does saying a sentence again help?

For the 51 dysarthric sentences a speaker really recorded twice (manifest/subset-retake.json),
Gemini 3.7 Flash gets the same inputs as the app's round C2 (audio, transcript, five
earlier sentences from the speaker), in two ways:

  second   the second recording alone, to tell a better take apart from combining takes
  both     both recordings and both transcripts, as the app's "Say it again" sends them

The first recording alone is round C2 itself (results/round-c2-...-run2.jsonl), so it is
not called again. Same prompt, model and thinking level as the product.

    uv run --no-sync python run_retake.py --mode second --run 1
    uv run --no-sync python run_retake.py --mode both --run 1
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from google.genai import types

from run_interpret import BENCHMARK_BACKOFF, KEY, REPO, history_block, history_for, wav_bytes
from torgo import ROOT, load_pcm

sys.path.insert(0, str(REPO / "codes" / "backpy"))
from app.interpret import (  # noqa: E402
    AUDIO_ADDENDUM,
    RETAKE_ADDENDUM,
    SYSTEM_PROMPT_V1,
    InterpretRequest,
    ModelReading,
    Retake,
    build_prompt,
    clean,
    generate_with_backoff,
)

log = logging.getLogger("round-d")
FIRST_STT = ROOT / "results" / "round-a-pilot2000-run1.jsonl"
SECOND_STT = ROOT / "results" / "round-a-retake-run1.jsonl"
MODEL = "gemini-3.7-flash"


def rows(path: Path) -> list[dict]:
    return [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if "meta" not in r]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=["second", "both"])
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--calls-per-minute", type=float, default=15.0)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    manifest = json.loads((ROOT / "manifest" / "subset-retake.json").read_text(encoding="utf-8"))
    pool = [r for r in rows(FIRST_STT) if not r.get("error")]
    first = {r["id"]: r for r in pool}
    second = {r["id"]: r for r in rows(SECOND_STT)}
    pairs = [(first[u["first_take"]], second[u["id"]]) for u in manifest["utterances"]]

    out_path = ROOT / "results" / f"round-d-{MODEL}-{args.mode}-run{args.run}.jsonl"
    if out_path.exists():
        raise SystemExit(f"{out_path.name} already exists; pick a new --run")

    from google import genai
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(str(KEY), scopes=["https://www.googleapis.com/auth/cloud-platform"])
    client = genai.Client(vertexai=True, project="cinemeridian", location="global", credentials=credentials,
                          http_options=types.HttpOptions(timeout=120_000))
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT_V1 + AUDIO_ADDENDUM + (RETAKE_ADDENDUM if args.mode == "both" else ""),
        response_mime_type="application/json",
        response_schema=ModelReading,
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW),
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    audio = load_pcm({a["id"] for a, _ in pairs} | {b["id"] for _, b in pairs})
    interval = 60.0 / args.calls_per_minute

    with out_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"meta": {"mode": args.mode, "model": MODEL, "thinking": "low", "history": 5, "prompt": "v1",
                                       "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}}) + "\n")
        next_at = 0.0
        for n, (a, b) in enumerate(pairs, 1):
            record = {"id": a["id"], "second_id": b["id"], "speaker": a["speaker"], "status": a["status"], "kind": a["kind"],
                      "reference": a["reference"], "hypothesis": a["hypothesis"], "second_hypothesis": b.get("hypothesis", "")}
            heard_first, heard_second = a["hypothesis"].strip(), (b.get("hypothesis") or "").strip()
            if (args.mode == "second" and not heard_second) or (args.mode == "both" and not (heard_first or heard_second)):
                record.update(interpretation="", alternatives=[], error="skipped: empty transcript")
                out.write(json.dumps(record) + "\n")
                continue
            wait = next_at - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            next_at = time.monotonic() + interval
            history = history_block(history_for(a, pool, 5))
            if args.mode == "second":
                prompt = build_prompt(InterpretRequest(transcript=heard_second)) + history
                parts = [types.Part.from_bytes(data=wav_bytes(audio[b["id"]]), mime_type="audio/wav"), prompt]
            else:
                request = InterpretRequest(transcript=heard_first or "(nothing)", retake=Retake(transcript=heard_second or "(nothing)"))
                prompt = build_prompt(request) + history
                parts = [types.Part.from_bytes(data=wav_bytes(audio[a["id"]]), mime_type="audio/wav"),
                         types.Part.from_bytes(data=wav_bytes(audio[b["id"]]), mime_type="audio/wav"), prompt]
            started = time.perf_counter()
            try:
                response, retries = await generate_with_backoff(client, MODEL, parts, config, BENCHMARK_BACKOFF)
                reading = ModelReading.model_validate_json(response.text)
                record.update(interpretation=clean(reading.interpretation), alternatives=[clean(x) for x in reading.alternatives],
                              confidence=reading.confidence, latency_ms=round((time.perf_counter() - started) * 1000),
                              retries=retries, error=None)
            except Exception as exc:  # recorded, never silently dropped
                record.update(interpretation="", alternatives=[], error=f"{type(exc).__name__}: {str(exc)[:200]}")
            out.write(json.dumps(record) + "\n")
            out.flush()
            log.info("%d/%d", n, len(pairs))
    log.info("finished -> %s", out_path.name)


if __name__ == "__main__":
    asyncio.run(main())
