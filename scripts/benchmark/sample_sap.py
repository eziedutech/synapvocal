"""Pick the SAP pilot (2,000 utterances) and write manifest/subset-sap-pilot2000.json.

Run only after the SAP Data Use Agreement is executed and the official distribution
is unpacked at SAP_DIR.

Rules, fixed 17 Sep 2026 before any SAP data was seen:
  * the official dev split only, so the pilot never touches SAP's test sets
  * one recording per (speaker, normalised text)
  * stratified by etiology: equal share per etiology where available, then an equal
    cap per speaker inside each etiology, so no condition or speaker dominates
  * fixed seed

    SAP_DIR=path/to/distribution uv run python sample_sap.py
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict

from sap import iter_utterances
from score import normalise
from torgo import ROOT

SEED = 20260917


def pick(utterances, target: int, seed: int = SEED):
    unique = {}
    for utt in utterances:
        unique.setdefault((utt.speaker, normalise(utt.reference)), utt)
    by_etiology: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    for utt in unique.values():
        by_etiology[utt.status][utt.speaker].append(utt)

    rng = random.Random(seed)
    chosen = []
    etiologies = sorted(by_etiology)
    remaining = target
    for i, etiology in enumerate(etiologies):
        share = remaining // (len(etiologies) - i)
        speakers = by_etiology[etiology]
        pools = {s: sorted(v, key=lambda u: u.id) for s, v in speakers.items()}
        for pool in pools.values():
            rng.shuffle(pool)
        taken = []
        # Round-robin across speakers so each speaker contributes evenly.
        while len(taken) < share and any(pools.values()):
            for speaker in sorted(pools):
                if pools[speaker] and len(taken) < share:
                    taken.append(pools[speaker].pop())
        chosen.extend(taken)
        remaining -= len(taken)
    return sorted(chosen, key=lambda u: u.id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=2000)
    parser.add_argument("--out", default="subset-sap-pilot2000")
    args = parser.parse_args()

    chosen = pick(iter_utterances(("dev",)), args.target)
    manifest = {
        "dataset": "Speech Accessibility Project, official research distribution, dev split",
        "source": "sap",
        "seed": SEED,
        "rules": {"split": "dev", "one_per_speaker_text": True, "stratified": "etiology, then speaker"},
        "variance_ids": [],
        "utterances": [u.__dict__ for u in chosen],
    }
    out = ROOT / "manifest" / f"{args.out}.json"
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    counts = defaultdict(lambda: [0, set()])
    for u in chosen:
        counts[u.status][0] += 1
        counts[u.status][1].add(u.speaker)
    print(f"wrote {out.name}: {len(chosen)} utterances")
    for etiology, (n, speakers) in sorted(counts.items()):
        print(f"  {etiology}: {n} utterances from {len(speakers)} speakers")


if __name__ == "__main__":
    main()
