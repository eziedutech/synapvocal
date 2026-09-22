"""Stream benchmark utterances to AssemblyAI exactly as the product does.

One websocket session per utterance, audio paced at real time in 100 ms chunks,
with the same connection settings as backpy (codes/backpy/app/stt_config.py).
After the last chunk the script sends Terminate, which flushes the final turn,
and joins every finished turn into one hypothesis.

Guard rails (added after run 1 made ~700 connection attempts in 3.4 minutes):
  * New sessions are paced: at most --sessions-per-minute (default 4). The free
    AssemblyAI plan allows 5 new streams per minute.
  * The first refusal (1008, 401, 403, 429, or an Error instead of Begin) aborts
    the whole run. Nothing after it is attempted.
  * One run per command. Nothing is chained.
  * Budget: benchmark spend is summed from session_seconds in every results file
    (including results/invalid). A run does not start if spend so far plus this
    run's estimate would pass BUDGET_USD, and stops if spend passes it mid-run.
    Browser sessions are not counted here; the AssemblyAI dashboard is the source
    of truth for the account balance.

Each utterance becomes one JSON line, including failures and utterances left
unattempted after an abort, each with its reason. Nothing is silently dropped.

    uv run python run_stt.py --round A --run 4 --limit 10       # rate smoke test
    uv run python run_stt.py --round A --run 5                  # full subset
    uv run python run_stt.py --round A --run 6 --variance-only  # variance check
    uv run python run_stt.py --round B --run 1                  # with context prompt
    uv run python run_stt.py --round B --run 2 --resume         # finish an interrupted run

Round B differs from A only by ROUND_B_PROMPT, fixed on 17 Sep 2026 before any B
result existed. It describes the product situation, not TORGO (no "reading aloud"),
so a gain here would carry over to real use. No keyterms: TORGO has no personal
vocabulary, and feeding reference words would be cheating.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import logging
import time
from pathlib import Path
from urllib.parse import urlencode

import websockets

from torgo import ROOT, load_pcm

REPO = ROOT.parent.parent
CHUNK_BYTES = 3200  # 100 ms of 16 kHz 16-bit mono
FINISH_TIMEOUT_S = 30
RETRY_DELAY_S = 5
# Agreed with Zia on 17 Sep 2026: benchmark spend on AssemblyAI stops at 15 USD.
BUDGET_USD = 15.0
USD_PER_HOUR = 0.45  # Universal-3.5 Pro realtime base rate, billed on session duration
PROMPT_USD_PER_HOUR = 0.05  # added when a prompt is sent
SESSION_OVERHEAD_S = 2.0  # connect and flush time per session, observed in round A

# Round E (19 Sep 2026): asks for a faithful transcript and describes the speech, after
# Zia's playground test where it kept one sentence in one turn and invented nothing.
ROUND_E_PROMPT = (
    "Transcribe English speech from a speaker with dysarthria. Their speech is slow and may be slurred or strained, "
    "with long pauses, stretched sounds and weak consonants inside a sentence. They may repeat a word or restart a phrase. "
    "Transcribe exactly the words they say, in the order they say them. Keep short words such as a, the, our, and, with "
    "when they are spoken. Do not add words that were not spoken, and do not replace an unclear word with a more common phrase."
)

ROUND_B_PROMPT = (
    "A person with dysarthria, a motor speech disorder, is speaking English to another person. "
    "Their speech may be slow, slurred or strained, with long pauses inside a sentence. "
    "Transcribe the English words they are trying to say."
)

log = logging.getLogger("benchmark")


class Refused(Exception):
    """The service said no. Retrying or moving on would only repeat the refusal."""


class SessionPacer:
    """Spaces session openings evenly so no rolling minute exceeds the limit."""

    def __init__(self, per_minute: float) -> None:
        self.interval = 60.0 / per_minute
        self.next_at = 0.0
        self.lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self.lock:
            now = time.monotonic()
            if self.next_at > now:
                await asyncio.sleep(self.next_at - now)
            self.next_at = max(now, self.next_at) + self.interval


def spent_usd() -> float:
    seconds = 0.0
    for path in (ROOT / "results").rglob("round-*.jsonl"):
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if "meta" in row:
                rate = USD_PER_HOUR + (PROMPT_USD_PER_HOUR if row["meta"].get("params", {}).get("prompt") else 0)
                continue
            seconds_here = row.get("session_seconds") or 0
            seconds += seconds_here * rate / USD_PER_HOUR
    return seconds / 3600 * USD_PER_HOUR


def load_stream_config() -> tuple[str, dict]:
    path = REPO / "codes" / "backpy" / "app" / "stt_config.py"
    spec = importlib.util.spec_from_file_location("stt_config", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.WS_URL, dict(module.STREAM_PARAMS)


def api_key() -> str:
    key = (REPO / "credentials" / "assembly.txt").read_text(encoding="utf-8").strip()
    if not key:
        raise SystemExit("credentials/assembly.txt is empty")
    return key


async def transcribe(url: str, key: str, pcm: bytes) -> dict:
    turns: dict[int, str] = {}
    words: dict[int, list] = {}
    started = time.perf_counter()
    try:
        ws_cm = websockets.connect(url, additional_headers={"Authorization": key})
        ws = await ws_cm.__aenter__()
    except websockets.InvalidStatus as exc:
        status = exc.response.status_code
        if status in (401, 403, 429):
            raise Refused(f"HTTP {status} on connect") from exc
        raise
    try:
        first = json.loads(await ws.recv())
        if first.get("type") != "Begin":
            raise Refused(f"expected Begin, got {first}")

        async def reader() -> dict:
            async for raw in ws:
                message = json.loads(raw)
                if message.get("type") == "Turn" and message.get("end_of_turn"):
                    turns[message["turn_order"]] = message.get("transcript", "")
                    words[message["turn_order"]] = [
                        {"text": w.get("text"), "confidence": w.get("confidence")} for w in message.get("words", [])
                    ]
                elif message.get("type") == "Termination":
                    return message
                elif message.get("type") == "Error":
                    raise Refused(f"error during session: {message}")
                elif message.get("type") not in ("Turn", "SpeechStarted"):
                    log.warning("unexpected message: %s", str(message)[:200])
            raise RuntimeError(f"closed without Termination (code {ws.close_code}, {ws.close_reason!r})")

        reading = asyncio.create_task(reader())
        for offset in range(0, len(pcm), CHUNK_BYTES):
            if reading.done():
                break
            await ws.send(pcm[offset : offset + CHUNK_BYTES])
            await asyncio.sleep(0.1)
        if not reading.done():
            await ws.send(json.dumps({"type": "Terminate"}))
        termination = await asyncio.wait_for(reading, FINISH_TIMEOUT_S)
    except websockets.ConnectionClosedError as exc:
        if exc.rcvd is not None and exc.rcvd.code == 1008:
            raise Refused(f"closed with 1008: {exc.rcvd.reason}") from exc
        raise
    finally:
        await ws_cm.__aexit__(None, None, None)

    return {
        "hypothesis": " ".join(turns[k] for k in sorted(turns)).strip(),
        "turns": len(turns),
        # Per-word confidence, to test skipping interpretation when recognition is sure.
        "words": [w for k in sorted(words) for w in words[k]],
        "wall_seconds": round(time.perf_counter() - started, 2),
        "session_seconds": termination.get("session_duration_seconds"),
    }


def is_transient(exc: Exception) -> bool:
    if isinstance(exc, Refused):
        return False
    if isinstance(exc, (asyncio.TimeoutError, OSError)):
        return True
    if isinstance(exc, websockets.ConnectionClosedError):
        return exc.rcvd is None or exc.rcvd.code in (1011, 1012, 1013)
    return False


async def worker(queue, url, key, pcm, out, counter, pacer, abort: asyncio.Event, budget: dict) -> None:
    while True:
        utt = await queue.get()
        record = {**utt}
        attempt = 0
        try:
            if abort.is_set():
                record["error"] = "not attempted: run aborted after a refusal"
                continue
            for attempt in (1, 2):
                await pacer.wait()
                if abort.is_set():
                    record["error"] = "not attempted: run aborted after a refusal"
                    break
                if budget["spent"] >= BUDGET_USD:
                    record["error"] = f"not attempted: budget of {BUDGET_USD} USD reached"
                    log.error("budget reached (%.2f USD), stopping", budget["spent"])
                    abort.set()
                    break
                try:
                    record.update(await transcribe(url, key, pcm[utt["id"]]))
                    record["error"] = None
                    budget["spent"] += (record["session_seconds"] or 0) / 3600 * budget["rate"]
                    break
                except Exception as exc:  # recorded, never swallowed
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    if isinstance(exc, Refused):
                        log.error("REFUSED on %s, aborting the run: %s", utt["id"], exc)
                        abort.set()
                        break
                    if attempt == 1 and is_transient(exc):
                        log.warning("%s transient failure, retrying once after %ss: %s", utt["id"], RETRY_DELAY_S, exc)
                        await asyncio.sleep(RETRY_DELAY_S)
                        continue
                    log.error("%s failed: %s", utt["id"], record["error"])
                    break
        finally:
            record["attempts"] = attempt
            out.write(json.dumps(record) + "\n")
            out.flush()
            counter["done"] += 1
            if counter["done"] % 25 == 0 or counter["done"] == counter["total"]:
                log.info("%d/%d done", counter["done"], counter["total"])
            queue.task_done()


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", required=True, choices=["A", "B"])
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--variance-only", action="store_true")
    parser.add_argument("--limit", type=int, help="smoke test: only the first N utterances")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--sessions-per-minute", type=float, default=4.0)
    parser.add_argument("--resume", action="store_true", help="continue an interrupted run in the same file")
    parser.add_argument("--manifest", default="subset-v1", help="manifest name in manifest/, without .json")
    parser.add_argument("--speech-model", help="override the product's speech model, e.g. universal-3-6-pro")
    parser.add_argument("--prompt", choices=["none", "B", "E"], help="override the round's prompt")
    parser.add_argument(
        "--filter-profanity",
        action="store_true",
        help="ask AssemblyAI to filter profanity, to see what it returns for the words it mishears as swearing",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    manifest = json.loads((ROOT / "manifest" / f"{args.manifest}.json").read_text(encoding="utf-8"))
    utterances = manifest["utterances"]
    if args.variance_only:
        wanted = set(manifest["variance_ids"])
        utterances = [u for u in utterances if u["id"] in wanted]
    if args.limit:
        utterances = utterances[: args.limit]

    ws_url, params = load_stream_config()
    if args.round == "B":
        params["prompt"] = ROUND_B_PROMPT
    if args.prompt == "B":
        params["prompt"] = ROUND_B_PROMPT
    elif args.prompt == "E":
        params["prompt"] = ROUND_E_PROMPT
    elif args.prompt == "none":
        params.pop("prompt", None)
    if args.speech_model:
        params["speech_model"] = args.speech_model
    if args.filter_profanity:
        params["filter_profanity"] = "true"
    url = f"{ws_url}?{urlencode(params)}"
    suffix = ("-variance" if args.variance_only else "") + (f"-smoke{args.limit}" if args.limit else "")
    if args.speech_model:
        suffix = f"-{args.speech_model}" + suffix
    if args.prompt:
        suffix = f"-prompt{args.prompt}" + suffix
    if args.filter_profanity:
        suffix = "-filterprofanity" + suffix
    tag = "" if args.manifest == "subset-v1" else f"-{args.manifest.removeprefix('subset-')}"
    out_path = ROOT / "results" / f"round-{args.round.lower()}{tag}-run{args.run}{suffix}.jsonl"
    out_path.parent.mkdir(exist_ok=True)
    kept_lines: list[str] = []
    if args.resume:
        # Keep every successful record, retry the rest, and refuse if the settings changed.
        if not out_path.exists():
            raise SystemExit(f"--resume needs an existing {out_path.name}")
        lines = out_path.read_text(encoding="utf-8").splitlines()
        original = json.loads(lines[0])["meta"]["params"]
        if original != params:
            raise SystemExit(f"refusing to resume: settings differ from the original run ({original} vs {params})")
        done = set()
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                log.warning("dropping a malformed line from the interrupted run")
                continue
            if "meta" in row or not row.get("error"):
                kept_lines.append(line)
                if "meta" not in row:
                    done.add(row["id"])
        utterances = [u for u in utterances if u["id"] not in done]
        log.info("resuming %s: %d kept, %d left to run", out_path.name, len(done), len(utterances))
    elif out_path.exists() or (out_path.parent / "invalid" / out_path.name).exists():
        raise SystemExit(f"{out_path.name} already exists; pick a new --run rather than overwrite a measurement")

    rate = USD_PER_HOUR + (PROMPT_USD_PER_HOUR if params.get("prompt") else 0)
    spent = spent_usd()
    estimate_usd = sum(u["duration"] + SESSION_OVERHEAD_S for u in utterances) / 3600 * rate
    log.info("benchmark spend so far %.2f USD, this run about %.2f USD, budget %.2f USD", spent, estimate_usd, BUDGET_USD)
    if spent + estimate_usd > BUDGET_USD:
        raise SystemExit(f"refusing to start: {spent:.2f} + {estimate_usd:.2f} USD would pass the {BUDGET_USD} USD budget")
    budget = {"spent": spent, "rate": rate}

    estimate_min = len(utterances) / args.sessions_per_minute
    log.info("%d utterances at %.1f new sessions/min: about %.0f min", len(utterances), args.sessions_per_minute, estimate_min)
    pcm = load_pcm({u["id"] for u in utterances})

    key = api_key()
    queue: asyncio.Queue = asyncio.Queue()
    for utt in utterances:
        queue.put_nowait(utt)
    counter = {"done": 0, "total": len(utterances)}
    pacer = SessionPacer(args.sessions_per_minute)
    abort = asyncio.Event()
    started = time.perf_counter()
    with out_path.open("w", encoding="utf-8") as out:
        meta = {"round": args.round, "run": args.run, "params": params, "sessions_per_minute": args.sessions_per_minute,
                "workers": args.workers, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        if args.resume:
            for line in kept_lines:
                out.write(line + "\n")
            # A second meta line marks where the resumed part begins.
            meta["resume"] = True
        out.write(json.dumps({"meta": meta}) + "\n")
        tasks = [asyncio.create_task(worker(queue, url, key, pcm, out, counter, pacer, abort, budget)) for _ in range(args.workers)]
        await queue.join()
        for task in tasks:
            task.cancel()
    minutes = (time.perf_counter() - started) / 60
    log.info("benchmark spend now %.2f USD of %.2f USD", spent_usd(), BUDGET_USD)
    if abort.is_set():
        log.error("ABORTED after a refusal (%.1f min). Results in %s are incomplete.", minutes, out_path.name)
        raise SystemExit(2)
    log.info("finished in %.1f min -> %s", minutes, out_path.name)


if __name__ == "__main__":
    asyncio.run(main())
