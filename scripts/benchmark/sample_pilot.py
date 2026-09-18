"""Pick the 2,000-utterance dysarthric pilot and write manifest/subset-pilot2000.json.

Agreed 17 Sep 2026: a larger TORGO pilot while the SAP corpus request is pending.
Rules:
  * dysarthric speakers only; one recording per (speaker, normalised text), so the
    same utterance from two microphones is never counted twice
  * headMic preferred, arrayMic when a text exists only there
  * every unique sentence (682), then single words sampled per speaker in proportion
    to what each speaker has, to reach exactly 2,000
  * fixed seed

    uv run python sample_pilot.py
"""

import json
import random
from collections import defaultdict

from score import normalise
from torgo import ROOT, iter_utterances

SEED = 20260917
TARGET = 2000


def main() -> None:
    unique: dict[tuple, dict] = defaultdict(dict)
    for utt in iter_utterances():
        if utt.status != "dysarthria":
            continue
        unique[(utt.speaker, normalise(utt.reference), utt.kind)][utt.mic] = utt

    chosen_by_key = {key: mics.get("headMic") or mics[sorted(mics)[0]] for key, mics in unique.items()}
    sentences = sorted((u for (_, _, kind), u in chosen_by_key.items() if kind == "sentence"), key=lambda u: u.id)
    words_by_speaker: dict[str, list] = defaultdict(list)
    for (speaker, _, kind), utt in chosen_by_key.items():
        if kind == "word":
            words_by_speaker[speaker].append(utt)

    rng = random.Random(SEED)
    need = TARGET - len(sentences)
    total_words = sum(len(v) for v in words_by_speaker.values())
    quotas = {s: int(need * len(v) / total_words) for s, v in words_by_speaker.items()}
    # Hand out the rounding remainder to the largest pools, deterministically.
    for speaker in sorted(words_by_speaker, key=lambda s: (-len(words_by_speaker[s]), s))[: need - sum(quotas.values())]:
        quotas[speaker] += 1

    words = []
    for speaker in sorted(words_by_speaker):
        pool = sorted(words_by_speaker[speaker], key=lambda u: u.id)
        words.extend(rng.sample(pool, quotas[speaker]))

    chosen = sorted(sentences + words, key=lambda u: u.id)
    assert len(chosen) == TARGET and len({u.id for u in chosen}) == TARGET

    manifest = {
        "dataset": "abnerh/TORGO-database (Hugging Face), dysarthric speakers only",
        "seed": SEED,
        "rules": {"one_per_speaker_text": True, "mic": "headMic, else arrayMic", "sentences": "all unique", "words": "proportional per speaker"},
        "variance_ids": [],
        "utterances": [u.__dict__ for u in chosen],
    }
    out = ROOT / "manifest" / "subset-pilot2000.json"
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")

    counts = defaultdict(lambda: [0, 0, 0.0])
    for u in chosen:
        counts[u.speaker][0 if u.kind == "sentence" else 1] += 1
        counts[u.speaker][2] += u.duration
    print(f"wrote {out.name}: {len(chosen)} utterances, {len(sentences)} sentences, {len(words)} words, "
          f"{sum(u.duration for u in chosen) / 3600:.2f} h audio, {sum(1 for u in chosen if u.mic != 'headMic')} from arrayMic")
    for speaker in sorted(counts):
        s, w, d = counts[speaker]
        print(f"  {speaker}: {s} sentences, {w} words, {d / 60:.1f} min")


if __name__ == "__main__":
    main()
