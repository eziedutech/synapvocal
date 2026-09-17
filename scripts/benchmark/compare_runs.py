"""Compare two runs on the utterances they share, to decide whether numbers are stable.

Stability criterion, fixed on 17 Sep 2026 before the variance run finished:
  * overall WER on the shared utterances differs by at most 0.02 (absolute), and
  * dysarthric WER on the shared utterances differs by at most 0.03 (absolute).
If either is exceeded, the runs are not stable and another repeat is needed
before any number is quoted.

Also reports how many utterances produced a different normalised transcript,
because an unchanged WER can hide answers that moved in both directions.

    uv run python compare_runs.py results/round-a-run5.jsonl results/round-a-run6-variance.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jiwer

from score import normalise

OVERALL_LIMIT = 0.02
DYSARTHRIA_LIMIT = 0.03


def load(path: Path) -> dict[str, dict]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {r["id"]: r for r in rows if "meta" not in r}


def wer(rows: list[dict]) -> float:
    return jiwer.process_words([normalise(r["reference"]) for r in rows], [normalise(r["hypothesis"]) for r in rows]).wer


def main() -> None:
    a_path, b_path = Path(sys.argv[1]), Path(sys.argv[2])
    a, b = load(a_path), load(b_path)
    shared = sorted(set(a) & set(b))
    failed = [i for i in shared if a[i].get("error") or b[i].get("error")]
    ids = [i for i in shared if i not in failed]
    if failed:
        print(f"excluded {len(failed)} utterances that failed in either run: {failed}")

    report = {}
    for label, pick in [("all", lambda r: True), ("dysarthria", lambda r: r["status"] == "dysarthria"), ("healthy", lambda r: r["status"] == "healthy")]:
        chosen = [i for i in ids if pick(a[i])]
        wa, wb = wer([a[i] for i in chosen]), wer([b[i] for i in chosen])
        changed = [i for i in chosen if normalise(a[i]["hypothesis"]) != normalise(b[i]["hypothesis"])]
        report[label] = {"n": len(chosen), "wer_a": round(wa, 4), "wer_b": round(wb, 4), "delta": round(wb - wa, 4), "changed_transcripts": len(changed)}
        print(f"{label:11} n={len(chosen):3} WER {a_path.stem}={wa:.3f} {b_path.stem}={wb:.3f} delta={wb - wa:+.3f} changed transcripts={len(changed)}")

    stable = abs(report["all"]["delta"]) <= OVERALL_LIMIT and abs(report["dysarthria"]["delta"]) <= DYSARTHRIA_LIMIT
    print(f"STABLE: {stable} (limits: overall {OVERALL_LIMIT}, dysarthria {DYSARTHRIA_LIMIT})")

    print("\nchanged transcripts (reference | first run | second run):")
    for i in ids:
        if normalise(a[i]["hypothesis"]) != normalise(b[i]["hypothesis"]):
            print(f"  {i} | {a[i]['reference']} | {a[i]['hypothesis']} | {b[i]['hypothesis']}".encode("ascii", "replace").decode())

    out = b_path.with_name(f"compare-{a_path.stem}-vs-{b_path.stem}.json")
    out.write_text(json.dumps({"shared": len(shared), "excluded_failed": failed, "stable": stable, "groups": report}, indent=1), encoding="utf-8")
    print(f"\nwrote {out.name}")


if __name__ == "__main__":
    main()
