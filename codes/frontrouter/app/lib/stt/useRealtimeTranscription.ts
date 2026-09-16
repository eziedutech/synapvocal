import { useCallback, useEffect, useRef, useState } from "react";

export type SttStatus = "idle" | "connecting" | "listening" | "stopping" | "error";

export type Turn = {
  order: number;
  text: string;
  final: boolean;
  // ms since the session started, for latency measurement later
  receivedAtMs: number;
};

type TokenResponse = { token: string; ws_url: string; sample_rate: number };

type Session = {
  ws: WebSocket;
  stream: MediaStream;
  audio: AudioContext;
  startedAt: number;
  began: boolean;
  stopTimer?: ReturnType<typeof setTimeout>;
};

function describeStartError(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError") return "Microphone permission was denied.";
    if (error.name === "NotFoundError") return "No microphone was found.";
    return `${error.name}: ${error.message}`;
  }
  return error instanceof Error ? error.message : String(error);
}

async function fetchToken(): Promise<TokenResponse> {
  const response = await fetch("/stt/token", { method: "POST" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? `Token request failed (${response.status})`);
  }
  return response.json();
}

export function useRealtimeTranscription() {
  const [status, setStatus] = useState<SttStatus>("idle");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const session = useRef<Session | null>(null);

  const release = useCallback(() => {
    const current = session.current;
    if (!current) return;
    session.current = null;
    clearTimeout(current.stopTimer);
    current.stream.getTracks().forEach((track) => track.stop());
    current.audio.close().catch((cause) => console.warn("[stt] audio close failed", cause));
    if (current.ws.readyState === WebSocket.OPEN || current.ws.readyState === WebSocket.CONNECTING) {
      current.ws.close();
    }
    setLevel(0);
  }, []);

  const fail = useCallback(
    (message: string) => {
      console.error("[stt]", message);
      setError(message);
      setStatus("error");
      release();
    },
    [release],
  );

  const start = useCallback(async () => {
    if (session.current) return;
    setError(null);
    setStatus("connecting");

    let stream: MediaStream | undefined;
    try {
      const [mic, token] = await Promise.all([
        navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        }),
        fetchToken(),
      ]);
      stream = mic;

      const audio = new AudioContext();
      await audio.audioWorklet.addModule("/worklets/pcm16-capture.js");
      const source = audio.createMediaStreamSource(stream);
      const capture = new AudioWorkletNode(audio, "pcm16-capture", {
        processorOptions: { targetRate: token.sample_rate },
      });
      // Some browsers only pull audio through nodes that reach the destination.
      const mute = audio.createGain();
      mute.gain.value = 0;
      source.connect(capture).connect(mute).connect(audio.destination);

      const ws = new WebSocket(`${token.ws_url}&token=${encodeURIComponent(token.token)}`);
      ws.binaryType = "arraybuffer";
      const current: Session = { ws, stream, audio, startedAt: performance.now(), began: false };
      session.current = current;

      capture.port.onmessage = (event: MessageEvent<{ pcm: ArrayBuffer; level: number }>) => {
        setLevel(event.data.level);
        if (current.began && ws.readyState === WebSocket.OPEN) ws.send(event.data.pcm);
      };

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data as string);
        if (message.type === "Begin") {
          current.began = true;
          setTurns([]);
          setStatus("listening");
        } else if (message.type === "Turn") {
          const turn: Turn = {
            order: message.turn_order,
            text: message.transcript,
            final: Boolean(message.end_of_turn),
            receivedAtMs: Math.round(performance.now() - current.startedAt),
          };
          setTurns((previous) => {
            const others = previous.filter((t) => t.order !== turn.order);
            return [...others, turn].sort((a, b) => a.order - b.order);
          });
        } else if (message.type === "Termination") {
          release();
          setStatus("idle");
        } else if (message.type === "Error" || message.error) {
          fail(`Speech recognition error: ${message.error ?? JSON.stringify(message)}`);
        }
      };

      ws.onclose = (event) => {
        if (session.current !== current) return;
        if (event.code === 1000) {
          release();
          setStatus("idle");
        } else {
          fail(`Speech recognition connection closed (${event.code}${event.reason ? `: ${event.reason}` : ""}).`);
        }
      };
      ws.onerror = () => console.warn("[stt] websocket error event; waiting for close code");
    } catch (cause) {
      stream?.getTracks().forEach((track) => track.stop());
      fail(describeStartError(cause));
    }
  }, [fail, release]);

  const stop = useCallback(() => {
    const current = session.current;
    if (!current) return;
    setStatus("stopping");
    current.stream.getTracks().forEach((track) => track.stop());
    if (current.ws.readyState === WebSocket.OPEN) {
      current.ws.send(JSON.stringify({ type: "Terminate" }));
      // If Termination never arrives, do not leave the Speaker stuck in "stopping".
      current.stopTimer = setTimeout(() => {
        console.warn("[stt] no Termination after 3 s, closing locally");
        release();
        setStatus("idle");
      }, 3000);
    } else {
      release();
      setStatus("idle");
    }
  }, [release]);

  const endTurn = useCallback(() => {
    const ws = session.current?.ws;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ForceEndpoint" }));
  }, []);

  useEffect(() => release, [release]);

  return { status, turns, level, error, start, stop, endTurn };
}
