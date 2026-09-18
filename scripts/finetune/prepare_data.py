"""Write the TORGO split as parquet files for the SageMaker training job.

One file per split in scripts/finetune/data/ (gitignored). Columns: id, speaker,
status, kind, text (the TORGO reference as written), wav (16 kHz mono 16-bit, the
original bytes). The files go only to the private bucket of our own AWS account;
TORGO is never redistributed.

    uv run --no-sync --project scripts/benchmark python scripts/finetune/prepare_data.py
    uv run --no-sync --project scripts/benchmark python scripts/finetune/prepare_data.py --limit 8   # smoke
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import wave
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "benchmark"))

from torgo import DATA, iter_utterances  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", default=str(HERE / "manifest" / "torgo-split-v1.json"))
    parser.add_argument("--limit", type=int, default=0, help="keep only the first N ids per split, for a smoke test")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    splits = {name: ids[: args.limit] if args.limit else ids for name, ids in manifest["ids"].items()}
    split_of = {i: name for name, ids in splits.items() for i in ids}
    meta = {u.id: u for u in iter_utterances() if u.id in split_of}

    rows: dict[str, list[dict]] = {name: [] for name in splits}
    for shard in sorted(DATA.glob("train-*.parquet")):
        audio = pq.read_table(shard, columns=["audio"]).column("audio").combine_chunks()
        paths = audio.field("path").to_pylist()
        blobs = audio.field("bytes")
        for i, path in enumerate(paths):
            name = split_of.get(path)
            if name is None:
                continue
            data = blobs[i].as_py()
            with wave.open(io.BytesIO(data)) as wav:
                shape = (wav.getframerate(), wav.getnchannels(), wav.getsampwidth())
            if shape != (16000, 1, 2):
                raise ValueError(f"{path}: expected 16 kHz mono 16-bit, got {shape}")
            u = meta[path]
            rows[name].append(
                {"id": u.id, "speaker": u.speaker, "status": u.status, "kind": u.kind, "text": u.reference, "wav": data}
            )

    suffix = f"-smoke{args.limit}" if args.limit else ""
    out_dir = HERE / "data" / f"{manifest['version']}{suffix}"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, items in rows.items():
        missing = len(splits[name]) - len(items)
        if missing:
            raise KeyError(f"{name}: {missing} ids not found in the TORGO shards")
        items.sort(key=lambda r: r["id"])
        pq.write_table(pa.Table.from_pylist(items), out_dir / f"{name}.parquet")
        print(f"{name}: {len(items)} rows")
    print(f"wrote {out_dir}")


if __name__ == "__main__":
    main()
