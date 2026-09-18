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

export type Sentence = {
  // Session and turn together; turn_order alone repeats across sessions.
  key: string;
  heard: string;
  words: TurnWord[];
  // "Say it again": the same sentence said a second time, heard as its own turn.
  retake: { key: string; heard: string; words: TurnWord[] } | null;
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

type HistoryPair = { heard: string; confirmed: string };

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
        audio_wav_base64: await base64Wav(getAudio(sentence.retake.key)),
      }
    : undefined;
  const response = await fetch("/bridge/interpret", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      transcript: sentence.heard,
      words: wordsForRequest(sentence.words),
      history,
      audio_wav_base64: await base64Wav(getAudio(sentence.key)),
      retake,
    }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail ?? `Interpretation failed (${response.status})`);
  return body as Interpretation;
}

// Every finished turn becomes a sentence, unless the Speaker asked to say one again: then
// the next finished turn is that sentence's second take. The heard text shows at once;
// the interpretation arrives later and never blocks it.
export function useSentences(turns: Turn[], sessionId: number, getAudio: (key: string) => Int16Array | null) {
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const [awaitingRetake, setAwaitingRetake] = useState<string | null>(null);
  const requested = useRef(new Set<string>());
  const confirmedRef = useRef<HistoryPair[]>([]);
  const sentencesRef = useRef<Sentence[]>([]);
  sentencesRef.current = sentences;
  const awaitingRef = useRef<string | null>(null);
  awaitingRef.current = awaitingRetake;

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

  useEffect(() => {
    for (const turn of turns) {
      const key = `${sessionId}-${turn.order}`;
      if (!turn.final || !turn.text.trim() || requested.current.has(key)) continue;
      requested.current.add(key);
      const target = awaitingRef.current ? sentencesRef.current.find((s) => s.key === awaitingRef.current) : undefined;
      if (target && target.confirmed === null) {
        const withRetake: Sentence = { ...target, retake: { key, heard: turn.text, words: turn.words } };
        update(target.key, () => withRetake);
        setAwaitingRetake(null);
        interpret(withRetake);
        continue;
      }
      const sentence: Sentence = {
        key,
        heard: turn.text,
        words: turn.words,
        retake: null,
        interpretation: { status: "loading" },
        confirmed: null,
        confirmedSource: null,
      };
      setSentences((previous) => [...previous, sentence]);
      interpret(sentence);
    }
  }, [turns, sessionId, interpret, update]);

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

  // Starts a fresh conversation: the list and the confirmed context sent to Gemini both
  // go. Keys stay in `requested`, so turns already heard are not added back, and an
  // interpretation still on its way finds no sentence to update.
  const clear = useCallback(() => {
    confirmedRef.current = [];
    setAwaitingRetake(null);
    setSentences([]);
  }, []);

  return { sentences, confirm, retry, clear, sayAgain, awaitingRetake };
}
