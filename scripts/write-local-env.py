"""Write the root .env used by docker compose from the files in credentials/.

Only key names and whether each was found are printed, never the values.
Existing lines in .env that this script does not own are kept as they are.

    python scripts/write-local-env.py
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# env name -> credentials file
SOURCES = {
    "ASSEMBLYAI_API_KEY": "assembly.txt",
    "DEEPGRAM_API_KEY": "deepgram.txt",
}


def main() -> int:
    values: dict[str, str] = {}
    missing: list[str] = []
    for name, filename in SOURCES.items():
        path = ROOT / "credentials" / filename
        value = path.read_text(encoding="utf-8").strip() if path.is_file() else ""
        if not value or any(c.isspace() for c in value):
            missing.append(f"{name} (credentials/{filename} missing, empty, or contains whitespace)")
            continue
        values[name] = value

    kept = []
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.split("=", 1)[0].strip() not in SOURCES:
                kept.append(line)

    lines = kept + [f"{name}={value}" for name, value in values.items()]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Read back to prove the write, rather than trusting the absence of an error.
    written = {
        line.split("=", 1)[0]: line.split("=", 1)[1]
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines()
        if "=" in line
    }
    for name in values:
        status = "ok" if written.get(name) == values[name] else "MISMATCH"
        print(f"{name}: {status}")
    for item in missing:
        print(f"NOT WRITTEN: {item}")

    return 1 if missing or any(written.get(n) != v for n, v in values.items()) else 0


if __name__ == "__main__":
    sys.exit(main())
