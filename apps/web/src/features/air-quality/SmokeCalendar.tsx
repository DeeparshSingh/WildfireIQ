import type { AqCalendar, AqCalendarDay } from "@/lib/api/hooks";

import { aqhiColor } from "./aqColors";

/**
 * GitHub-style contribution heatmap of daily max-AQHI for the last N weeks.
 * Hover any cell for the underlying date + max-PM2.5.
 */

const CELL = 12;
const GAP = 3;

function dayOfWeek(d: Date): number {
  return d.getUTCDay(); // 0 = Sun
}

export function SmokeCalendar({ data }: { data: AqCalendar }) {
  if (!data.days.length) {
    return (
      <div
        style={{
          padding: 24,
          fontFamily: "var(--font-body)",
          fontSize: 13,
          color: "var(--color-text-low)",
        }}
      >
        No calendar data yet.
      </div>
    );
  }

  // Index by ISO date for O(1) lookup.
  const byDay = new Map<string, AqCalendarDay>();
  for (const r of data.days) byDay.set(r.day_utc, r);

  const last = new Date(`${data.days[data.days.length - 1].day_utc}T00:00:00Z`);
  // Always end on the most recent Saturday so the rightmost column is full.
  const endSat = new Date(last);
  endSat.setUTCDate(endSat.getUTCDate() + (6 - dayOfWeek(endSat)));
  const firstSun = new Date(endSat);
  firstSun.setUTCDate(firstSun.getUTCDate() - (data.days.length + 14));
  // Align to Sunday
  firstSun.setUTCDate(firstSun.getUTCDate() - dayOfWeek(firstSun));

  const totalDays = Math.round((+endSat - +firstSun) / 86_400_000) + 1;
  const weeks = Math.ceil(totalDays / 7);
  const W = weeks * (CELL + GAP) + GAP;
  const H = 7 * (CELL + GAP) + GAP;

  const cells: { x: number; y: number; iso: string; row?: AqCalendarDay }[] = [];
  for (let i = 0; i < totalDays; i++) {
    const d = new Date(firstSun);
    d.setUTCDate(d.getUTCDate() + i);
    const iso = d.toISOString().slice(0, 10);
    const col = Math.floor(i / 7);
    const row = i % 7;
    cells.push({
      x: GAP + col * (CELL + GAP),
      y: GAP + row * (CELL + GAP),
      iso,
      row: byDay.get(iso),
    });
  }

  return (
    <div style={{ overflowX: "auto" }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Smoke calendar">
        {cells.map((c) => (
          <rect
            key={c.iso}
            x={c.x}
            y={c.y}
            width={CELL}
            height={CELL}
            rx={2}
            fill={c.row ? aqhiColor(c.row.max_aqhi) : "var(--color-bg-2)"}
            opacity={c.row ? 1 : 0.5}
            stroke={c.row ? "var(--color-stroke-strong)" : "transparent"}
            strokeWidth={0.5}
          >
            <title>
              {c.iso}
              {c.row
                ? ` · max PM2.5 ${c.row.max_pm25.toFixed(1)} µg/m³ · AQHI ${c.row.max_aqhi.toFixed(1)}`
                : " · no data"}
            </title>
          </rect>
        ))}
      </svg>
      <div
        style={{
          marginTop: 10,
          display: "flex",
          gap: 14,
          alignItems: "center",
          fontFamily: "var(--font-data)",
          fontSize: 9,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--color-text-low)",
        }}
      >
        <span>less</span>
        {[1, 3, 5, 7, 9, 11].map((a) => (
          <span
            key={a}
            style={{
              width: CELL,
              height: CELL,
              borderRadius: 2,
              background: aqhiColor(a),
              display: "inline-block",
            }}
          />
        ))}
        <span>more</span>
      </div>
    </div>
  );
}
