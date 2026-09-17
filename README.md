# SynapVocal

> A realtime voice bridge for people with dysarthria: it hears what they say, offers what they may have meant, and speaks the sentence they confirm.

![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB)
![AssemblyAI Universal-3.5 Pro](https://img.shields.io/badge/AssemblyAI-Universal--3.5%20Pro-36b0aa)
![Gemini 3.7 Flash](https://img.shields.io/badge/Gemini-3.7%20Flash-4285F4)
![Deepgram Aura-2](https://img.shields.io/badge/Deepgram-Aura--2-13EF93)
![React Router 8.4](https://img.shields.io/badge/React%20Router-8.4-CA4245)

Built for the **AssemblyAI Voice Agent Hackathon** (lablab.ai, September 2026), Realtime Speech-to-Text path.

Live demo: not deployed yet. Local setup is below.

## Table of Contents

- [What it is](#what-it-is)
- [How to test](#how-to-test)
- [Architecture](#architecture)
- [Running locally](#running-locally)
- [Configuration](#configuration)
- [Results](#results)
- [What it does not claim](#what-it-does-not-claim)
- [Credits and licenses](#credits-and-licenses)
- [How this was built](#how-this-was-built)
- [License](#license)

## What it is

Dysarthria is a motor speech disorder. Speech comes out slow, slurred or broken,
so other people struggle to understand it, and so does speech recognition.

SynapVocal sits between the Speaker and the Listener:

1. **Hear.** The browser streams the microphone to AssemblyAI Universal-3.5 Pro in real time.
2. **Offer.** When a sentence ends, Gemini proposes what the Speaker most likely meant, plus two other readings. What was heard is always offered too.
3. **Confirm.** The Speaker picks one, or edits it. **Nothing is said aloud before they confirm.**
4. **Speak.** Deepgram Aura-2 says the confirmed sentence clearly to the Listener.

The confirmation step is the design, not a safety net. The benchmark below shows
why: an automatic correction is no more accurate than the raw transcript, but
letting the Speaker choose is.

## How to test

1. Run it locally (see below) and open `http://localhost:3310`.
2. Press **Start listening** and allow the microphone. The ring shows it is hearing you.
3. Speak an English sentence. Pause in the middle if you like, then press **I'm done speaking** or wait.
4. The sentence card shows **Heard** at once, then suggestions a few seconds later.
5. Pick the closest option or press **Edit**, then **Confirm and speak**.
6. `/status` shows both service versions and whether each key is configured, without revealing any key.

The AssemblyAI free plan allows 5 new streaming sessions per minute across all users.

## Architecture

```
Browser
  microphone -> AudioWorklet (16 kHz PCM) -> AssemblyAI streaming (one-time token)
  every other call goes to the frontend only
        |
frontrouter  React Router 8 + Radix Themes, the only public service
        |  server-side calls over the internal network
backpy  FastAPI, no public domain
  POST /api/stt/token         one-time AssemblyAI token, key stays on the server
  POST /api/bridge/interpret  Gemini 3.7 Flash, JSON schema, logged backoff on 429
  POST /api/tts/speak         Deepgram Aura-2, audio streamed through
  GET  /api/health            versions and which keys are configured
```

Choices worth knowing:

- **Audio goes straight from the browser to AssemblyAI**, one network hop fewer. The permanent key never reaches the browser.
- **One source of STT settings** ([`stt_config.py`](codes/backpy/app/stt_config.py)), loaded by both the product and the benchmark, so measurements describe what users get.
- **No database.** The server keeps no audio and no transcripts.
- **Gemini on the `global` endpoint.** Gemini 3 models are not served from `us-central1` for this project (404), and 429 there is transient shared capacity, retried with logged backoff.

```
codes/
  backpy/          FastAPI: stt, interpret, tts, health, tests
  frontrouter/     React Router app: Bridge page, voice ring, sentence cards
scripts/
  benchmark/       TORGO subset, STT and interpretation runs, scoring
docker-compose.yml local mirror of production: only the frontend is published
```

## Running locally

Requires Docker, plus `uv` and Node 24 for running tests outside containers.

1. Put keys in `credentials/` (gitignored, never committed): `assembly.txt`, `deepgram.txt`, and a Google Cloud service account key `gcp-synapvocal-backpy.json` with the Vertex AI User role.
2. Write the local `.env` from them:

```bash
python scripts/write-local-env.py
```

3. Start both services:

```bash
GIT_SHA=$(git rev-parse --short HEAD) docker compose up --build
```

4. Open `http://localhost:3310`.

Tests:

```bash
cd codes/backpy && uv run pytest
```

```bash
cd codes/frontrouter && npm run typecheck
```

## Configuration

| Variable | Service | Purpose |
|---|---|---|
| `ASSEMBLYAI_API_KEY` | backpy | issues one-time streaming tokens |
| `DEEPGRAM_API_KEY` | backpy | voice output |
| `GOOGLE_APPLICATION_CREDENTIALS` | backpy | path to the service account key, mounted read-only |
| `GOOGLE_CLOUD_PROJECT` | backpy | project that runs Gemini |
| `GOOGLE_CLOUD_LOCATION` | backpy | `global` |
| `GEMINI_MODEL` | backpy | `gemini-3.7-flash` |
| `BACKPY_INTERNAL_URL` | frontrouter | internal address of backpy, read server-side only |
| `GIT_SHA` | both | build version, shown on `/status` to prove what is deployed |

## Results

All numbers come from [`scripts/benchmark`](scripts/benchmark) on the
[TORGO database](#credits-and-licenses): a fixed subset of 695 head-microphone
utterances (seed 20260917), streamed at real time through the same settings the
product uses. Word error rate (WER) is corpus-level after normalising case and punctuation.

### Round A: speech recognition alone

| Group | Utterances | WER | Exactly right |
|---|---|---|---|
| Dysarthric, sentences | 296 | **0.400** | 42% |
| Dysarthric, single words | 120 | 0.833 | 33% |
| Control, sentences | 174 | 0.021 | 91% |
| Control, single words | 105 | 0.209 | 79% |

Per dysarthric speaker, sentence and word WER combined, the spread is wide:
M01 0.84, M04 0.80, F01 0.64, M02 0.61, M05 0.36, F03 0.11, F04 0.04, M03 0.01.

**Stability.** The same 60 utterances were run three times. Dysarthric WER came
back 0.465, 0.433 and 0.442, so differences under about 0.03 are noise and are not
reported as improvements.

### Round C0: does interpretation help?

Gemini read the 296 dysarthric sentence transcripts from round A.

| | Gemini 3.7 Flash | Gemini 3.8 Flash |
|---|---|---|
| WER of the suggestion alone (raw was 0.400) | 0.396 | 0.401 |
| WER if the Speaker picks the best option | **0.352** | 0.355 |
| Sentences exactly right, best option (raw: 124) | **141** | 140 |
| Latency p50 / p90 | 2.6 s / 5.6 s | 2.3 s / 8.4 s |

- **Automatic correction does not help.** With 3.7 Flash, 38 sentences got better and 40 got worse.
- **Choice does.** In 31 sentences (3.7 Flash) the best answer was an alternative, not the main suggestion.
- **3.7 Flash is used:** same quality as 3.8, with a much shorter latency tail.

Round B (recognition with a context prompt) is running and will be added.

## What it does not claim

- It does not diagnose anything and is not a medical device.
- It does not understand dysarthric speech better than speech recognition does. Suggestions are guesses, which is why the Speaker confirms every sentence.
- It is not trained on anyone's voice. No model is fine-tuned.
- English only.
- The "best option" numbers assume the Speaker recognises their own sentence. They are an upper bound, not a measured user result.
- TORGO sentences are read aloud and many are well known ("The quick brown fox..."). Free conversation will be harder.

## Credits and licenses

- **TORGO database**, used for evaluation only, under its academic, non-profit terms. No TORGO audio is in this repository.
  Rudzicz, F., Namasivayam, A.K., Wolff, T. (2012). The TORGO database of acoustic and articulatory speech from speakers with dysarthria. *Language Resources and Evaluation*, 46(4), 523 to 541.
  Via [abnerh/TORGO-database](https://huggingface.co/datasets/abnerh/TORGO-database); original at the [University of Toronto](https://www.cs.toronto.edu/~complingweb/data/TORGO/torgo.html).
- **AssemblyAI** Universal-3.5 Pro streaming speech-to-text.
- **Google Gemini** 3.7 Flash on Vertex AI, through `google-genai`.
- **Deepgram** Aura-2 text-to-speech.
- **FastAPI**, **uvicorn**, **httpx**, **pydantic**, **React Router**, **React**, **Radix Themes**, **Inter** (via Fontsource), **jiwer**, **pyarrow**: their respective open source licences.

## How this was built

A code assistant was used to speed up development and debugging. Design
decisions, measurements and claims were checked by hand against real runs.

Three findings changed the product:

- **Language must be pinned.** Without `language_codes=en`, one unclear dysarthric utterance came back in Mandarin.
- **Correction alone is not the value; choice is.** Round C0 turned an "AI fixes your speech" idea into a pick-and-confirm design.
- **Rate limits are part of the design.** The free AssemblyAI plan allows 5 new sessions per minute, so the benchmark is paced below it and stops on the first refusal instead of retrying.

## License

MIT, see [LICENSE](LICENSE).
