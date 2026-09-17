"""Score round C0 files: does interpretation move the text closer to what was said?

For each file, on the same successful utterances:
  * WER of the raw transcript against the TORGO reference (round A),
  * WER of the interpretation against the reference,
  * how often the interpretation fixed, broke, or left alone an utterance,
  * latency percentiles.

Honest limit, printed with every result: TORGO sentences are read prompts, many
of them well known ("The quick brown fox..."). A model can restore a famous
sentence from a few words without understanding the speaker, so a lower WER here
is an upper bound on what free conversation would see.

    uv run python score_interpret.py results/round-c0-*.jsonl
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import jiwer

from score import normalise


def utterance_wer(reference: str, text: str) -> float:
    return jiwer.process_words(normalise(reference), normalise(text) or "").wer


def summarise(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    meta = rows[0]["meta"]
    rows = rows[1:]
    ok = [r for r in rows if not r.get("error")]
    failed = [r for r in rows if r.get("error")]

    def group(items: list[dict]) -> dict:
        refs = [normalise(r["reference"]) for r in items]
        raw = jiwer.process_words(refs, [normalise(r["hypothesis"]) for r in items]).wer
        interp = jiwer.process_words(refs, [normalise(r["interpretation"]) for r in items]).wer
        fixed = broke = same = 0
        for r in items:
            before, after = utterance_wer(r["reference"], r["hypothesis"]), utterance_wer(r["reference"], r["interpretation"])
            if after < before:
                fixed += 1
            elif after > before:
                broke += 1
            else:
                same += 1
        return {"n": len(items), "wer_raw": round(raw, 4), "wer_interpretation": round(interp, 4), "improved": fixed, "worsened": broke, "no_change_in_wer": same}

    by_speaker = defaultdict(list)
    for r in ok:
        by_speaker[r["speaker"]].append(r)
    latencies = sorted(r["latency_ms"] for r in ok)
    return {
        "file": path.name,
        "model": meta["model"],
        "thinking": meta["thinking"],
        "attempted": len(rows),
        "failed": len(failed),
        "failures": [{"id": r["id"], "error": r["error"]} for r in failed],
        "all": group(ok) if ok else None,
        "speakers": {s: group(items) for s, items in sorted(by_speaker.items())},
        "latency_ms": {
            "p50": statistics.median(latencies),
            "p90": latencies[int(0.9 * (len(latencies) - 1))],
            "max": latencies[-1],
        } if latencies else None,
        "limit": "TORGO sentences are read, often well-known prompts; a model can restore them from fragments. Treat lower WER as an upper bound.",
    }


def main() -> None:
    for name in sys.argv[1:]:
        path = Path(name)
        s = summarise(path)
        path.with_suffix(".summary.json").write_text(json.dumps(s, indent=1), encoding="utf-8")
        print(f"\n{s['model']} thinking={s['thinking']}: attempted {s['attempted']}, failed {s['failed']}")
        if s["all"]:
            a = s["all"]
            print(f"  all       n={a['n']} WER raw={a['wer_raw']:.3f} -> interpreted={a['wer_interpretation']:.3f}  improved={a['improved']} worsened={a['worsened']} same={a['no_change_in_wer']}")
            for speaker, g in s["speakers"].items():
                print(f"  {speaker:9} n={g['n']:3} WER raw={g['wer_raw']:.3f} -> interpreted={g['wer_interpretation']:.3f}  improved={g['improved']} worsened={g['worsened']}")
            print(f"  latency ms: {s['latency_ms']}")
        for f in s["failures"][:5]:
            print(f"  FAILED {f['id']}: {f['error']}")
    print("\nLimit: " + "TORGO sentences are read, often well-known prompts; lower WER here is an upper bound.")


if __name__ == "__main__":
    main()
