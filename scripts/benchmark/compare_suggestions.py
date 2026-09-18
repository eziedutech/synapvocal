"""Compare interpretation runs on exactly the same sentences.

Only sentences present, and not failed, in every file are scored, so a run with more
failures cannot look better by skipping hard items. Best choice counts every option the
Speaker would see: suggestion, alternatives and what was heard (both tries in round D).

    uv run --no-sync python compare_suggestions.py results/a.jsonl results/b.jsonl [...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jiwer

from score import normalise


def rows(path: Path) -> dict[str, dict]:
    items = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return {r["id"]: r for r in items if "id" in r and not r.get("error") and r.get("interpretation") is not None}


def utterance_wer(reference: str, text: str) -> float:
    return jiwer.wer(normalise(reference), normalise(text) or "<empty>")


def summarise(items: list[dict]) -> dict:
    words = err_raw = err_sug = err_best = 0.0
    exact_raw = exact_sug = exact_best = close_best = 0
    for r in items:
        n = len(normalise(r["reference"]).split())
        heard = [r["hypothesis"]] + ([r["second_hypothesis"]] if r.get("second_hypothesis") else [])
        options = [r["interpretation"], *r["alternatives"], *heard]
        raw, sug, best = utterance_wer(r["reference"], r["hypothesis"]), utterance_wer(r["reference"], r["interpretation"]), min(utterance_wer(r["reference"], o) for o in options if o)
        words += n
        err_raw, err_sug, err_best = err_raw + raw * n, err_sug + sug * n, err_best + best * n
        exact_raw, exact_sug, exact_best = exact_raw + (raw == 0), exact_sug + (sug == 0), exact_best + (best == 0)
        close_best += best <= 0.2
    return {
        "n": len(items),
        "wer_raw": round(err_raw / words, 3),
        "wer_suggestion": round(err_sug / words, 3),
        "wer_best": round(err_best / words, 3),
        "exact_raw": exact_raw,
        "exact_suggestion": exact_sug,
        "exact_best": exact_best,
        "close_best": close_best,
    }


def main() -> None:
    runs = {Path(p).name: rows(Path(p)) for p in sys.argv[1:]}
    shared = set.intersection(*(set(r) for r in runs.values()))
    print(f"{len(shared)} sentences scored in every run")
    for name, run in runs.items():
        print(name, summarise([run[i] for i in sorted(shared)]))


if __name__ == "__main__":
    main()
