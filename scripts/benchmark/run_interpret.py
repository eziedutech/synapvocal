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
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

from torgo import ROOT

REPO = ROOT.parent.parent
sys.path.insert(0, str(REPO / "codes" / "backpy"))

from google.genai import types  # noqa: E402

from app.interpret import (  # noqa: E402
    SYSTEM_PROMPT,
    InterpretRequest,
    ModelReading,
    build_prompt,
    clean,
    generate_with_backoff,
    normalise,
)

BENCHMARK_BACKOFF = (4.0, 8.0, 16.0, 32.0, 64.0)

KEY = REPO / "credentials" / "gcp-synapvocal-backpy.json"
log = logging.getLogger("round-c0")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--thinking", choices=["default", "low"], default="default")
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--calls-per-minute", type=float, default=10.0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    rows = [json.loads(line) for line in (ROOT / args.source).read_text(encoding="utf-8").splitlines()]
    items = [r for r in rows if "meta" not in r and not r.get("error") and r["status"] == "dysarthria" and r["kind"] == "sentence"]
    if args.limit:
        items = items[: args.limit]

    out_path = ROOT / "results" / f"round-c0-{args.model}-{args.thinking}-run{args.run}{f'-smoke{args.limit}' if args.limit else ''}.jsonl"
    if out_path.exists():
        raise SystemExit(f"{out_path.name} already exists; pick a new --run")

    from google import genai
    from google.oauth2 import service_account

    credentials = service_account.Credentials.from_service_account_file(str(KEY), scopes=["https://www.googleapis.com/auth/cloud-platform"])
    client = genai.Client(vertexai=True, project="cinemeridian", location="global", credentials=credentials,
                          http_options=types.HttpOptions(timeout=120_000))
    thinking = types.ThinkingConfig(thinking_level=types.ThinkingLevel.LOW) if args.thinking == "low" else None
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        response_schema=ModelReading,
        thinking_config=thinking,
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )
    interval = 60.0 / args.calls_per_minute
    log.info("%d transcripts, %s thinking=%s, %.0f calls/min: about %.0f min", len(items), args.model, args.thinking, args.calls_per_minute, len(items) * interval / 60)

    aborted = None
    with out_path.open("w", encoding="utf-8") as out:
        out.write(json.dumps({"meta": {"source": str(args.source), "model": args.model, "thinking": args.thinking, "calls_per_minute": args.calls_per_minute, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}}) + "\n")
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
                response, retries = await generate_with_backoff(
                    client, args.model, build_prompt(InterpretRequest(transcript=item["hypothesis"])), config, BENCHMARK_BACKOFF
                )
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
