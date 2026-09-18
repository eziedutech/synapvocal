"""Second takes: dysarthric sentences that the same speaker really recorded twice.

The pilot kept one recording per speaker and sentence. TORGO has a few sentences a
speaker read again in another recording (a different utterance number or session, not
the same utterance on a second microphone). Those are the only honest test of "say it
again": two separate attempts at one sentence.

For each such pair, the pilot's recording is the first take and another recording is the
second (headMic preferred, then the lowest id, so the choice is fixed).

    uv run --no-sync python sample_retake.py   -> manifest/subset-retake.json
"""

from __future__ import annotations

import json
from collections import defaultdict

from score import normalise
from torgo import ROOT, iter_utterances


def take_of(utterance_id: str) -> tuple[str, str]:
    # F01_1_headMic_0008.wav -> session 1, utterance 0008: one spoken attempt, whatever the mic.
    parts = utterance_id.removesuffix(".wav").split("_")
    return parts[1], parts[-1]


def main() -> None:
    pilot = json.loads((ROOT / "manifest" / "subset-pilot2000.json").read_text(encoding="utf-8"))
    first = {(u["speaker"], normalise(u["reference"])): u for u in pilot["utterances"] if u["kind"] == "sentence"}

    candidates: dict[tuple[str, str], list] = defaultdict(list)
    for u in iter_utterances():
        if u.status == "dysarthria" and u.kind == "sentence":
            candidates[(u.speaker, normalise(u.reference))].append(u)

    seconds = []
    for key, first_take in sorted(first.items()):
        others = [u for u in candidates.get(key, []) if take_of(u.id) != take_of(first_take["id"])]
        if not others:
            continue
        others.sort(key=lambda u: (u.mic != "headMic", u.id))
        u = others[0]
        seconds.append(
            {"id": u.id, "speaker": u.speaker, "status": u.status, "kind": u.kind, "mic": u.mic, "duration": u.duration,
             "reference": u.reference, "first_take": first_take["id"]}
        )

    out = ROOT / "manifest" / "subset-retake.json"
    out.write_text(json.dumps({
        "dataset": pilot["dataset"],
        "rules": {"second_take": "same speaker and sentence, a different recording (utterance or session), headMic preferred"},
        "variance_ids": [],
        "utterances": seconds,
    }, indent=1), encoding="utf-8")
    print(f"{len(seconds)} second takes -> {out}")


if __name__ == "__main__":
    main()
