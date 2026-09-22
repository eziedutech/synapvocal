import { useCallback, useEffect, useRef, useState } from "react";

import { toWav } from "~/lib/contrib/wav";
import type { Turn, TurnWord } from "~/lib/stt/useRealtimeTranscription";

export type Interpretation = {
  transcript: string;
  interpretation: string;
  alternatives: string[];
  confidence: number;
  unchanged: boolean;
  model: string;
  latency_ms: number;
};

// Where a confirmed sentence came from; recorded with contributions as a label quality hint.
export type LabelSource = "heard" | "suggestion" | "alternative" | "edited";

export type Take = {
  // Session and turn together; turn_order alone repeats across sessions.
  key: string;
  // Every turn this take is built from, in order. Usually one, more when the Speaker
  // paused mid-sentence and the recogniser ended the turn there.
  turnKeys: string[];
  heard: string;
  words: TurnWord[];
};

export type Sentence = Take & {
  // "Say it again": the same sentence said a second time, heard as its own take.
  retake: Take | null;
  interpretation:
    | { status: "loading" }
    | { status: "ready"; data: Interpretation }
    | { status: "failed"; reason: string };
  // What the Speaker confirmed, once they have.
  confirmed: string | null;
  confirmedSource: LabelSource | null;
};

// Earlier sentences sent along, as the benchmark's round C2 did (5 pairs).
const HISTORY = 5;

// Speech that pauses gets cut into several turns: the recogniser ends a turn after
// min_turn_silence, 400 ms, and a dysarthric pause inside a sentence easily passes that.
// Measured on the TORGO pilot, 119 of 682 sentences came back as more than one turn. The
// benchmark scores all of a recording's turns as one sentence, so the app does the same:
// a turn extends the sentence still open instead of starting a new one, and the sentence
// closes when nothing more has arrived for this long.
//
// 1500 ms is a chosen value, not a measured one. Turn timings are not kept in the results
// files, so the distribution of gaps inside a sentence has not been measured; what is known
// is that every gap we merge is one the recogniser already judged to be a finished turn.
// The Speaker never has to wait for it: End sentence closes the sentence at once.
const MERGE_WINDOW_MS = 1500;
// After End sentence, wait only long enough for the turn it forces to arrive.
const FLUSH_WINDOW_MS = 2000;

type HistoryPair = { heard: string; confirmed: string };

function joinAudio(keys: string[], getAudio: (key: string) => Int16Array | null): Int16Array | null {
  const parts = keys.map(getAudio).filter((p): p is Int16Array => p !== null && p.length > 0);
  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0];
  const joined = new Int16Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const part of parts) {
    joined.set(part, at);
    at += part.length;
  }
  return joined;
}

async function base64Wav(samples: Int16Array | null): Promise<string | undefined> {
  if (!samples) return undefined;
  const bytes = new Uint8Array(await toWav(samples).arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

const wordsForRequest = (words: TurnWord[]) => words.map((w) => ({ text: w.text, confidence: w.confidence }));

// The sentence audio goes to Gemini with the transcript: measured on TORGO, that and the
// history lower the suggestion error most (round C2). Audio is processed, never stored.
async function requestInterpretation(
  sentence: Sentence,
  history: HistoryPair[],
  getAudio: (key: string) => Int16Array | null,
): Promise<Interpretation> {
  const retake = sentence.retake
    ? {
        transcript: sentence.retake.heard,
        words: wordsForRequest(sentence.retake.words),
        audio_wav_base64: await base64Wav(joinAudio(sentence.retake.turnKeys, getAudio)),
      }
    : undefined;
  const response = await fetch("/bridge/interpret", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      transcript: sentence.heard,
      words: wordsForRequest(sentence.words),
      history,
      audio_wav_base64: await base64Wav(joinAudio(sentence.turnKeys, getAudio)),
      retake,
    }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail ?? `Interpretation failed (${response.status})`);
  return body as Interpretation;
}

// A finished turn extends the sentence still open, or starts one. The sentence closes after
// MERGE_WINDOW_MS with nothing further, or as soon as the Speaker ends it, and only then is
// it interpreted: a fragment interpreted on its own invites an answer about nothing that was
// said. The heard text shows as each turn arrives and never waits for the interpretation.
export function useSentences(turns: Turn[], sessionId: number, getAudio: (key: string) => Int16Array | null) {
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const [awaitingRetake, setAwaitingRetake] = useState<string | null>(null);
  const requested = useRef(new Set<string>());
  const confirmedRef = useRef<HistoryPair[]>([]);
  const sentencesRef = useRef<Sentence[]>([]);
  sentencesRef.current = sentences;
  const awaitingRef = useRef<string | null>(null);
  awaitingRef.current = awaitingRetake;
  // The sentence still taking turns, and the timer that will close it.
  const openKey = useRef<string | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const update = useCallback((key: string, change: (s: Sentence) => Sentence) => {
    setSentences((previous) => previous.map((s) => (s.key === key ? change(s) : s)));
  }, []);

  const interpret = useCallback(
    (sentence: Sentence) => {
      update(sentence.key, (s) => ({ ...s, interpretation: { status: "loading" } }));
      requestInterpretation(sentence, confirmedRef.current.slice(-HISTORY), getAudio)
        .then((data) => update(sentence.key, (s) => ({ ...s, interpretation: { status: "ready", data } })))
        .catch((error: Error) => {
          console.error("[bridge] interpretation failed", sentence.key, error);
          update(sentence.key, (s) => ({ ...s, interpretation: { status: "failed", reason: error.message } }));
        });
    },
    [update, getAudio],
  );

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) clearTimeout(closeTimer.current);
    closeTimer.current = null;
  }, []);

  // Close the open sentence: either it becomes the second take of the sentence the Speaker
  // asked to say again, or it is interpreted on its own.
  const closeOpen = useCallback(() => {
    cancelClose();
    const key = openKey.current;
    openKey.current = null;
    if (key === null) return;
    const closing = sentencesRef.current.find((s) => s.key === key);
    if (!closing) return;

    const target = awaitingRef.current ? sentencesRef.current.find((s) => s.key === awaitingRef.current) : undefined;
    if (target && target.key !== key && target.confirmed === null) {
      const withRetake: Sentence = {
        ...target,
        retake: { key: closing.key, turnKeys: closing.turnKeys, heard: closing.heard, words: closing.words },
      };
      setSentences((previous) => previous.filter((s) => s.key !== key).map((s) => (s.key === target.key ? withRetake : s)));
      setAwaitingRetake(null);
      interpret(withRetake);
      return;
    }
    interpret(closing);
  }, [cancelClose, interpret]);

  const scheduleClose = useCallback(
    (delay: number) => {
      cancelClose();
      closeTimer.current = setTimeout(closeOpen, delay);
    },
    [cancelClose, closeOpen],
  );

  useEffect(() => {
    for (const turn of turns) {
      const key = `${sessionId}-${turn.order}`;
      if (!turn.final || !turn.text.trim() || requested.current.has(key)) continue;
      requested.current.add(key);

      const open = openKey.current ? sentencesRef.current.find((s) => s.key === openKey.current) : undefined;
      if (open) {
        update(open.key, (s) => ({
          ...s,
          turnKeys: [...s.turnKeys, key],
          heard: `${s.heard} ${turn.text}`.trim(),
          words: [...s.words, ...turn.words],
        }));
      } else {
        openKey.current = key;
        setSentences((previous) => [
          ...previous,
          {
            key,
            turnKeys: [key],
            heard: turn.text,
            words: turn.words,
            retake: null,
            interpretation: { status: "loading" },
            confirmed: null,
            confirmedSource: null,
          },
        ]);
      }
      scheduleClose(MERGE_WINDOW_MS);
    }
  }, [turns, sessionId, update, scheduleClose]);

  // The Speaker ended the sentence. The turn that forces is still on its way, so take it and
  // then close; if nothing arrives, close anyway rather than leaving the sentence open.
  const endSentence = useCallback(() => {
    if (openKey.current !== null) scheduleClose(FLUSH_WINDOW_MS);
  }, [scheduleClose]);

  const confirm = useCallback(
    (key: string, text: string, source: LabelSource) => {
      const heard = sentencesRef.current.find((s) => s.key === key)?.heard ?? "";
      if (heard) confirmedRef.current = [...confirmedRef.current, { heard, confirmed: text }];
      if (awaitingRef.current === key) setAwaitingRetake(null);
      update(key, (s) => ({ ...s, confirmed: text, confirmedSource: source }));
    },
    [update],
  );

  const retry = useCallback(
    (key: string) => {
      const sentence = sentencesRef.current.find((s) => s.key === key);
      if (sentence) interpret(sentence);
    },
    [interpret],
  );

  // The next sentence the Speaker finishes becomes the second take of this one.
  const sayAgain = useCallback((key: string | null) => setAwaitingRetake(key), []);

  // Every sample of a sentence, across the turns it was built from.
  const sentenceAudio = useCallback((sentence: Sentence) => joinAudio(sentence.turnKeys, getAudio), [getAudio]);

  // Starts a fresh conversation: the list and the confirmed context sent to Gemini both
  // go. Keys stay in `requested`, so turns already heard are not added back, and an
  // interpretation still on its way finds no sentence to update.
  const clear = useCallback(() => {
    cancelClose();
    openKey.current = null;
    confirmedRef.current = [];
    setAwaitingRetake(null);
    setSentences([]);
  }, [cancelClose]);

  useEffect(() => cancelClose, [cancelClose]);

  return { sentences, confirm, retry, clear, sayAgain, awaitingRetake, endSentence, sentenceAudio };
}
