"""Compare speech recognition runs on exactly the same utterances.

Corpus WER, exact matches, and how often one sentence came back split into more than
one turn (a pause read as the end of the sentence), overall and per speaker.

    uv run --no-sync python compare_stt.py results/a.jsonl results/b.jsonl [...]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import jiwer

from score import normalise


def rows(path: Path) -> dict[str, dict]:
    items = (json.loads(line) for line in path.read_text(encoding="utf-8").splitlines())
    return {r["id"]: r for r in items if "id" in r and not r.get("error")}


def summarise(items: list[dict]) -> dict:
    def wer(group: list[dict]) -> float:
        return round(jiwer.wer([normalise(r["reference"]) for r in group], [normalise(r["hypothesis"]) or "<empty>" for r in group]), 3)

    by_speaker: dict[str, list] = defaultdict(list)
    for r in items:
        by_speaker[r["speaker"]].append(r)
    turns = [r.get("turns") for r in items]
    return {
        "n": len(items),
        "wer": wer(items),
        "exact": sum(normalise(r["reference"]) == normalise(r["hypothesis"]) for r in items),
        "split_into_turns": sum(1 for t in turns if isinstance(t, int) and t > 1),
        "by_speaker": {s: wer(g) for s, g in sorted(by_speaker.items())},
    }


def main() -> None:
    runs = {Path(p).name: rows(Path(p)) for p in sys.argv[1:]}
    shared = set.intersection(*(set(r) for r in runs.values()))
    print(f"{len(shared)} utterances scored in every run")
    for name, run in runs.items():
        print(name, summarise([run[i] for i in sorted(shared)]))


if __name__ == "__main__":
    main()
