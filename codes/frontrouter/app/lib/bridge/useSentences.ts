import { useCallback, useEffect, useRef, useState } from "react";

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
};

const RECENT_CONTEXT = 5;

async function requestInterpretation(transcript: string, recent: string[]): Promise<Interpretation> {
  const response = await fetch("/bridge/interpret", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ transcript, recent }),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(body?.detail ?? `Interpretation failed (${response.status})`);
  return body as Interpretation;
}

// Every finished turn becomes a sentence. The heard text shows immediately; the
// interpretation arrives later (2 to 6 s with Gemini 3.x Flash) and never blocks it.
export function useSentences(turns: Turn[], sessionId: number) {
  const [sentences, setSentences] = useState<Sentence[]>([]);
  const requested = useRef(new Set<string>());
  const confirmedRef = useRef<string[]>([]);

  const update = useCallback((key: string, change: (s: Sentence) => Sentence) => {
    setSentences((previous) => previous.map((s) => (s.key === key ? change(s) : s)));
  }, []);

  const interpret = useCallback(
    (key: string, heard: string) => {
      update(key, (s) => ({ ...s, interpretation: { status: "loading" } }));
      requestInterpretation(heard, confirmedRef.current.slice(-RECENT_CONTEXT))
        .then((data) => update(key, (s) => ({ ...s, interpretation: { status: "ready", data } })))
        .catch((error: Error) => {
          console.error("[bridge] interpretation failed", key, error);
          update(key, (s) => ({ ...s, interpretation: { status: "failed", reason: error.message } }));
        });
    },
    [update],
  );

  useEffect(() => {
    for (const turn of turns) {
      const key = `${sessionId}-${turn.order}`;
      if (!turn.final || !turn.text.trim() || requested.current.has(key)) continue;
      requested.current.add(key);
      setSentences((previous) => [
        ...previous,
        { key, heard: turn.text, interpretation: { status: "loading" }, confirmed: null },
      ]);
      interpret(key, turn.text);
    }
  }, [turns, sessionId, interpret]);

  const confirm = useCallback(
    (key: string, text: string) => {
      confirmedRef.current = [...confirmedRef.current, text];
      update(key, (s) => ({ ...s, confirmed: text }));
    },
    [update],
  );

  const retry = useCallback(
    (key: string) => {
      const sentence = sentences.find((s) => s.key === key);
      if (sentence) interpret(key, sentence.heard);
    },
    [sentences, interpret],
  );

  return { sentences, confirm, retry };
}
