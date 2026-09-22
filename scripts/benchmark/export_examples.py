"""Build the Bridge's TORGO example cards from the results files.

The cards say what the benchmark heard and suggested for each recording. Typed by
hand they went stale the moment the app changed speech recognition model, so they
are computed here from the same runs the /benchmark page uses:

  what was heard     the streaming run on the model the product uses
  what was suggested the interpretation run the product's settings match

The nine recordings themselves are fixed: whatever .wav files sit in the examples
directory is the set. This script never chooses them, it only describes them.

    uv run python export_examples.py
"""

from __future__ import annotations

import json
from pathlib import Path

from export_web import PILOT, PILOT_STT_MODELS, rows
from score import normalise
from torgo import ROOT

EXAMPLES_DIR = ROOT.parent.parent / "codes" / "frontrouter" / "public" / "examples" / "torgo"
OUT = ROOT.parent.parent / "codes" / "frontrouter" / "app" / "data" / "torgoExamples.json"

# The run whose transcripts the product's speech recognition settings produce, and the
# interpretation run whose settings the product matches (audio plus five earlier sentences).
HEARD = PILOT_STT_MODELS["u36"]
SUGGESTED = PILOT["app"]

# Severity comes from how badly speech recognition does on that speaker across the whole
# pilot, not from a judgement about the person. Word error rate, on the model in use.
SEVERITY_BANDS = [(0.2, "mild"), (0.55, "moderate")]


def severity(speaker_wer: float) -> str:
    for limit, label in SEVERITY_BANDS:
        if speaker_wer < limit:
            return label
    return "severe"


def main() -> None:
    files = sorted(p.name for p in EXAMPLES_DIR.glob("*.wav"))
    if not files:
        raise SystemExit(f"no example recordings in {EXAMPLES_DIR}")

    heard = {r["id"]: r for r in rows(HEARD)}
    suggested = {r["id"]: r for r in rows(SUGGESTED) if not r.get("error")}

    by_speaker: dict[str, list[dict]] = {}
    for r in heard.values():
        by_speaker.setdefault(r["speaker"], []).append(r)
    speaker_wer = {}
    for speaker, items in by_speaker.items():
        import jiwer

        speaker_wer[speaker] = jiwer.wer(
            [normalise(r["reference"]) for r in items],
            [normalise(r["hypothesis"]) or "<empty>" for r in items],
        )

    examples = []
    missing = []
    for name in files:
        h = heard.get(name)
        s = suggested.get(name)
        if h is None or s is None:
            missing.append(name)
            continue
        examples.append({
            "id": name,
            "file": f"/examples/torgo/{name}",
            "speaker": h["speaker"],
            "severity": severity(speaker_wer[h["speaker"]]),
            "reference": h["reference"],
            "benchmark_heard": h["hypothesis"],
            "benchmark_suggestion": s["interpretation"],
            # True when the benchmark's first suggestion was the sentence word for word.
            # Shown so a card cannot promise more than the measurement supports.
            "benchmark_exact": normalise(s["interpretation"]) == normalise(h["reference"]),
            # More than one means the Speaker paused and the recogniser ended the turn
            # there; the app joins them back into one sentence, as the benchmark does.
            "benchmark_turns": h.get("turns", 1),
            "seconds": round(h["duration"], 1),
        })

    if missing:
        raise SystemExit(f"no results for {', '.join(missing)}: score those recordings before exporting")

    # Easiest first, so the dialog opens on a recording that is quick to follow.
    order = {"mild": 0, "moderate": 1, "severe": 2}
    examples.sort(key=lambda e: (order[e["severity"]], e["seconds"]))
    OUT.write_text(json.dumps(examples, indent=1), encoding="utf-8")
    exact = sum(1 for e in examples if e["benchmark_exact"])
    print(f"wrote {OUT}: {len(examples)} examples, {exact} where the first suggestion was exactly right")


if __name__ == "__main__":
    main()
