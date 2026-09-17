import { useEffect, useRef } from "react";

// Abstract circular spectrum of the microphone: many thin lines radiate from a
// hollow ring, and their lengths trace one smooth, organic outline. The outline
// is driven by a handful of control points around the circle, each fed by one
// speech frequency band (roughly 80 Hz to 5 kHz) and interpolated between, so
// the shape swells unevenly with the voice instead of pulsing as a whole.

const SIZE = 112;
const LINES = 140;
const INNER_RADIUS = 18;
const MIN_LINE = 4;
// SIZE / 2 = INNER_RADIUS + energy growth (4) + MIN_LINE + MAX_LINE, so a full swell stays inside the canvas.
const MAX_LINE = 30;
const LOW_HZ = 80;
const HIGH_HZ = 5000;

// Bands are placed around the circle out of order so neighbouring lobes differ.
const CONTROL_ORDER = [0, 6, 2, 9, 4, 11, 1, 7, 3, 10, 5, 8];
const CONTROLS = CONTROL_ORDER.length;
// At rest the ring is even: no shape until there is a voice to shape it.
const RESTING_VALUE = 0.06;

// The logo teal and soft related greens (lighter Radix steps), alternated around the ring.
const PALETTE = ["--sv-brand", "--teal-7", "--mint-8", "--jade-7", "--sv-brand", "--grass-7", "--mint-9"];

type Mode = "idle" | "active" | "busy";

function bandIndexes(analyser: AnalyserNode): number[] {
  const hzPerBin = analyser.context.sampleRate / analyser.fftSize;
  return Array.from({ length: CONTROLS }, (_, i) => {
    // Log spacing so low voice harmonics are not squeezed into one band.
    const hz = LOW_HZ * Math.pow(HIGH_HZ / LOW_HZ, i / (CONTROLS - 1));
    return Math.min(analyser.frequencyBinCount - 1, Math.round(hz / hzPerBin));
  });
}

// Periodic Catmull-Rom: a smooth closed curve through the control values.
function outline(controls: Float32Array, t: number): number {
  const scaled = t * CONTROLS;
  const i = Math.floor(scaled);
  const f = scaled - i;
  const p0 = controls[(i - 1 + CONTROLS) % CONTROLS];
  const p1 = controls[i % CONTROLS];
  const p2 = controls[(i + 1) % CONTROLS];
  const p3 = controls[(i + 2) % CONTROLS];
  return (
    0.5 *
    (2 * p1 + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f + (-p0 + 3 * p1 - 3 * p2 + p3) * f * f * f)
  );
}

export function VoiceOrb({
  analyser,
  mode,
  label,
}: {
  analyser: AnalyserNode | null;
  mode: Mode;
  label: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const meterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const ratio = window.devicePixelRatio || 1;
    canvas.width = SIZE * ratio;
    canvas.height = SIZE * ratio;
    context.setTransform(ratio, 0, 0, ratio, 0, 0);

    const styles = getComputedStyle(canvas);
    const palette = PALETTE.map((name) => styles.getPropertyValue(name).trim() || "#29a383");
    const ringColor = styles.getPropertyValue("--accent-a6").trim() || "rgba(41,163,131,0.3)";
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const bins = analyser ? new Uint8Array(analyser.frequencyBinCount) : null;
    const indexes = analyser ? bandIndexes(analyser) : [];
    const controls = new Float32Array(CONTROLS).fill(RESTING_VALUE);
    const center = SIZE / 2;
    let frame = 0;
    let phase = 0;
    let rotation = 0;

    const draw = () => {
      let energy = 0;
      if (analyser && bins) {
        analyser.getByteFrequencyData(bins);
        CONTROL_ORDER.forEach((band, slot) => {
          const target = bins[indexes[band]] / 255;
          // Ease toward the new value so the outline flows rather than jitters.
          controls[slot] = controls[slot] * 0.72 + target * 0.28;
          energy += controls[slot];
        });
        energy /= CONTROLS;
        rotation += 0.0025;
      }
      if (meterRef.current) meterRef.current.setAttribute("aria-valuenow", String(Math.round(energy * 100)));

      const breathe = mode === "busy" && !reduceMotion ? 1 + 0.12 * Math.sin(phase) : 1;
      const inner = INNER_RADIUS + energy * 4;

      context.clearRect(0, 0, SIZE, SIZE);
      context.lineWidth = 1;
      context.lineCap = "butt";

      for (let n = 0; n < LINES; n++) {
        const t = n / LINES;
        const angle = t * Math.PI * 2 + rotation;
        const value = Math.max(0, Math.min(1, outline(controls, t)));
        const length = (MIN_LINE + value * MAX_LINE) * breathe;
        const cos = Math.cos(angle);
        const sin = Math.sin(angle);

        context.globalAlpha = mode === "active" ? 0.4 + 0.4 * value : 0.45;
        context.strokeStyle = palette[Math.floor(t * palette.length * 2) % palette.length];
        context.beginPath();
        context.moveTo(center + cos * inner, center + sin * inner);
        context.lineTo(center + cos * (inner + length), center + sin * (inner + length));
        context.stroke();
      }

      // Hollow centre: a fine ring, no fill.
      context.globalAlpha = 1;
      context.lineWidth = 1.5;
      context.strokeStyle = ringColor;
      context.beginPath();
      context.arc(center, center, inner - 3, 0, Math.PI * 2);
      context.stroke();

      phase += 0.06;
      if (analyser || (mode === "busy" && !reduceMotion)) frame = requestAnimationFrame(draw);
    };

    draw();
    return () => cancelAnimationFrame(frame);
  }, [analyser, mode]);

  return (
    <div
      ref={meterRef}
      className="sv-orb"
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={0}
    >
      <canvas ref={canvasRef} style={{ width: SIZE, height: SIZE }} aria-hidden="true" />
    </div>
  );
}
