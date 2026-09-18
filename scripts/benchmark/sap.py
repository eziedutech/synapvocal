"""Reader for the Speech Accessibility Project (SAP) research distribution.

Nothing here downloads data. SAP audio and transcripts are used only after the Data
Use Agreement is fully executed, from the official distribution unpacked locally at
SAP_DIR (default scripts/benchmark/data/sap, gitignored like TORGO).

Distribution layout, as read by SAP's own SplitTrainTest/new_split_code/reader.py:
  <split>/<speaker_id>.json   {"Etiology": ..., "Files": [{"Filename": ..., "Prompt": {"Transcript": ...}}]}
  <split>/<file>.wav          audio
The utterance id is the wav file name without extension; the speaker id is the part
before the first underscore.
"""

from __future__ import annotations

import io
import json
import os
import wave
from pathlib import Path
from typing import Iterator

from torgo import ROOT, Utterance

SAP_DIR = Path(os.environ.get("SAP_DIR", ROOT / "data" / "sap"))
SPLITS = ("train", "dev", "test1", "test2")


def split_dirs() -> list[tuple[str, Path]]:
    found = []
    for split in SPLITS:
        for name in (split, split[0].upper() + split[1:]):
            if (SAP_DIR / name).is_dir():
                found.append((split, SAP_DIR / name))
                break
    if not found:
        raise SystemExit(f"No SAP distribution found in {SAP_DIR}. Set SAP_DIR once the official data is available.")
    return found


def iter_utterances(splits: tuple[str, ...] = ("dev",)) -> Iterator[Utterance]:
    for split, directory in split_dirs():
        if split not in splits:
            continue
        for speaker_json in sorted(directory.glob("*.json")):
            data = json.loads(speaker_json.read_text(encoding="utf-8"))
            etiology = data.get("Etiology")
            if not etiology:
                raise ValueError(f"{speaker_json.name} has no Etiology")
            for entry in data.get("Files", []):
                filename = Path(entry["Filename"]).name
                transcript = (entry.get("Prompt") or {}).get("Transcript")
                if transcript is None:
                    raise ValueError(f"{filename} has no Transcript")
                wav_path = directory / filename
                with wave.open(str(wav_path)) as wav:
                    duration = wav.getnframes() / wav.getframerate()
                yield Utterance(
                    id=Path(filename).stem,
                    speaker=Path(filename).stem.split("_")[0],
                    status=etiology,
                    kind="sentence" if len(transcript.split()) > 1 else "word",
                    mic=split,
                    duration=round(duration, 3),
                    reference=transcript,
                )


def load_pcm(ids: set[str], splits: tuple[str, ...] = ("dev",)) -> dict[str, bytes]:
    """Raw 16 kHz mono 16-bit PCM. Other formats are refused, never silently resampled."""
    found: dict[str, bytes] = {}
    for split, directory in split_dirs():
        if split not in splits:
            continue
        for wav_path in directory.glob("*.wav"):
            if wav_path.stem not in ids:
                continue
            with wave.open(str(wav_path)) as wav:
                shape = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
                if shape != (16000, 1, 2):
                    raise ValueError(f"{wav_path.name}: expected 16 kHz mono 16-bit, got {shape}; add a documented conversion step first")
                found[wav_path.stem] = wav.readframes(wav.getnframes())
    missing = ids - found.keys()
    if missing:
        raise KeyError(f"{len(missing)} SAP ids not found, e.g. {sorted(missing)[:3]}")
    return found


def write_fake_distribution(target: Path, speakers: int = 3, per_speaker: int = 4) -> None:
    """Tiny synthetic distribution (silence, made-up text) to test the pipeline without real data."""
    etiologies = ["Parkinson's Disease", "ALS", "Cerebral Palsy", "Down Syndrome", "Stroke"]
    dev = target / "Dev"
    dev.mkdir(parents=True, exist_ok=True)
    for s in range(speakers):
        speaker = f"fake{s:04d}-0000-0000-0000-000000000000"
        files = []
        for u in range(per_speaker):
            name = f"{speaker}_{u}_{s}.wav"
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(bytes(16000))
            (dev / name).write_bytes(buffer.getvalue())
            files.append({"Filename": name, "Prompt": {"Transcript": "turn on the lights" if u % 2 else "hello"}})
        (dev / f"{speaker}.json").write_text(json.dumps({"Etiology": etiologies[s % len(etiologies)], "Files": files}), encoding="utf-8")
