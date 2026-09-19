import { useCallback, useEffect, useRef, useState } from "react";

export type SttStatus = "idle" | "connecting" | "listening" | "stopping" | "error";

export type Turn = {
  order: number;
  text: string;
  final: boolean;
  // ms since the session started, for latency measurement later
  receivedAtMs: number;
  // AssemblyAI's words with their confidence and timing (ms from the first audio sent).
  words: TurnWord[];
};

type TokenResponse = { token: string; ws_url: string; sample_rate: number };

// Where the audio comes from. A file is streamed at real time, exactly like a microphone,
// and played aloud at the same time so the listener hears what is being recognised.
export type AudioSource = { kind: "microphone" } | { kind: "file"; name: string; samples: Int16Array };
export type FileProgress = { name: string; sentMs: number; totalMs: number };

type Session = {
  ws: WebSocket;
  // Audio sent since Begin, kept only for contributors (see keepAudio).
  chunks: Int16Array[];
  // Samples dropped from the front of `chunks` to cap memory.
  droppedSamples: number;
  stream: MediaStream | null;
  audio: AudioContext;
  // File source only: the timer that feeds 100 ms chunks, and the playback node.
  feeder?: ReturnType<typeof setInterval>;
  player?: AudioBufferSourceNode;
  startedAt: number;
  began: boolean;
  id?: number;
  onBegin?: () => void;
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

// Word timings in AssemblyAI Turn messages are ms from the first audio sent.
export type TurnWord = { text: string; confidence: number; start: number; end: number };

const SAMPLE_RATE = 16000;
const KEEP_SECONDS = 180;
const KEEP_SENTENCES = 20; // enough for the sentence being confirmed, never the whole conversation
const PAD_BEFORE_MS = 250;
const PAD_AFTER_MS = 400;

function sliceSamples(current: Session, fromMs: number, toMs: number): Int16Array | null {
  const total = current.chunks.reduce((n, c) => n + c.length, 0);
  const from = Math.max(0, Math.floor((fromMs * SAMPLE_RATE) / 1000) - current.droppedSamples);
  const to = Math.min(total, Math.ceil((toMs * SAMPLE_RATE) / 1000) - current.droppedSamples);
  if (to <= from) return null;
  const out = new Int16Array(to - from);
  let offset = 0;
  for (const chunk of current.chunks) {
    const start = Math.max(0, from - offset);
    const end = Math.min(chunk.length, to - offset);
    if (end > start) out.set(chunk.subarray(start, end), offset + start - from);
    offset += chunk.length;
    if (offset >= to) break;
  }
  return out;
}

// keepAudio: hold each finished sentence's audio in this page's memory, for Gemini to hear
// it and, in a contribution session, for the Speaker to choose to give it. Never stored.
export function useRealtimeTranscription({ keepAudio = false }: { keepAudio?: boolean } = {}) {
  const [status, setStatus] = useState<SttStatus>("idle");
  const [turns, setTurns] = useState<Turn[]>([]);
  // Increments on every Begin; turn_order restarts at 0 in each session.
  const [sessionId, setSessionId] = useState(0);
  // Live analyser for visualisation. Set once per session, read per animation frame.
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fileProgress, setFileProgress] = useState<FileProgress | null>(null);
  const session = useRef<Session | null>(null);
  const turnAudio = useRef(new Map<string, Int16Array>());
  const sessionCounter = useRef(0);
  const keepAudioRef = useRef(keepAudio);
  keepAudioRef.current = keepAudio;

  const release = useCallback(() => {
    const current = session.current;
    if (!current) return;
    session.current = null;
    clearTimeout(current.stopTimer);
    clearInterval(current.feeder);
    try {
      current.player?.stop();
    } catch {
      // already stopped
    }
    current.stream?.getTracks().forEach((track) => track.stop());
    current.audio.close().catch((cause) => console.warn("[stt] audio close failed", cause));
    if (current.ws.readyState === WebSocket.OPEN || current.ws.readyState === WebSocket.CONNECTING) {
      current.ws.close();
    }
    setAnalyser(null);
    setFileProgress(null);
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

  const start = useCallback(async (source: AudioSource = { kind: "microphone" }) => {
    if (session.current) return;
    setError(null);
    setStatus("connecting");

    let stream: MediaStream | null = null;
    try {
      const [mic, token] = await Promise.all([
        source.kind === "microphone"
          ? navigator.mediaDevices.getUserMedia({
              audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
            })
          : Promise.resolve(null),
        fetchToken(),
      ]);
      stream = mic;

      const audio = new AudioContext();
      const spectrum = audio.createAnalyser();
      spectrum.fftSize = 1024;
      spectrum.smoothingTimeConstant = 0.78;

      const ws = new WebSocket(`${token.ws_url}&token=${encodeURIComponent(token.token)}`);
      ws.binaryType = "arraybuffer";
      const current: Session = { ws, stream, audio, startedAt: performance.now(), began: false, chunks: [], droppedSamples: 0 };
      session.current = current;
      setAnalyser(spectrum);

      const send = (pcm: ArrayBuffer) => {
        if (!current.began || ws.readyState !== WebSocket.OPEN) return;
        if (keepAudioRef.current) {
          current.chunks.push(new Int16Array(pcm.slice(0)));
          let kept = current.chunks.reduce((n, c) => n + c.length, 0);
          while (kept > KEEP_SECONDS * SAMPLE_RATE && current.chunks.length > 1) {
            const dropped = current.chunks.shift()!;
            current.droppedSamples += dropped.length;
            kept -= dropped.length;
          }
        }
        ws.send(pcm);
      };

      if (stream) {
        await audio.audioWorklet.addModule("/worklets/pcm16-capture.js");
        const input = audio.createMediaStreamSource(stream);
        const capture = new AudioWorkletNode(audio, "pcm16-capture", {
          processorOptions: { targetRate: token.sample_rate },
        });
        // Some browsers only pull audio through nodes that reach the destination.
        const mute = audio.createGain();
        mute.gain.value = 0;
        input.connect(capture).connect(mute).connect(audio.destination);
        input.connect(spectrum).connect(mute);
        capture.port.onmessage = (event: MessageEvent<{ pcm: ArrayBuffer }>) => send(event.data.pcm);
      } else if (source.kind === "file") {
        // Played aloud through the analyser, and fed to recognition in 100 ms chunks at real
        // time once the session begins, the way the benchmark streams TORGO.
        const buffer = audio.createBuffer(1, source.samples.length, SAMPLE_RATE);
        const channel = buffer.getChannelData(0);
        for (let i = 0; i < source.samples.length; i++) channel[i] = source.samples[i] / 0x8000;
        const player = audio.createBufferSource();
        player.buffer = buffer;
        player.connect(spectrum).connect(audio.destination);
        current.player = player;
        const totalMs = Math.round((source.samples.length / SAMPLE_RATE) * 1000);
        setFileProgress({ name: source.name, sentMs: 0, totalMs });
        current.onBegin = () => {
          player.start();
          const chunk = SAMPLE_RATE / 10;
          let offset = 0;
          current.feeder = setInterval(() => {
            if (offset >= source.samples.length) {
              clearInterval(current.feeder);
              // The recording is over: close its sentence now, then end the session.
              if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ForceEndpoint" }));
              current.stopTimer = setTimeout(() => stopRef.current(), 2500);
              return;
            }
            const piece = source.samples.slice(offset, offset + chunk);
            offset += chunk;
            send(piece.buffer);
            setFileProgress({ name: source.name, sentMs: Math.min(totalMs, Math.round((offset / SAMPLE_RATE) * 1000)), totalMs });
          }, 100);
        };
      }

      ws.onmessage = (event) => {
        const message = JSON.parse(event.data as string);
        if (message.type === "Begin") {
          current.began = true;
          setTurns([]);
          current.id = ++sessionCounter.current;
          setSessionId(current.id);
          setStatus("listening");
          current.onBegin?.();
        } else if (message.type === "Turn") {
          const turn: Turn = {
            order: message.turn_order,
            text: message.transcript,
            final: Boolean(message.end_of_turn),
            receivedAtMs: Math.round(performance.now() - current.startedAt),
            words: ((message.words ?? []) as TurnWord[]).map(({ text, confidence, start, end }) => ({ text, confidence, start, end })),
          };
          const words = turn.words;
          if (turn.final && keepAudioRef.current && words.length > 0 && current.id !== undefined) {
            const samples = sliceSamples(current, words[0].start - PAD_BEFORE_MS, words[words.length - 1].end + PAD_AFTER_MS);
            if (samples) {
              turnAudio.current.set(`${current.id}-${turn.order}`, samples);
              // Only recent sentences can still be retried or contributed; drop the rest.
              while (turnAudio.current.size > KEEP_SENTENCES) turnAudio.current.delete(turnAudio.current.keys().next().value!);
            }
          }
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

  // Lets the file feeder end the session without depending on `stop` directly.
  const stopRef = useRef<() => void>(() => undefined);

  const stop = useCallback(() => {
    const current = session.current;
    if (!current) return;
    setStatus("stopping");
    clearInterval(current.feeder);
    try {
      current.player?.stop();
    } catch {
      // already stopped
    }
    current.stream?.getTracks().forEach((track) => track.stop());
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

  stopRef.current = stop;

  const endTurn = useCallback(() => {
    const ws = session.current?.ws;
    if (ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "ForceEndpoint" }));
  }, []);

  useEffect(() => release, [release]);

  // Audio of a finished sentence, keyed like sentences (`${sessionId}-${turn order}`).
  const getTurnAudio = useCallback((key: string) => turnAudio.current.get(key) ?? null, []);
  const forgetTurnAudio = useCallback((key?: string) => {
    if (key) turnAudio.current.delete(key);
    else turnAudio.current.clear();
  }, []);

  return { status, turns, sessionId, analyser, error, fileProgress, start, stop, endTurn, getTurnAudio, forgetTurnAudio };
}
