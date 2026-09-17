"""Pick the fixed benchmark subset and write it to manifest/subset-v1.json.

Rounds A, B and C all read this manifest, so they score the same utterances.
Rules (agreed 17 Sep 2026):
  * headMic only, so the same utterance is never counted twice
  * per dysarthric speaker: up to 40 sentences; per control speaker: up to 25
  * per speaker: up to 15 single words
  * a speaker's repeated prompt counts once (distinct reference text per speaker)
  * variance check: 60 utterances spread across speakers, run twice in round A

    uv run python sample.py
"""

import json
import random
from collections import defaultdict

from torgo import ROOT, iter_utterances

SEED = 20260917
SENTENCES = {"dysarthria": 40, "healthy": 25}
WORDS = 15
VARIANCE_SIZE = 60


def main() -> None:
    pools: dict[tuple[str, str], list] = defaultdict(list)
    seen: set[tuple[str, str]] = set()
    for utt in iter_utterances():
        if utt.mic != "headMic":
            continue
        key = (utt.speaker, utt.reference.lower())
        if key in seen:
            continue
        seen.add(key)
        pools[(utt.speaker, utt.kind)].append(utt)

    rng = random.Random(SEED)
    chosen = []
    for (speaker, kind), pool in sorted(pools.items()):
        pool.sort(key=lambda u: u.id)
        status = pool[0].status
        limit = SENTENCES[status] if kind == "sentence" else WORDS
        chosen.extend(rng.sample(pool, min(limit, len(pool))))

    chosen.sort(key=lambda u: u.id)
    # Round-robin across speakers so the variance set is not dominated by one voice.
    by_speaker = defaultdict(list)
    for utt in chosen:
        by_speaker[utt.speaker].append(utt)
    for items in by_speaker.values():
        rng.shuffle(items)
    variance = []
    while len(variance) < VARIANCE_SIZE and any(by_speaker.values()):
        for speaker in sorted(by_speaker):
            if by_speaker[speaker] and len(variance) < VARIANCE_SIZE:
                variance.append(by_speaker[speaker].pop().id)

    manifest = {
        "dataset": "abnerh/TORGO-database (Hugging Face), 4 parquet shards, 1,564,871,166 bytes",
        "seed": SEED,
        "rules": {"mic": "headMic", "sentences_per_speaker": SENTENCES, "words_per_speaker": WORDS},
        "variance_ids": sorted(variance),
        "utterances": [utt.__dict__ for utt in chosen],
    }
    out = ROOT / "manifest" / "subset-v1.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    counts = defaultdict(lambda: [0, 0.0])
    for utt in chosen:
        counts[(utt.status, utt.kind)][0] += 1
        counts[(utt.status, utt.kind)][1] += utt.duration
    print(f"wrote {out.relative_to(ROOT)}: {len(chosen)} utterances, {len(variance)} in variance set")
    for key in sorted(counts):
        print(f"  {key}: {counts[key][0]} utterances, {counts[key][1] / 60:.1f} min")
    print(f"  total audio: {sum(u.duration for u in chosen) / 60:.1f} min")
    short = {s: len(v) for s, v in pools.items() if len(v) < (SENTENCES[v[0].status] if s[1] == 'sentence' else WORDS)}
    if short:
        print(f"  pools smaller than the limit (all taken): {short}")


if __name__ == "__main__":
    main()
