# SynapVocal

**A confirm-before-speak voice bridge for people whose speech is hard to understand**

Muhammad Zia ul Haq, EZI Edutech Dev
Built for the AssemblyAI Voice Agent Hackathon, lablab.ai, September 2026
Live: [synap.eziedutech.dev](https://synap.eziedutech.dev) · Code: [github.com/eziedutech/synapvocal](https://github.com/eziedutech/synapvocal)

---

## Abstract

Speech recognition has become accurate enough to be invisible, but only for people
whose speech it has heard before. On the TORGO database of dysarthric speech, a
current production streaming recogniser gets 40% of words wrong on sentences from
speakers with dysarthria, against 2% for control speakers in the same recording
sessions. The people who would gain the most from speech interfaces are the ones
they serve worst.

SynapVocal does not try to close that gap by correcting speech automatically. We
measured that approach and it does not work: asked to repair a dysarthric
transcript from text alone, a strong language model made 58 sentences better and
117 worse, and its output was less accurate than the raw transcript. What works is
a different division of labour. The machine proposes, the speaker decides, and
nothing is spoken aloud until the speaker confirms it.

Three design choices, each adopted only after it was measured, carry the result.
Letting the model **hear the sentence** instead of only reading its transcript.
Giving it the **speaker's own earlier sentences** in the same session. And
**offering a choice** rather than a correction, because on 31 of 296 sentences the
best answer was an alternative the model ranked second or third.

On every unique dysarthric sentence in TORGO (680 sentences, 8 speakers), streamed
in real time through the settings the deployed app uses: AssemblyAI Universal-3.6
Pro alone reaches word error rate 0.299 with 324 sentences exactly right. With
SynapVocal's suggestions the first suggestion reaches 0.220, and when the speaker
picks the best of the four options offered, 0.185 with 426 sentences exactly right,
a 38% relative reduction in word error rate and 102 more sentences recovered word
for word. Median wait for a suggestion is 3.8 s.

The system is deployed and public. This paper describes what it does, how it was
measured, what was tried and discarded, and what it does not claim.

---

## 1. The problem

Dysarthria is a motor speech disorder: the muscles used for speech are weak, slow
or poorly coordinated, so speech becomes slurred, strained, quiet or broken. It is
a consequence, not a disease, and it follows cerebral palsy, amyotrophic lateral
sclerosis, Parkinson's disease, stroke, traumatic brain injury and other
conditions. Intelligence and intent are unaffected. What is affected is being
understood.

Two things follow, and the second is less obvious than the first.

**People struggle to understand.** Listeners who know the speaker adapt; strangers
do not. A pharmacist, a taxi driver, a nurse on a first shift, all of them ask the
speaker to repeat, then guess, then turn to whoever came along. The speaker's
autonomy narrows to the set of people who have learned their voice.

**Machines struggle more.** Voice assistants, dictation and phone menus are trained
on speech that is already easy to understand. On the TORGO database, in the same
recording sessions with the same microphone and the same read sentences, a current
streaming recogniser reaches word error rate 0.021 for control speakers and 0.398
for speakers with dysarthria, a factor of nineteen. The technology that is
supposed to widen access is itself a barrier, and the gap is widening as everything
else becomes voice-first.

The obvious response is to train a better recogniser. That is worth doing and is
part of our roadmap, but it is a years-long, data-hungry effort in a domain where
data is scarce by construction: recording people with progressive conditions is
slow, tiring for them, and rightly constrained by consent. SynapVocal asks a
narrower question. **Given a recogniser that gets 40% of words wrong, can a useful
tool be built today?**

---

## 2. Design principles

Four commitments shaped every decision, and each of them cost something.

**The speaker confirms. Always.** A system that guesses what a disabled person
meant and says it aloud in their name is not an accessibility tool, it is a
ventriloquist. Every sentence passes through an explicit confirmation before any
audio is produced. This costs a tap and a few seconds, and it is not a safety net
bolted on afterwards: it is the reason the numbers below are usable at all, because
it converts a bad automatic answer into a good assisted one.

**Offer, do not overwrite.** What the recogniser heard is always one of the
options, marked with an ear icon, and it is presented first. We considered
replacing it with the model's best suggestion and measured that this would be
worse (Section 6.1).

**Measure before claiming.** Every design choice in this paper was decided by a
benchmark run on real dysarthric recordings, streamed in real time through exactly
the settings the deployed product uses. Product and benchmark read their speech
recognition settings from one shared file, so a measurement always describes what a
user gets. Three features were measured and rejected.

**Say plainly what is not covered.** The deployed app, its README and its benchmark
page each carry a "what this does not claim" section. Results are on dysarthria in
one corpus, in English, on read sentences. Everything else is unmeasured, and
unmeasured is stated as unmeasured.

---

## 3. The system

### 3.1 The four steps

1. **Hear.** The browser captures the microphone at 16 kHz through an AudioWorklet
   and streams raw PCM directly to AssemblyAI Universal-3.6 Pro over a WebSocket,
   using a one-time token minted server-side. The permanent API key never reaches
   the browser, and the audio takes one network hop fewer than it would through our
   own backend. Partial transcripts appear as the person speaks.

   The recogniser ends a turn after 400 ms of silence, and dysarthric speech pauses
   where fluent speech does not: on the TORGO pilot, 119 of 682 sentences came back
   as more than one turn. A turn therefore extends the sentence already open rather
   than starting a new one, and the sentence closes when nothing further has arrived
   or when the speaker presses **End sentence**. This matches how the benchmark
   scores a recording, where every turn of one utterance is one sentence. Interpreting
   a fragment on its own invites a confident answer about nothing that was said.

2. **Offer.** When a sentence closes, the backend sends Gemini 3.7 Flash three
   things: the audio of that sentence, the transcript AssemblyAI produced, and the
   last five sentences this speaker already confirmed in this session. Gemini
   returns a most-likely reading plus two alternatives, each with a confidence band
   rendered as Likely, Possible or Unsure, under a strict JSON schema.

3. **Confirm.** The sentence card shows what was heard immediately, with the
   suggestions arriving a few seconds later underneath. The speaker picks one, taps
   a single wrong word to swap it, edits freely, or presses **Say it again** to
   repeat the sentence and have both attempts interpreted together. **Nothing is
   spoken before this step.**

4. **Speak.** Deepgram Aura-2 says the confirmed sentence aloud in a clear voice.

### 3.2 Two features that exist because of a measurement

**Say it again.** Repeating a sentence is the natural human repair strategy, and we
measured whether it helps a machine. On the 51 TORGO sentences a speaker genuinely
recorded twice, the first attempt alone yields best-choice WER 0.317 and 21 exact
sentences; the second attempt alone yields 0.298 and 27; **both attempts
interpreted together** yield 0.211 and 28 exact, with 35 close. Combining the
tries is what helps, not merely having a second one, so the feature sends both
recordings and both transcripts rather than replacing the first.

**Fix a word.** Severe dysarthria often produces a transcript that is right except
for one word. Rewriting a whole sentence to fix one word is a heavy interaction for
someone whose motor control is already the constraint, so the words of the chosen
sentence are individually tappable, and tapping one offers the alternatives the
other candidates proposed in that position.

### 3.3 Architecture

![SynapVocal architecture: the browser streams 16 kHz PCM straight to AssemblyAI with a one-time token, while every other call goes through frontrouter, the only service with a domain, to backpy, which holds every key and calls Gemini, Deepgram and the contribution store.](../assets/architecture.svg)

Four properties are worth stating explicitly, because each was a deliberate
decision rather than a default.

- **Only the frontend is public.** The FastAPI service has no domain. Every key
  lives there, and `/api/health` reports which keys are configured without
  revealing any.
- **The Bridge stores nothing.** Sentence audio lives in the page's memory, goes to
  Gemini to be interpreted, and is dropped. Only a signed-in contributor, inside an
  explicitly marked contribution session, can choose to save a recording.
- **Failure is never silent.** Gemini's `global` endpoint returns 429 and 504 under
  shared load. Each retry is logged with its delay, and after the retries the call
  falls back to Gemini 3.5 Flash-Lite, which draws on separate capacity. A
  suggestion that never arrives says so on the card; the heard text stays usable.
- **Rate limits are part of the design.** Every route that spends paid credit is
  limited per visitor, with a global ceiling on new speech recognition sessions per
  hour, so a public demo cannot be drained by a script.

---

## 4. How it was measured

### 4.1 Corpus

The **TORGO database** (Rudzicz, Namasivayam and Wolff, 2012) holds 16,552
utterances, about 13.7 hours, from 8 speakers with dysarthria arising from cerebral
palsy or ALS and 7 control speakers, recorded with both a head-mounted and an array
microphone. It is used here for evaluation only, under its academic and non-profit
terms, and its audio is not redistributed. Nine short clips appear in the app as
examples, with the citation shown beside them.

Two properties of TORGO shape the method. Speaker identity lives in the filename
rather than a column, so per-speaker analysis is possible. And a single utterance
is typically recorded by two microphones at once, so one microphone must be chosen
per run or every utterance is counted twice. All runs use the head microphone.

Two evaluation sets were used. A **first round** of 695 head-microphone utterances
sampled with a fixed seed, split into dysarthric and control, sentences and single
words. A **pilot** covering every unique dysarthric sentence in the corpus, 682
sentences, one recording per speaker and text, which is the set all headline numbers
come from.

### 4.2 Protocol

Audio is streamed at real time over a WebSocket, not uploaded as a file, through
the identical settings the product uses, loaded from the same shared configuration
module. Word error rate is corpus-level, after normalising case, punctuation and
digits, and after accepting British and American spellings of the same word
(grey/gray, aluminium/aluminum, colour, honour, humour), since TORGO's prompts use
one and the recogniser returns the other.

Four figures are reported throughout:

- **WER of the recogniser alone**, the baseline.
- **WER of the first suggestion**, what the speaker sees at the top.
- **WER when the speaker picks the best option** among what was heard and the three
  suggestions. This is an **upper bound**: it assumes the speaker recognises their
  own sentence when they see it. It is not a user study, and it is labelled as an
  upper bound wherever it appears in the product.
- **Latency**, p50 and p90, from a closed sentence to suggestions on screen,
  including time spent waiting out provider congestion.

"Exactly right" means word for word after normalisation. "Close" means at most one
word in five is wrong.

### 4.3 Is the measurement stable?

Sixty utterances were streamed three times under identical settings. Control
speakers came back identical every time (0.014). Dysarthric results came back
0.461, 0.428 and 0.437. **Differences under about 0.03 are therefore run-to-run
noise and are not reported as improvements anywhere in this paper or in the
product.** A handful of hard utterances that the recogniser guesses differently on
each pass account for the whole spread.

---

## 5. Results

### 5.1 The gap this project exists for

First round, 695 utterances, AssemblyAI streaming alone:

| Group | Utterances | WER | Exactly right |
|---|---|---|---|
| Dysarthric, sentences | 296 | **0.398** | 43% |
| Dysarthric, single words | 120 | 0.833 | 33% |
| Control, sentences | 174 | 0.021 | 91% |
| Control, single words | 105 | 0.209 | 79% |

Single words are harder for everyone, because one misheard word is a 100% error for
that utterance and there is no context to recover from. The nineteenfold gap
between dysarthric and control sentences is the problem statement of this project,
measured in the same sessions with the same equipment.

**Averages hide the people.** Per speaker, sentences and words combined:

| Speaker | M03 | F04 | F03 | M05 | M02 | F01 | M04 | M01 |
|---|---|---|---|---|---|---|---|---|
| WER | 0.014 | 0.043 | 0.104 | 0.356 | 0.605 | 0.643 | 0.793 | 0.843 |

For three speakers the recogniser is already nearly perfect. For four it misses
more than half of every sentence. Any single average describes none of them, which
is why every chart in the product reports per speaker as well.

### 5.2 What the model needs in order to help

Pilot, every unique dysarthric sentence, Gemini 3.7 Flash, each row differing only
in what Gemini receives:

| Gemini receives | First suggestion | Speaker picks best | Exactly right | Close | p50 | p90 |
|---|---|---|---|---|---|---|
| Nothing (AssemblyAI alone) | 0.317 | | 324 of 681 | 396 | | |
| Transcript only | 0.337 | 0.282 | 354 | 420 | 3.0 s | 11.8 s |
| Transcript + audio | 0.264 | 0.231 | 395 | 460 | 3.8 s | 8.4 s |
| Transcript + audio + 5 earlier sentences | 0.231 | 0.198 | 418 | 484 | 4.4 s | 23.1 s |
| **Same, on Universal-3.6 Pro transcripts (the app)** | **0.220** | **0.185** | **426 of 680** | **502** | **3.8 s** | **17.9 s** |

Three findings, in the order they changed the product.

**Text-only correction is worse than doing nothing.** The first suggestion from the
transcript alone scores 0.337 against a 0.317 baseline, and drops exact sentences
from 324 to 314: it improved 58 sentences and damaged 117. This is the single most
important negative result in the project. A language model reading a mangled
transcript has no evidence about what was actually said; it has a prior over
English sentences, and it regularises toward fluent text that the speaker did not
utter. **The original plan was an "AI that fixes your speech." This measurement
ended it.**

**Hearing the audio is what makes the difference.** The same model, same prompt,
with the sentence's audio attached, moves the first suggestion from 0.337 to 0.264
and from 314 exact to 364, crossing from worse-than-baseline to clearly better. The
acoustic evidence the recogniser discarded when it committed to a transcript is
still in the audio, and the model can use it.

**The speaker's own earlier sentences help again.** Five confirmed sentences of
context move the first suggestion from 0.264 to 0.231. Part of this is topic, and
part is that the model sees how this particular speaker's articulation maps to
words, from examples the speaker themselves validated minutes earlier. This is
per-speaker adaptation without training anything.

**Choice is worth as much as the suggestion.** In the first round, on 31 of 296
sentences the best available answer was an alternative rather than the main
suggestion. Across the pilot, the gap between the first suggestion and the
speaker's best choice is consistently 0.03 to 0.05 WER and 25 to 40 sentences. An
interface that showed only the top answer would throw that away.

### 5.3 The deployed system, end to end

680 unique dysarthric TORGO sentences, AssemblyAI Universal-3.6 Pro streaming plus
Gemini 3.7 Flash with sentence audio and five sentences of history, which is the
deployed configuration:

| | AssemblyAI alone | SynapVocal, first suggestion | SynapVocal, speaker picks best |
|---|---|---|---|
| Word error rate | 0.299 | 0.220 | **0.185** |
| Exactly right | 324 (48%) | 401 (59%) | **426 (63%)** |
| Close | 403 (59%) | | **502 (74%)** |

**Relative reduction in word error rate: 26% for the first suggestion, 38% for the
speaker's best choice. 102 more sentences are recovered word for word.** Median
wait for suggestions is 3.8 s, p90 17.9 s, with the heard text usable throughout.

### 5.4 Choosing the recogniser, on the speakers who need it

Before moving the product to AssemblyAI's newest streaming model, we compared four
settings on the 165 pilot sentences of the three hardest speakers (M04, M01, F01),
the same sentences in each setting:

| Setting | WER | Exactly right | Sentences split at a pause |
|---|---|---|---|
| Universal-3.5 Pro, no prompt | 0.744 | 14 | 64 |
| 3.5 Pro + prompt describing dysarthric speech | 0.756 | 11 | 59 |
| **Universal-3.6 Pro, no prompt** | **0.724** | 11 | **53** |
| 3.6 Pro + the same prompt | 0.766 | 7 | 51 |

The newer model heard these speakers slightly better and, more usefully, split 17%
fewer sentences in the middle at a pause, which matters because dysarthric speech
pauses where fluent speech does not and a sentence cut in half loses its context.
The gain was then confirmed on all 682 pilot sentences (0.317 to 0.301, 128 splits
to 119) before the product was changed, and it carried through the whole pipeline:
first suggestion 0.230 to 0.220, best choice 0.196 to 0.185, exact best 418 to 426.
Better hearing improves every step downstream.

**Testing on the hardest speakers first is a deliberate choice.** An average over
all eight speakers is dominated by the three the recogniser already handles, where
no improvement is available. Progress lives at the difficult end.

---

## 6. Tried and not kept

Negative results are reported here because they determined the design, and because
a system evaluated only on its successes cannot be trusted.

**6.1 Automatic correction instead of choice.** Section 5.2. Text-only correction
raised WER and destroyed 117 sentences to repair 58. The product never overwrites
the heard text with a suggestion.

**6.2 A context prompt for the recogniser.** AssemblyAI accepts a prompt. Telling
it that the speaker may have dysarthria gave WER 0.400 against 0.398 on the same
296 sentences: no change. On the hardest speakers it was actively harmful for both
models (0.744 to 0.756, and 0.724 to 0.766). The product sends no prompt.

**6.3 A richer interpretation prompt.** A second prompt version supplied
AssemblyAI's per-word confidence scores and asked for three alternatives in a
different format. Tuned on one half of the pilot, it lost there: best-choice WER
0.214 against 0.196, and 196 exact against 204. Following our own rule that a tuning
set which loses is not re-run on the held-out half in the hope of a better number,
it was dropped and the original prompt kept. The word confidences are now discarded
by the backend rather than sent.

**6.4 A faster model for the suggestions.** Gemini 3.5 Flash-Lite answers in 1.8 s
at p50 against 3.8 s, which is attractive for a realtime interface. With the same
audio it scored 0.351 best-choice against 0.296 on the same 296 sentences, roughly
matching the larger model's **text-only** performance: it was not making use of the
audio. It is kept as the fallback when the main model is unavailable, where a fast
imperfect answer beats none, and not as the default.

**6.5 Gemini 3.8 Flash.** Equal quality to 3.7 Flash (best-choice 0.353 against
0.350 on 296 sentences, 143 exact against 144, inside the noise band of 0.03) with a
much longer latency tail: p90 8.4 s against 5.6 s and a worst case of 112 s. Equal
accuracy at worse tail latency is not an upgrade for an interactive tool.

**6.6 A two-stage suggestion.** An early plan showed a fast text-only suggestion
first, replaced by the audio-based one when it arrived. Since the text-only stage
measured *worse* than the raw transcript (6.1), it would have shown the speaker a
degraded option first and doubled the model quota per sentence. It was not built.

---

## 7. Limitations

- **Not a medical device.** It diagnoses nothing and assesses nothing.
- **Suggestions are guesses**, which is exactly why the speaker confirms every
  sentence before anything is spoken.
- **Measured on dysarthria in TORGO only.** The design targets the conditions
  covered by TORGO and the Speech Accessibility Project: dysarthria, cerebral
  palsy, ALS, Parkinson's disease, Down syndrome and stroke. Only dysarthria from
  cerebral palsy or ALS has been measured. No claim is made for the others until
  they are measured, per condition.
- **Read sentences, not conversation.** TORGO's prompts are read aloud and many are
  well known ("The quick brown fox..."), which is easier than spontaneous speech in
  two ways: the sentences are grammatical, and a language model has seen some of
  them. Free conversation will be harder.
- **The "speaker picks best" figures are an upper bound.** They assume the speaker
  recognises their own sentence among the options. A user study has not been run.
- **How long a pause may be before a sentence is treated as finished is a chosen
  value**, not a measured one. The speaker can end a sentence without waiting for it.
- **English only.**
- **No model is trained on anyone's voice.** The deployed system uses off-the-shelf
  models with prompting, audio conditioning and in-session context.
- **The slow tail is real.** p90 of 17.9 s comes from shared provider capacity.
  Under congestion the heard text remains available and the interface says the
  suggestion is taking longer than usual, but a speaker in a hurry will use the
  transcript.
- **Severe speech stays hard.** For M04, M01 and F01 most sentences are still not
  exactly right. The ear-marked option, Fix a word and Say it again matter most
  precisely where the automatic answer matters least.

---

## 8. Data, consent and contribution

Speech recognition hears dysarthric speech badly because it has rarely heard it.
Recordings paired with the sentence the speaker confirmed are the most useful
training data that exists for this problem, and there is very little of it.

TORGO is used under academic and non-profit terms, cited in the app, the README and
this paper, and never redistributed. Unofficial re-uploads of restricted corpora
were deliberately not used, even where they were freely downloadable, because
availability is not a licence. Access to the Speech Accessibility Project corpus
has been formally requested through a Data Use Agreement executed by the
institution.

The app therefore offers people a way to contribute, on strictly opt-in terms:

1. Sign in with Google and read the consent page. Nothing is collected before
   agreeing, and contributors must be 18 or older.
2. Open an explicitly marked **contribution session**, visually distinct from the
   Bridge so the two are never confused.
3. After confirming a sentence, choose **Contribute** or **Skip**, and state
   whether the confirmed text is exactly what was said.
4. Review, play back, delete individual recordings, withdraw consent or delete the
   account entirely, at any time.

Recordings are stored encrypted in private cloud storage under random identifiers;
account details and sentence texts sit in a database on our own server. Nothing is
published or shared. The consent version is pinned in both the backend and the
frontend and must match, so a change to the terms cannot be applied retroactively
to people who agreed to something else. **The Bridge itself stores nothing at all**,
whether or not anyone is signed in.

---

## 9. What comes next

The deployed system is complete and measured. These are the directions the
measurements point to, none of them claimed as results.

**A recogniser fine-tuned on dysarthric speech.** Whisper large-v3 with LoRA
adapters on TORGO. Data preparation, a leakage-safe split and the training job are
implemented and ready: sentence texts are disjoint between train and test by hash,
and three speakers are held out entirely so the held-out evaluation measures
generalisation to an unheard voice rather than memorisation of a fixed prompt list.
Execution waits on GPU capacity approval. It will be reported only once measured on
speakers it has never heard, combined with rather than replacing the streaming
recogniser, whose realtime behaviour it does not have.

**Measurement per condition.** Once the Speech Accessibility Project corpus is
available, the same pipeline runs per etiology, and results are reported per
condition rather than pooled.

**Low-confidence words surfaced in the interface.** The recogniser already returns
per-word confidence. It did not help the model (6.3), but showing the speaker which
words are shaky is a different use of the same signal, and directs Fix a word to
where it is needed.

**The pause that ends a sentence.** Turns are joined into one sentence when nothing
further arrives within a fixed window. That window is a chosen value, not a measured
one: turn timings are not kept in the results files, so the distribution of pauses
inside a dysarthric sentence, against the pauses between two sentences, has never
been measured. Measuring it would replace a guess in the interaction with a number,
and it costs one short instrumented run.

**A study with actual speakers.** Every accuracy figure that involves choosing is
an upper bound until people with dysarthria use this and we measure what they
actually pick, how long it takes them, and whether they are understood.

---

## 10. Conclusion

The accessibility gap in speech technology is usually framed as a data problem to be
solved by training. It is, eventually. But a system built today, on models that get
40% of the words wrong, already recovers 63% of sentences word for word, if it is
honest about being uncertain and hands the decision to the person whose sentence it
is.

The measurements say something narrower and more useful than "AI helps." Reading a
transcript does not help and actively hurts. Hearing the audio helps. Hearing the
speaker's own earlier sentences helps again. Offering a choice helps as much as
improving the suggestion. And the person who knows what they said is the only one
qualified to decide which option is right.

---

## References

Rudzicz, F., Namasivayam, A.K., Wolff, T. (2012). The TORGO database of acoustic
and articulatory speech from speakers with dysarthria. *Language Resources and
Evaluation*, 46(4), 523 to 541.
Original corpus: <https://www.cs.toronto.edu/~complingweb/data/TORGO/torgo.html>

Speech Accessibility Project, University of Illinois Urbana-Champaign.
<https://speechaccessibilityproject.beckman.illinois.edu/>

## Components

AssemblyAI Universal-3.6 Pro streaming speech-to-text (rounds A to D used
Universal-3.5 Pro). Google Gemini 3.7 Flash and 3.5 Flash-Lite on Vertex AI.
Deepgram Aura-2 text-to-speech. Firebase Authentication for contributor sign-in.
FastAPI, uvicorn, httpx, pydantic, SQLAlchemy, Alembic, asyncpg, boto3,
PostgreSQL, React Router 8, React, Radix Themes, jose, jiwer, pyarrow, under their
respective open source licences. Ear icon from Lucide (ISC).

Benchmark scripts and raw per-utterance results:
<https://github.com/eziedutech/synapvocal/tree/main/scripts/benchmark>

A code assistant was used to speed up development and debugging. Design decisions,
measurements and claims were checked by hand against real runs.

Released under the MIT licence.
