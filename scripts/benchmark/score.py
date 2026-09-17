"""Score a results file: corpus WER per group, per speaker, and the failures.

Normalisation is applied identically to reference and hypothesis: lower case,
punctuation removed, digits spelled out, whitespace collapsed. TORGO references
have no punctuation, and the streaming model formats its output, so without this
every comma would count as an error.

WER here is corpus-level (total errors / total reference words) for each group,
so long sentences weigh more than single words. Failed utterances are listed and
excluded from WER, never silently counted as empty.

    uv run python score.py results/round-a-run1.jsonl
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import jiwer

DIGITS = "zero one two three four five six seven eight nine".split()


def normalise(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\b(\d)\b", lambda m: DIGITS[int(m.group(1))], text)
    text = re.sub(r"[^a-z0-9' ]+", " ", text)
    text = text.replace("'", "")
    return " ".join(text.split())


def score(path: Path) -> dict:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    meta = rows[0].get("meta", {})
    rows = [r for r in rows if "meta" not in r]
    failed = [r for r in rows if r.get("error")]
    ok = [r for r in rows if not r.get("error")]
    if any(r["error"].startswith("not attempted") for r in failed):
        print("WARNING: this run was aborted after a refusal; it is incomplete and must not be quoted as a result")

    groups: dict[str, list] = defaultdict(list)
    for r in ok:
        r["ref_n"] = normalise(r["reference"])
        r["hyp_n"] = normalise(r["hypothesis"])
        for key in ("all", r["status"], f"{r['status']}/{r['kind']}", f"speaker/{r['speaker']}"):
            groups[key].append(r)

    def wer(items: list) -> dict:
        refs = [r["ref_n"] for r in items]
        hyps = [r["hyp_n"] for r in items]
        measures = jiwer.process_words(refs, hyps)
        exact = sum(1 for r in items if r["ref_n"] == r["hyp_n"])
        return {
            "utterances": len(items),
            "reference_words": sum(len(x.split()) for x in refs),
            "wer": round(measures.wer, 4),
            "substitutions": measures.substitutions,
            "deletions": measures.deletions,
            "insertions": measures.insertions,
            "exact_match_rate": round(exact / len(items), 4),
            "empty_hypotheses": sum(1 for r in items if not r["hyp_n"]),
        }

    return {
        "file": path.name,
        "meta": meta,
        "attempted": len(rows),
        "failed": len(failed),
        "failures": [{"id": r["id"], "error": r["error"]} for r in failed],
        "groups": {key: wer(items) for key, items in sorted(groups.items())},
    }


def main() -> None:
    path = Path(sys.argv[1])
    summary = score(path)
    out = path.with_suffix(".summary.json")
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"{summary['file']}: attempted {summary['attempted']}, failed {summary['failed']}")
    for key, g in summary["groups"].items():
        print(f"  {key:28} n={g['utterances']:4} words={g['reference_words']:5} WER={g['wer']:.3f} exact={g['exact_match_rate']:.2f} empty={g['empty_hypotheses']}")
    for f in summary["failures"][:10]:
        print(f"  FAILED {f['id']}: {f['error']}")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
