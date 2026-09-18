import { useCallback, useEffect, useRef, useState } from "react";

import { toWav } from "~/lib/contrib/wav";
import type { Turn } from "~/lib/stt/useRealtimeTranscription";

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

async function base64Wav(samples: Int16Array): Promise<string> {
  const bytes = new Uint8Array(await toWav(samples).arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(binary);
}

// The sentence audio goes to Gemini with the transcript: measured on TORGO, that and the
// history lower the suggestion error most (round C2). Audio is processed, never stored.
async function requestInterpretation(
  transcript: string,
  history: HistoryPair[],
  audio: Int16Array | null,
): Promise<Interpretation> {
  const audio_wav_base64 = audio ? await base64Wav(audio) : undefined;
  const response = await fetch("/bridge/interpret", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, history, audio_wav_base64 }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail ?? `Interpretation failed (${response.status})`);
  return body as Interpretation;
}

// Every finished turn becomes a sentence. The heard text shows immediately; the
// interpretation arrives later (2 to 6 s with Gemini 3.x Flash) and never blocks it.
export function useSentences(turns: Turn[], sessionId: number, getAudio: (key: string) => Int16Array | null) {
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const requested = useRef(new Set<string>());
  const confirmedRef = useRef<HistoryPair[]>([]);

  const update = useCallback((key: string, change: (s: Sentence) => Sentence) => {
    setSentences((previous) => previous.map((s) => (s.key === key ? change(s) : s)));
  }, []);

  const interpret = useCallback(
    (key: string, heard: string) => {
      update(key, (s) => ({ ...s, interpretation: { status: "loading" } }));
      requestInterpretation(heard, confirmedRef.current.slice(-HISTORY), getAudio(key))
        .then((data) => update(key, (s) => ({ ...s, interpretation: { status: "ready", data } })))
        .catch((error: Error) => {
          console.error("[bridge] interpretation failed", key, error);
          update(key, (s) => ({ ...s, interpretation: { status: "failed", reason: error.message } }));
        });
    },
    [update, getAudio],
  );

  useEffect(() => {
    for (const turn of turns) {
      const key = `${sessionId}-${turn.order}`;
      if (!turn.final || !turn.text.trim() || requested.current.has(key)) continue;
      requested.current.add(key);
      setSentences((previous) => [
        ...previous,
        { key, heard: turn.text, interpretation: { status: "loading" }, confirmed: null, confirmedSource: null },
      ]);
      interpret(key, turn.text);
    }
  }, [turns, sessionId, interpret]);

  const confirm = useCallback(
    (key: string, text: string, source: LabelSource) => {
      const heard = sentences.find((s) => s.key === key)?.heard ?? "";
      if (heard) confirmedRef.current = [...confirmedRef.current, { heard, confirmed: text }];
      update(key, (s) => ({ ...s, confirmed: text, confirmedSource: source }));
    },
    [update, sentences],
  );

  const retry = useCallback(
    (key: string) => {
      const sentence = sentences.find((s) => s.key === key);
      if (sentence) interpret(key, sentence.heard);
    },
    [sentences, interpret],
  );

  // Starts a fresh conversation: the list and the confirmed context sent to Gemini both
  // go. Keys stay in `requested`, so turns already heard are not added back, and an
  // interpretation still on its way finds no sentence to update.
  const clear = useCallback(() => {
    confirmedRef.current = [];
    setSentences([]);
  }, []);

  return { sentences, confirm, retry, clear };
}
