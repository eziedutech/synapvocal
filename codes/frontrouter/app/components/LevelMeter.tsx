// Shows that the microphone is hearing something. Speech RMS rarely exceeds
// ~0.3, so the value is scaled up for a readable bar.
export function LevelMeter({ level, active }: { level: number; active: boolean }) {
  const percent = active ? Math.min(100, Math.round(level * 400)) : 0;
  return (
    <div
      className="sv-level"
      role="meter"
      aria-label="Microphone level"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className="sv-level-fill" style={{ width: `${percent}%` }} />
    </div>
  );
}
