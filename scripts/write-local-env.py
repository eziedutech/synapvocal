"""Write the root .env used by docker compose from the files in credentials/.

Only key names and whether each was found are printed, never the values.
Existing lines in .env that this script does not own are kept as they are.

    python scripts/write-local-env.py
"""

from pathlib import Path
import re
import secrets
import sys

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

# env name -> credentials file
SOURCES = {
    "ASSEMBLYAI_API_KEY": "assembly.txt",
    "DEEPGRAM_API_KEY": "deepgram.txt",
}

# Local secrets with no outside source: generated once, then kept on later runs.
GENERATED = ("INTERNAL_API_TOKEN", "SESSION_SECRET")

# Firebase web app config for contributor sign-in, as copied from the Firebase console.
# These values are public by design (they are sent to the browser); no admin key is used.
FIREBASE_FILE = "firebase-conf.txt"
FIREBASE_KEYS = {"apiKey": "FIREBASE_API_KEY", "authDomain": "FIREBASE_AUTH_DOMAIN", "projectId": "FIREBASE_PROJECT_ID", "appId": "FIREBASE_APP_ID"}


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

    firebase = ROOT / "credentials" / FIREBASE_FILE
    text = firebase.read_text(encoding="utf-8") if firebase.is_file() else ""
    for key, name in FIREBASE_KEYS.items():
        found = re.search(rf'{key}:\s*"([^"]+)"', text)
        if found:
            values[name] = found.group(1)
        else:
            missing.append(f"{name} (credentials/{FIREBASE_FILE} missing or has no {key}; sign-in stays off)")

    existing = {}
    kept = []
    owned = set(SOURCES) | set(GENERATED) | set(FIREBASE_KEYS.values()) | {"GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"}
    if ENV_PATH.is_file():
        for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
            name = line.split("=", 1)[0].strip()
            if name in owned:
                existing[name] = line.split("=", 1)[1] if "=" in line else ""
            else:
                kept.append(line)
    for name in GENERATED:
        values[name] = existing.get(name) or secrets.token_urlsafe(48)

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
