"""Shared helpers for reading the local TORGO shards."""

from __future__ import annotations

import io
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pyarrow.parquet as pq

ROOT = Path(__file__).parent
DATA = ROOT / "data"
NAME = re.compile(r"^(?P<speaker>[FM]C?\d+)_(?P<session>\d+)_(?P<mic>[A-Za-z]+)_(?P<utt>\d+)\.wav$")


@dataclass(frozen=True)
class Utterance:
    id: str  # audio file name, unique in the dataset
    speaker: str
    status: str  # "dysarthria" or "healthy"
    kind: str  # "sentence" or "word"
    mic: str
    duration: float
    reference: str


def iter_utterances() -> Iterator[Utterance]:
    for shard in sorted(DATA.glob("train-*.parquet")):
        table = pq.read_table(shard, columns=["audio", "transcription", "speech_status", "duration"])
        paths = table.column("audio").combine_chunks().field("path").to_pylist()
        for path, text, status, duration in zip(
            paths,
            table.column("transcription").to_pylist(),
            table.column("speech_status").to_pylist(),
            table.column("duration").to_pylist(),
        ):
            match = NAME.match(path)
            if not match:
                raise ValueError(f"unexpected audio file name: {path!r}")
            yield Utterance(
                id=path,
                speaker=match["speaker"],
                status=status,
                kind="sentence" if len(text.split()) > 1 else "word",
                mic=match["mic"],
                duration=duration,
                reference=text,
            )


def load_pcm(ids: set[str]) -> dict[str, bytes]:
    """Return raw 16 kHz mono 16-bit PCM for the given ids. Refuses any other format."""
    found: dict[str, bytes] = {}
    for shard in sorted(DATA.glob("train-*.parquet")):
        audio = pq.read_table(shard, columns=["audio"]).column("audio").combine_chunks()
        paths = audio.field("path").to_pylist()
        wanted = [i for i, path in enumerate(paths) if path in ids]
        if not wanted:
            continue
        blobs = audio.field("bytes")
        for i in wanted:
            with wave.open(io.BytesIO(blobs[i].as_py())) as wav:
                shape = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
                if shape != (16000, 1, 2):
                    raise ValueError(f"{paths[i]}: expected 16 kHz mono 16-bit, got {shape}")
                found[paths[i]] = wav.readframes(wav.getnframes())
    missing = ids - found.keys()
    if missing:
        raise KeyError(f"{len(missing)} ids not found in shards, e.g. {sorted(missing)[:3]}")
    return found
