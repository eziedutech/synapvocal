# SynapVocal

> A realtime voice bridge for people whose speech is hard to understand, including dysarthria and the speech of people with Parkinson's disease, ALS, cerebral palsy, Down syndrome or stroke: it hears what they say, offers what they may have meant, and speaks the sentence they confirm.

![Python 3.14](https://img.shields.io/badge/Python-3.14-3776AB)
![AssemblyAI Universal-3.5 Pro](https://img.shields.io/badge/AssemblyAI-Universal--3.5%20Pro-36b0aa)
![Gemini 3.7 Flash](https://img.shields.io/badge/Gemini-3.7%20Flash-4285F4)
![Deepgram Aura-2](https://img.shields.io/badge/Deepgram-Aura--2-13EF93)
![React Router 8.4](https://img.shields.io/badge/React%20Router-8.4-CA4245)

Built for the **AssemblyAI Voice Agent Hackathon** (lablab.ai, September 2026), Realtime Speech-to-Text path.

Live demo: [synap.eziedutech.dev](https://synap.eziedutech.dev). Local setup is below.

## Table of Contents

- [What it is](#what-it-is)
- [Who it is for](#who-it-is-for)
- [How to test](#how-to-test)
- [Architecture](#architecture)
- [Running locally](#running-locally)
- [Configuration](#configuration)
- [Contributing recordings](#contributing-recordings)
- [Results](#results)
- [What it does not claim](#what-it-does-not-claim)
- [Credits and licenses](#credits-and-licenses)
- [How this was built](#how-this-was-built)
- [License](#license)

## What it is

Some conditions make speech slow, slurred, strained or broken. Dysarthria, a motor
speech disorder, is the most common reason, and it is one of several. When that
happens other people struggle to understand, and so does speech recognition.

SynapVocal sits between the Speaker and the Listener:

1. **Hear.** The browser streams the microphone to AssemblyAI Universal-3.5 Pro in real time.
2. **Offer.** When a sentence ends, Gemini listens to that sentence's audio, reads the transcript and the Speaker's earlier sentences, and proposes what they most likely meant, plus two other readings. What was heard is always offered too.
3. **Confirm.** The Speaker picks one, or edits it. **Nothing is said aloud before they confirm.**
4. **Speak.** Deepgram Aura-2 says the confirmed sentence clearly to the Listener.

The confirmation step is the design, not a safety net. On every unique dysarthric
sentence in TORGO, the Speaker's best option was exactly right for 418 of 681
sentences, against 324 for speech recognition alone, and even the best suggestion
is still a guess.

## Who it is for

SynapVocal focuses on the conditions covered by the two speech corpora it is built
and evaluated around:

| Condition | TORGO | Speech Accessibility Project (SAP) |
|---|---|---|
| Dysarthria | Yes: 8 speakers, from cerebral palsy or ALS | Yes, across the conditions below |
| Cerebral palsy | Yes | Yes |
| Amyotrophic lateral sclerosis (ALS) | Yes | Yes |
| Parkinson's disease | | Yes |
| Down syndrome | | Yes |
| Stroke | | Yes |

**Measured so far: dysarthria, on TORGO.** Every number in [Results](#results) comes
from TORGO speakers with dysarthria from cerebral palsy or ALS. Access to the SAP
corpus has been requested; the conditions it adds are part of the design and will
be reported per condition once they are measured, not before.

## How to test

1. Run it locally (see below) and open `http://localhost:3310`.
2. Press **Start with Microphone** and allow the microphone, or **Start with TORGO Example** to hear a real dysarthric recording go through the app, or **Start with Your Audio File** to use your own recording (up to 60 s). Files are streamed at real time, exactly like the microphone.
3. Speak an English sentence. Pause in the middle if you like, then press **End sentence** or wait.
4. The sentence card shows what was heard (ear icon) at once, then suggestions a few seconds later.
5. Pick the closest option, tap a single wrong word to swap it, or press **Edit**. If nothing is close, press **Say it again** and repeat the sentence. Then **Confirm and speak**.
6. `/benchmark` shows the measured results; `/status` shows both service versions and which keys are configured, without revealing any.

Optional: **Contribute** lets a signed-in person who agrees to it save recordings of sentences they choose, in a separate contribution session. The Bridge itself stores nothing.

## Architecture

```
Browser
  microphone -> AudioWorklet (16 kHz PCM) -> AssemblyAI streaming (one-time token)
  every other call goes to the frontend only
        |
frontrouter  React Router 8 + Radix Themes, the only public service
        |  per-visitor rate limits, Firebase sign-in check, session cookie
        |  server-side calls over the internal network
backpy  FastAPI, no public domain
  POST /api/stt/token         one-time AssemblyAI token, key stays on the server
  POST /api/bridge/interpret  Gemini 3.7 Flash with the sentence audio, JSON schema,
                              logged backoff, falls back to 3.5 Flash-Lite
  POST /api/tts/speak         Deepgram Aura-2, audio streamed through
  /api/users, /api/me, /api/contributions   voluntary contributions (Postgres + S3)
  GET  /api/health            versions and which keys are configured
```

Choices worth knowing:

- **Audio goes straight from the browser to AssemblyAI**, one network hop fewer. The permanent key never reaches the browser.
- **One source of STT settings** ([`stt_config.py`](codes/backpy/app/stt_config.py)), loaded by both the product and the benchmark, so measurements describe what users get.
- **The Bridge stores nothing.** Sentence audio is held in the page's memory, sent to Gemini to interpret it, and dropped. Only a signed-in contributor, in a contribution session, can choose to save a recording.
- **Gemini on the `global` endpoint.** Gemini 3 models are not served from `us-central1` for this project (404). 429 and 504 there are transient shared capacity: one logged retry, then Gemini 3.5 Flash-Lite, which has its own capacity.
- **Rate limits per visitor** on every route that spends paid credit, so the demo cannot be drained by a script.

```
codes/
  backpy/          FastAPI: stt, interpret, tts, contributions, health, migrations, tests
  frontrouter/     React Router app: Bridge, contribution session, benchmark, status
scripts/
  benchmark/       TORGO subsets, STT and interpretation runs, scoring
  finetune/        TORGO split and Whisper LoRA training on SageMaker (in progress)
docker-compose.yml local mirror of production: only the frontend is published
```

## Running locally

Requires Docker, plus `uv` and Node 24 for running tests outside containers.

1. Put keys in `credentials/` (gitignored, never committed): `assembly.txt`, `deepgram.txt`, and a Google Cloud service account key `gcp-synapvocal-backpy.json` with the Vertex AI User role.
2. Write the local `.env` from them:

```bash
python scripts/write-local-env.py
```

   For sign-in, also add the Firebase web config as `firebase-conf.txt`; without it the Bridge works and contributions stay off.

3. Start the services (Postgres for contributions starts with them):

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
| `GEMINI_FALLBACK_MODEL` | backpy | `gemini-3.5-flash-lite`, used when the main model fails; empty turns it off |
| `DATABASE_URL` | backpy | Postgres for contributions, `postgresql+asyncpg://...` |
| `STORAGE_BACKEND`, `S3_BUCKET`, `S3_REGION`, `S3_PREFIX` | backpy | where contributed recordings go (`s3`, or `local` in development) |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | backpy | S3 access for contributed recordings |
| `INTERNAL_API_TOKEN` | both | proves to backpy that a contribution call comes from frontrouter |
| `SESSION_SECRET` | frontrouter | signs the contributor session cookie |
| `FIREBASE_API_KEY`, `FIREBASE_AUTH_DOMAIN`, `FIREBASE_PROJECT_ID`, `FIREBASE_APP_ID` | frontrouter | Google sign-in through Firebase (public values) |
| `BACKPY_INTERNAL_URL` | frontrouter | internal address of backpy, read server-side only |
| `GIT_SHA` | both | build version, shown on `/status` to prove what is deployed |

Everything for contributions is optional: without it those routes answer 503 and the Bridge is unchanged.

## Contributing recordings

Speech recognition hears people with dysarthria badly because it has rarely heard
them. Recordings paired with the sentence the speaker confirmed are the most useful
data there is, and there is very little of it. So SynapVocal lets people give it,
if they choose to:

1. Sign in with Google and read the consent page. Nothing is collected before agreeing (18 or older).
2. Open a **contribution session**. It looks like the Bridge but is marked as a contribution session, so it is never confused with it.
3. After confirming a sentence, choose **Contribute** or **Skip**, and say whether it is exactly what was said.
4. See, delete, withdraw consent or delete the account at any time on the Contribute page.

Recordings are stored encrypted in private cloud storage under random ids; account details
and sentence texts stay in a database on our own server. They are never published or shared.

## Results

All numbers come from [`scripts/benchmark`](scripts/benchmark) on the
[TORGO database](#credits-and-licenses), streamed at real time through the same
settings the product uses. Word error rate (WER) is corpus-level after normalising
case and punctuation. The same numbers, as charts, are on the `/benchmark` page.

### Larger pilot: every unique dysarthric sentence

681 sentences, one per speaker and text (head microphone), with Gemini 3.7 Flash.
AssemblyAI alone: WER **0.317**, 324 exactly right.

| What Gemini receives | First suggestion WER | Speaker picks best | Exactly right (best) | Wait p50 / p90 |
|---|---|---|---|---|
| Transcript only | 0.337 | 0.282 | 354 | 3.0 s / 11.8 s |
| Transcript + audio | 0.264 | 0.231 | 395 | 3.8 s / 8.4 s |
| Transcript + audio + 5 earlier sentences (**the app**) | **0.231** | **0.198** | **418** (61%) | 4.4 s / 23.1 s |

- **From text alone, the first suggestion is slightly worse than AssemblyAI.** Hearing the audio is what makes it better, and the same person's earlier sentences help again.
- **The app uses the last setup:** each sentence's audio goes to Gemini with the transcript and the Speaker's earlier sentences in this session.
- **Severe speech stays hard.** For the speakers with the most errors (M04, M01, F01) most sentences are still not exactly right. The ear-marked option and editing matter most for them.
- The slow tail (p90 23 s) is Gemini's shared capacity being busy; the heard text is usable meanwhile.

### Saying it again (round D)

TORGO has 51 dysarthric sentences that a speaker really recorded twice (21 from M04,
the hardest speaker). Same setup as the app, one try against both:

| Input | First suggestion WER | Speaker picks best | Exactly right (best) | Close |
|---|---|---|---|---|
| One try (the app without Say it again) | 0.358 | 0.317 | 21 of 51 | 27 |
| Second try alone | 0.400 | 0.298 | 27 of 51 | 29 |
| **Both tries together (Say it again)** | **0.269** | **0.211** | **28 of 51** | **35** |

Combining the tries is what helps, not only having a second one. The set is small, so
this is a direction rather than a precise figure. It is why the app has **Say it again**.

**Tried and not used.** A second prompt that adds AssemblyAI's per-word confidence and
asks for three alternatives was tuned on one half of the pilot and lost there (best-choice
WER 0.214 against 0.196), so it was never run on the other half and the app keeps the first.

### First round: a fixed subset of 695 utterances

A fixed subset of 695 head-microphone utterances (seed 20260917).

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

**Round B.** A context prompt for AssemblyAI ("the speaker may have dysarthria")
gave WER 0.400 on the same sentences: no change.

**Round C0: text-only interpretation.** Gemini read the 296 dysarthric sentence transcripts from round A.

| | Gemini 3.7 Flash | Gemini 3.8 Flash |
|---|---|---|
| WER of the suggestion alone (raw was 0.400) | 0.396 | 0.401 |
| WER if the Speaker picks the best option | **0.352** | 0.355 |
| Sentences exactly right, best option (raw: 124) | **141** | 140 |
| Latency p50 / p90 | 2.6 s / 5.6 s | 2.3 s / 8.4 s |

- **Automatic correction does not help.** With 3.7 Flash, 38 sentences got better and 40 got worse.
- **Choice does.** In 31 sentences (3.7 Flash) the best answer was an alternative, not the main suggestion.
- **3.7 Flash is used:** same quality as 3.8, with a much shorter latency tail.


## What it does not claim

- It does not diagnose anything and is not a medical device.
- Suggestions are guesses and can be wrong, which is why the Speaker confirms every sentence.
- Results are measured on dysarthria (TORGO) only. Parkinson's disease, Down syndrome and stroke are not measured yet, and no claim is made for them until they are.
- The app does not use a model trained on anyone's voice. A Whisper fine-tune on TORGO is in progress and will be reported only once measured on speakers it has never heard.
- English only.
- The "best option" numbers assume the Speaker recognises their own sentence. They are an upper bound, not a measured user result.
- TORGO sentences are read aloud and many are well known ("The quick brown fox..."). Free conversation will be harder.

## Credits and licenses

- **TORGO database**, under its academic, non-profit terms. Used for evaluation; nine short sentence recordings are included as the app's examples (`codes/frontrouter/public/examples/torgo`), with this citation shown beside them.
  Rudzicz, F., Namasivayam, A.K., Wolff, T. (2012). The TORGO database of acoustic and articulatory speech from speakers with dysarthria. *Language Resources and Evaluation*, 46(4), 523 to 541.
  Via [abnerh/TORGO-database](https://huggingface.co/datasets/abnerh/TORGO-database); original at the [University of Toronto](https://www.cs.toronto.edu/~complingweb/data/TORGO/torgo.html).
- **AssemblyAI** Universal-3.5 Pro streaming speech-to-text.
- **Google Gemini** 3.7 Flash and 3.5 Flash-Lite on Vertex AI, through `google-genai`.
- **Firebase Authentication** for Google sign-in (contributors only).
- **Deepgram** Aura-2 text-to-speech.
- **FastAPI**, **uvicorn**, **httpx**, **pydantic**, **SQLAlchemy**, **Alembic**, **asyncpg**, **boto3**, **PostgreSQL**, **React Router**, **React**, **Radix Themes**, **jose**, **Inter** (via Fontsource), **jiwer**, **pyarrow**: their respective open source licences. The ear icon is from **Lucide** (ISC).

## How this was built

A code assistant was used to speed up development and debugging. Design
decisions, measurements and claims were checked by hand against real runs.

Three findings changed the product:

- **Language must be pinned.** Without `language_codes=en`, one unclear dysarthric utterance came back in Mandarin.
- **Correction alone is not the value; choice is.** Round C0 turned an "AI fixes your speech" idea into a pick-and-confirm design.
- **Let the model hear, not only read.** Sending each sentence's audio with the transcript took the suggestion from worse than AssemblyAI to clearly better.
- **Rate limits are part of the design.** Benchmark runs are paced below each provider's limits and stop on the first refusal instead of retrying; the public app limits each visitor.

## License

MIT, see [LICENSE](LICENSE).
