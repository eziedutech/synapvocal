"""Count what is actually inside the downloaded TORGO shards.

Reads only the metadata columns plus each audio file name, never the audio
bytes, so it runs in seconds. The speaker, session and microphone live in the
file name (e.g. M02_1_headMic_0066.wav), not in a column.

    uv run python inventory.py
"""

from collections import Counter
from pathlib import Path
import re

import pyarrow.parquet as pq

DATA = Path(__file__).parent / "data"
NAME = re.compile(r"^(?P<speaker>[FM]C?\d+)_(?P<session>\d+)_(?P<mic>[A-Za-z]+)_(?P<utt>\d+)\.wav$")


def main() -> None:
    rows = 0
    unparsed: list[str] = []
    by_status = Counter()
    by_speaker = Counter()
    by_mic = Counter()
    by_kind = Counter()
    seconds = Counter()

    for shard in sorted(DATA.glob("train-*.parquet")):
        table = pq.read_table(shard, columns=["audio", "transcription", "speech_status", "duration"])
        paths = table.column("audio").combine_chunks().field("path").to_pylist()
        for path, text, status, duration in zip(
            paths,
            table.column("transcription").to_pylist(),
            table.column("speech_status").to_pylist(),
            table.column("duration").to_pylist(),
        ):
            rows += 1
            match = NAME.match(path or "")
            if not match:
                unparsed.append(path)
                continue
            kind = "sentence" if len(text.split()) > 1 else "word"
            by_status[status] += 1
            by_speaker[(match["speaker"], status)] += 1
            by_mic[(status, match["mic"])] += 1
            by_kind[(status, kind)] += 1
            seconds[(status, kind)] += duration

    print(f"rows: {rows}")
    print(f"unparsed file names: {len(unparsed)} {unparsed[:5]}")
    print("\nby status:", dict(by_status))
    print("\nby status and kind (count, hours):")
    for key in sorted(by_kind):
        print(f"  {key}: {by_kind[key]}, {seconds[key] / 3600:.2f} h")
    print("\nby status and mic:")
    for key in sorted(by_mic):
        print(f"  {key}: {by_mic[key]}")
    print("\nby speaker:")
    for (speaker, status), count in sorted(by_speaker.items()):
        print(f"  {speaker} ({status}): {count}")


if __name__ == "__main__":
    main()
