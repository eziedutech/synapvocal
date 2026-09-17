import { useCallback, useEffect, useRef, useState } from "react";

export type SpeechState = { key: string; status: "loading" | "playing" } | { key: string; status: "failed"; reason: string } | null;

// Plays one sentence at a time. Starting a new one stops the previous, so the
// Listener never hears two sentences over each other.
export function useSpeech() {
  const [state, setState] = useState<SpeechState>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const request = useRef<AbortController | null>(null);

  const stop = useCallback(() => {
    request.current?.abort();
    request.current = null;
    if (audio.current) {
      audio.current.pause();
      URL.revokeObjectURL(audio.current.src);
      audio.current = null;
    }
    setState(null);
  }, []);

  const speak = useCallback(
    async (key: string, text: string) => {
      stop();
      const controller = new AbortController();
      request.current = controller;
      setState({ key, status: "loading" });
      try {
        const response = await fetch("/tts/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
          signal: controller.signal,
        });
        if (!response.ok) {
          const body = await response.json().catch(() => null);
          throw new Error(body?.detail ?? `Voice output failed (${response.status})`);
        }
        const url = URL.createObjectURL(await response.blob());
        const player = new Audio(url);
        audio.current = player;
        player.onended = () => {
          URL.revokeObjectURL(url);
          if (audio.current === player) {
            audio.current = null;
            setState(null);
          }
        };
        await player.play();
        setState({ key, status: "playing" });
      } catch (error) {
        if (controller.signal.aborted) return;
        const reason = error instanceof Error ? error.message : String(error);
        console.error("[speech] failed", key, error);
        setState({ key, status: "failed", reason });
      }
    },
    [stop],
  );

  useEffect(() => stop, [stop]);

  return { state, speak, stop };
}
