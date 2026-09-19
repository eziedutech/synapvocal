"""Build the data file behind the /benchmark page from the results files.

Numbers on the page are never typed by hand: they are computed here from the
committed results, so the page and the files cannot disagree.

    uv run python export_web.py
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import jiwer

from score import normalise, score
from torgo import ROOT, iter_utterances

OUT = ROOT.parent.parent / "codes" / "frontrouter" / "app" / "data" / "benchmark.json"
RESULTS = ROOT / "results"

ROUND_A = RESULTS / "round-a-run5.jsonl"
VARIANCE_RUNS = [RESULTS / "round-a-run5.jsonl", RESULTS / "round-a-run6-variance.jsonl", RESULTS / "round-a-run7-variance.jsonl"]
ROUND_B = RESULTS / "round-b-run2.jsonl"
# Larger pilot, 17 Sep 2026: every unique dysarthric sentence in TORGO (one per speaker and text),
# all with Gemini 3.7 Flash, thinking LOW.
PILOT_STT = RESULTS / "round-a-pilot2000-run1.jsonl"
PILOT = {
    "text": RESULTS / "round-c0-gemini-3.7-flash-low-run4.jsonl",
    "audio": RESULTS / "round-c1-gemini-3.7-flash-low-run3.jsonl",
    "audio_history": RESULTS / "round-c2-gemini-3.7-flash-audio-h5-low-run2.jsonl",
}
# Round D, 18 Sep 2026: the 51 dysarthric sentences a speaker really recorded twice.
RETAKE = {
    "one": RESULTS / "round-c2-gemini-3.7-flash-audio-h5-low-run2.jsonl",
    "second": RESULTS / "round-d-gemini-3.7-flash-second-run1.jsonl",
    "both": RESULTS / "round-d-gemini-3.7-flash-both-run1.jsonl",
}
# Prompt v2 (word confidences, three alternatives), tune half only: it lost, so it is shown as tried.
PROMPT_V2_TUNE = RESULTS / "round-c2-gemini-3.7-flash-audio-h5-low-v2-words-tune-run1.jsonl"
# Round E, 19 Sep 2026: AssemblyAI model and prompt on the three hardest speakers (exploratory).
ROUND_E = {
    "u35": RESULTS / "round-a-pilot2000-run1.jsonl",
    "u35_prompt": RESULTS / "round-a-severe-run1-promptE.jsonl",
    "u36": RESULTS / "round-a-severe-run1-promptnone-universal-3-6-pro.jsonl",
    "u36_prompt": RESULTS / "round-a-severe-run1-promptE-universal-3-6-pro.jsonl",
}
C0 = {"gemini-3.7-flash": RESULTS / "round-c0-gemini-3.7-flash-low-run3.jsonl", "gemini-3.8-flash": RESULTS / "round-c0-gemini-3.8-flash-low-run2.jsonl"}


def rows(path: Path) -> list[dict]:
    return [r for r in (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()) if "meta" not in r]


def utterance_wer(reference: str, text: str) -> float:
    return jiwer.process_words(normalise(reference), normalise(text) or "").wer


def corpus_wer(pairs: list[tuple[str, str]]) -> float:
    return jiwer.process_words([normalise(r) for r, _ in pairs], [normalise(h) for _, h in pairs]).wer


def group_view(summary: dict, key: str) -> dict:
    g = summary["groups"][key]
    return {"utterances": g["utterances"], "wer": g["wer"], "exact": g["exact_match_rate"]}


def round_summary(path: Path) -> dict:
    s = score(path)
    return {
        "attempted": s["attempted"],
        "failed": s["failed"],
        "groups": {k: group_view(s, k) for k in ("dysarthria/sentence", "dysarthria/word", "healthy/sentence", "healthy/word", "dysarthria", "healthy")},
        "speakers": [
            {"speaker": k.split("/")[1], "wer": g["wer"], "utterances": g["utterances"], "status": "healthy" if "C" in k.split("/")[1] else "dysarthria"}
            for k, g in s["groups"].items()
            if k.startswith("speaker/")
        ],
    }


def variance() -> list[dict]:
    wanted = {r["id"] for r in rows(VARIANCE_RUNS[1])}
    out = []
    for i, path in enumerate(VARIANCE_RUNS, 1):
        picked = [r for r in rows(path) if r["id"] in wanted and not r.get("error")]
        out.append({
            "label": f"Repeat {i}",
            "dysarthria": round(corpus_wer([(r["reference"], r["hypothesis"]) for r in picked if r["status"] == "dysarthria"]), 4),
            "healthy": round(corpus_wer([(r["reference"], r["hypothesis"]) for r in picked if r["status"] == "healthy"]), 4),
            "utterances": len(picked),
        })
    return out


def interpretation(model: str, path: Path) -> dict:
    items = [r for r in rows(path) if not r.get("error")]
    total = 0
    err_raw = err_suggestion = err_best = 0.0
    exact_raw = exact_suggestion = exact_best = improved = worsened = 0
    # "Close": at most one word in five wrong for that sentence. Reported beside
    # exact matches, never instead of them.
    close_raw = close_best = 0
    for r in items:
        n = len(normalise(r["reference"]).split())
        total += n
        options = [r["hypothesis"], r["interpretation"], *r["alternatives"]]
        wers = [utterance_wer(r["reference"], o) for o in options]
        err_raw += wers[0] * n
        err_suggestion += wers[1] * n
        err_best += min(wers) * n
        exact_raw += wers[0] == 0
        exact_suggestion += wers[1] == 0
        exact_best += min(wers) == 0
        close_raw += wers[0] <= 0.2
        close_best += min(wers) <= 0.2
        improved += wers[1] < wers[0]
        worsened += wers[1] > wers[0]
    latencies = sorted(r["latency_ms"] for r in items)
    return {
        "model": model,
        "sentences": len(items),
        "wer_raw": round(err_raw / total, 4),
        "wer_suggestion": round(err_suggestion / total, 4),
        "wer_best_choice": round(err_best / total, 4),
        "exact_raw": exact_raw,
        "exact_suggestion": exact_suggestion,
        "exact_best_choice": exact_best,
        "close_raw": close_raw,
        "close_best_choice": close_best,
        "improved": improved,
        "worsened": worsened,
        "latency_ms": {
            "p50": round(statistics.median(latencies)),
            "p90": latencies[int(0.9 * (len(latencies) - 1))],
            "max": latencies[-1],
        },
        "retries": sum(r.get("retries", 0) for r in items),
    }


def counts(items) -> dict:
    """Sentences and single words, per speaker group, for any rows with status and kind."""
    out = {f"{status}/{kind}": 0 for status in ("dysarthria", "healthy") for kind in ("sentence", "word")}
    for item in items:
        out[f"{item['status']}/{item['kind']}"] += 1
    return out


def tested_sets() -> dict:
    full = [{"status": u.status, "kind": u.kind, "duration": u.duration} for u in iter_utterances()]
    variance_ids = {r["id"] for r in rows(VARIANCE_RUNS[1])}
    return {
        "full": {"recordings": len(full), "hours": round(sum(u["duration"] for u in full) / 3600, 1), **counts(full)},
        "round_a": counts(rows(ROUND_A)),
        "variance": counts(r for r in rows(ROUND_A) if r["id"] in variance_ids),
        "suggestions": counts(r for r in rows(C0["gemini-3.7-flash"]) if not r.get("error")),
        "pilot_stt": counts(rows(PILOT_STT)),
        "pilot_suggestions": counts(r for r in rows(PILOT["audio_history"]) if not r.get("error")),
    }


def shared_summary(paths: dict[str, Path]) -> dict:
    """Same sentences in every run; best choice counts both heard texts when there are two."""
    from compare_suggestions import rows as keyed, summarise

    runs = {name: keyed(path) for name, path in paths.items()}
    ids = sorted(set.intersection(*(set(r) for r in runs.values())))
    return {name: summarise([run[i] for i in ids]) for name, run in runs.items()}


def retake() -> dict:
    return shared_summary(RETAKE)


def round_e() -> dict:
    from compare_stt import rows as keyed, summarise

    runs = {name: keyed(path) for name, path in ROUND_E.items()}
    ids = sorted(set.intersection(*(set(r) for r in runs.values())))
    return {name: summarise([run[i] for i in ids]) for name, run in runs.items()}


def prompt_v2() -> dict:
    return shared_summary({"v1": PILOT["audio_history"], "v2": PROMPT_V2_TUNE})


def main() -> None:
    b_rows = rows(ROUND_B)
    b_complete = len(b_rows) == 695 and not any(r.get("error") for r in b_rows)
    data = {
        "dataset": {
            "name": "TORGO",
            "subset": "695 head-microphone utterances, seed 20260917",
            "speakers": {"dysarthria": 8, "healthy": 7},
            "tested": tested_sets(),
        },
        "round_a": round_summary(ROUND_A),
        "variance": variance(),
        "round_b": round_summary(ROUND_B) if b_complete else None,
        "round_c0": [interpretation(model, path) for model, path in C0.items()],
        "pilot": {variant: interpretation("gemini-3.7-flash", path) for variant, path in PILOT.items()},
        "retake": retake(),
        "prompt_v2": prompt_v2(),
        "round_e": round_e(),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"wrote {OUT} (round B {'included' if b_complete else 'not complete, omitted'})")


if __name__ == "__main__":
    main()
