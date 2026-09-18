"""Split TORGO for fine-tuning Whisper so that test scores cannot come from memorising.

Two rules, both enforced here and checked again before writing:

* Text-disjoint. Every normalised prompt text is assigned to train, validation or
  test by a hash of the text itself. TORGO speakers read the same prompt lists, so a
  split by utterance would let the model learn a sentence from one speaker and be
  "tested" on it from another.
* Speaker-held-out view. Three dysarthric speakers (mild F03, moderate M02, severe
  M04, by their AssemblyAI WER on the pilot) never appear in training at all. Their
  test items answer the question a new Speaker asks: does it help someone it has
  never heard?

The "seen speakers" test view keeps the other five dysarthric speakers, whose other
recordings (different texts) are in training. That is the personal-adaptation case.

Training keeps both microphones of an utterance as natural augmentation. Test keeps
one recording per speaker and text (headMic, else arrayMic), the same rule as the
benchmark pilot, so results line up with AssemblyAI's scores on those ids.

    uv run --no-sync --project scripts/benchmark python scripts/finetune/split_torgo.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "benchmark"))

from score import normalise  # noqa: E402
from torgo import iter_utterances  # noqa: E402

VERSION = "v1"
HELD_OUT_SPEAKERS = {"F03", "M02", "M04"}
TEST_BUCKETS = {0, 1}  # 20 percent of texts
VALIDATION_BUCKETS = {2}  # 10 percent of texts


def text_role(text: str) -> str:
    bucket = int(hashlib.sha256(text.encode()).hexdigest(), 16) % 10
    if bucket in TEST_BUCKETS:
        return "test"
    if bucket in VALIDATION_BUCKETS:
        return "validation"
    return "train"


def main() -> None:
    utterances = list(iter_utterances())
    train, validation = [], []
    test_candidates: dict[tuple[str, str], dict[str, object]] = defaultdict(dict)

    for utt in utterances:
        text = normalise(utt.reference)
        if not text:
            continue
        role = text_role(text)
        if role == "test":
            if utt.status == "dysarthria":
                test_candidates[(utt.speaker, text)][utt.mic] = utt
            continue
        if utt.speaker in HELD_OUT_SPEAKERS:
            continue
        (validation if role == "validation" else train).append(utt)

    test = [mics.get("headMic") or mics[sorted(mics)[0]] for mics in test_candidates.values()]
    test_seen = [u for u in test if u.speaker not in HELD_OUT_SPEAKERS]
    test_unseen = [u for u in test if u.speaker in HELD_OUT_SPEAKERS]

    train_texts = {normalise(u.reference) for u in train}
    assert not train_texts & {normalise(u.reference) for u in test}, "text leak into test"
    assert not train_texts & {normalise(u.reference) for u in validation}, "text leak into validation"
    assert not {u.speaker for u in train + validation} & HELD_OUT_SPEAKERS, "held-out speaker in training"

    def describe(items: list) -> dict:
        return {
            "utterances": len(items),
            "hours": round(sum(u.duration for u in items) / 3600, 2),
            "sentences": sum(u.kind == "sentence" for u in items),
            "by_status": dict(Counter(u.status for u in items)),
            "by_speaker": dict(sorted(Counter(u.speaker for u in items).items())),
        }

    manifest = {
        "version": VERSION,
        "rules": {
            "text_disjoint": "sha256(normalised text) % 10: test {0,1}, validation {2}, train rest",
            "held_out_speakers": sorted(HELD_OUT_SPEAKERS),
            "train_mics": "both",
            "test_mic": "headMic, else arrayMic, one per speaker and text",
            "test_status": "dysarthria only",
        },
        "summary": {
            "train": describe(train),
            "validation": describe(validation),
            "test_seen_speakers": describe(test_seen),
            "test_unseen_speakers": describe(test_unseen),
        },
        "ids": {
            "train": sorted(u.id for u in train),
            "validation": sorted(u.id for u in validation),
            "test_seen_speakers": sorted(u.id for u in test_seen),
            "test_unseen_speakers": sorted(u.id for u in test_unseen),
        },
    }
    out = HERE / "manifest" / f"torgo-split-{VERSION}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(manifest, indent=1), encoding="utf-8")
    print(json.dumps(manifest["summary"], indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
