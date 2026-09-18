import { Flex, Text } from "@radix-ui/themes";
import { useState } from "react";

// Horizontal bars, drawn as plain SVG. Specs: bars at most 20px thick, a 4px rounded
// data end and a square baseline, hairline solid grid, values at the bar tip in text
// ink (never the series colour), and each bar is its own focusable hover target.

export type BarSeries = { key: string; label: string; color: string };
// axisLabel: what the axis shows, when shorter than label ("" to show nothing, e.g. the
// second bar of a group). label stays the full name for tooltips and screen readers.
export type BarRow = { label: string; value: number; series: string; detail?: string; group?: string; axisLabel?: string };

const LABEL_W = 190;
const VALUE_W = 64;
const ROW_H = 34;
const BAR_H = 18;
const GROUP_GAP = 14;
const WIDTH = 720;

function barPath(x0: number, y: number, width: number, height: number): string {
  const r = Math.min(4, width);
  const x1 = x0 + width;
  return `M${x0},${y} H${x1 - r} Q${x1},${y} ${x1},${y + r} V${y + height - r} Q${x1},${y + height} ${x1 - r},${y + height} H${x0} Z`;
}

export function BarChart({
  rows,
  series,
  max,
  format,
  reference,
  ticks,
}: {
  rows: BarRow[];
  series: BarSeries[];
  max: number;
  format: (value: number) => string;
  reference?: { value: number; label: string };
  ticks: number[];
}) {
  const [hover, setHover] = useState<number | null>(null);
  const colorOf = (key: string) => series.find((s) => s.key === key)?.color ?? "var(--gray-8)";
  const plotW = WIDTH - LABEL_W - VALUE_W;
  const x = (value: number) => LABEL_W + (Math.min(value, max) / max) * plotW;

  let y = 8;
  let previousGroup: string | undefined;
  const placed = rows.map((row) => {
    if (row.group !== undefined && previousGroup !== undefined && row.group !== previousGroup) y += GROUP_GAP;
    previousGroup = row.group;
    const top = y;
    y += ROW_H;
    return { row, top };
  });
  const axisY = y + 4;
  const height = axisY + 22;
  const active = hover === null ? null : placed[hover];

  return (
    <Flex direction="column" gap="3">
      {series.length > 1 && (
        <Flex gap="4" wrap="wrap" aria-hidden="true">
          {series.map((s) => (
            <Flex key={s.key} align="center" gap="2">
              <span className="sv-legend-swatch" style={{ background: s.color }} />
              <Text size="2" color="gray">
                {s.label}
              </Text>
            </Flex>
          ))}
        </Flex>
      )}
      <div className="sv-chart">
        <svg viewBox={`0 0 ${WIDTH} ${height}`} width="100%" role="img" aria-label="Bar chart, also available as a table">
          {ticks.map((tick) => (
            <g key={tick}>
              <line x1={x(tick)} x2={x(tick)} y1={4} y2={axisY} className="sv-chart-grid" />
              <text x={x(tick)} y={axisY + 16} textAnchor="middle" className="sv-chart-tick">
                {format(tick)}
              </text>
            </g>
          ))}
          {reference && (
            <g>
              <line x1={x(reference.value)} x2={x(reference.value)} y1={0} y2={axisY} className="sv-chart-reference" />
            </g>
          )}
          {placed.map(({ row, top }, index) => {
            const barY = top + (ROW_H - BAR_H) / 2;
            const width = Math.max(1, x(row.value) - LABEL_W);
            const dim = hover !== null && hover !== index;
            return (
              <g
                key={`${row.label}-${index}`}
                tabIndex={0}
                className="sv-chart-bar"
                onPointerEnter={() => setHover(index)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(index)}
                onBlur={() => setHover(null)}
                aria-label={`${row.label}: ${format(row.value)}`}
              >
                <rect x={0} y={top} width={WIDTH} height={ROW_H} fill="transparent" />
                <text x={LABEL_W - 12} y={top + ROW_H / 2} textAnchor="end" dominantBaseline="central" className="sv-chart-label">
                  {row.axisLabel ?? row.label}
                </text>
                <path d={barPath(LABEL_W, barY, width, BAR_H)} fill={colorOf(row.series)} opacity={dim ? 0.45 : 1} />
                <text x={LABEL_W + width + 8} y={top + ROW_H / 2} dominantBaseline="central" className="sv-chart-value">
                  {format(row.value)}
                </text>
              </g>
            );
          })}
          <line x1={LABEL_W} x2={LABEL_W} y1={4} y2={axisY} className="sv-chart-axis" />
        </svg>
        {active && (
          <div
            className="sv-chart-tooltip"
            role="status"
            style={{ left: `${(x(active.row.value) / WIDTH) * 100}%`, top: `${((active.top + ROW_H) / height) * 100}%` }}
          >
            <Text size="3" weight="bold">
              {format(active.row.value)}
            </Text>
            <Text size="2" color="gray">
              {active.row.label}
              {series.length > 1 ? `, ${series.find((s) => s.key === active.row.series)?.label}` : ""}
            </Text>
            {active.row.detail && <Text size="1" color="gray">{active.row.detail}</Text>}
          </div>
        )}
      </div>
      {reference && (
        <Flex align="center" gap="2" aria-hidden="true">
          <span className="sv-legend-reference" />
          <Text size="2" color="gray">
            {reference.label}
          </Text>
        </Flex>
      )}
    </Flex>
  );
}
