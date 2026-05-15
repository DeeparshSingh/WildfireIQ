/**
 * Section 3 — "Fire season starts earlier and ends later." A horizontal bar
 * per year from first-ignition DOY to last-ignition DOY, coloured by total
 * area burned.
 */
import { useClimateRibbon } from "@/lib/api/hooks";

import { InfoChip } from "./InfoChip";
import { SectionShell } from "./SectionShell";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const MONTH_DOYS = [
  { label: "Jan", doy: 1 },
  { label: "Feb", doy: 32 },
  { label: "Mar", doy: 60 },
  { label: "Apr", doy: 91 },
  { label: "May", doy: 121 },
  { label: "Jun", doy: 152 },
  { label: "Jul", doy: 182 },
  { label: "Aug", doy: 213 },
  { label: "Sep", doy: 244 },
  { label: "Oct", doy: 274 },
  { label: "Nov", doy: 305 },
  { label: "Dec", doy: 335 },
];

function intensityColour(area_ha: number, max_ha: number): string {
  const f = Math.min(1, Math.sqrt(area_ha / Math.max(1, max_ha)));
  // sage → amber → ember
  if (f < 0.33) return "hsl(140 55% 50%)";
  if (f < 0.66) return "hsl(45 95% 58%)";
  if (f < 0.9) return "hsl(22 100% 56%)";
  return "hsl(0 80% 52%)";
}

export function Section3_Ribbon() {
  const q = useClimateRibbon();
  const data = q.data ?? [];
  const maxArea = Math.max(1, ...data.map((d) => d.area_burned_ha ?? 0));

  const width = 1080;
  const left = 64;
  const right = 24;
  const usable = width - left - right;
  const rowHeight = 14;
  const rowGap = 4;
  const height = (rowHeight + rowGap) * data.length + 40;

  const xFor = (doy: number) => left + (doy / 365) * usable;

  return (
    <SectionShell
      kicker="Section 3"
      title="The shape of a fire season."
      sub="Each row is one year — bar starts at the day-of-year of the first reported ignition and ends at the last; colour intensity scales with total area burned. Contrary to the global narrative, in the Thompson-Okanagan the data does not show a lengthening season: first-ignition DOY has no significant trend, and end-of-season DOY is actually trending modestly earlier (−1.3 days/yr, CI excludes zero). What has clearly intensified is the burn area within those windows."
      info={
        <InfoChip
          source="BC Wildfire Service · DataBC"
          method="`season_start_doy` = min DOY of fire discoveries; `season_end_doy` = max; Theil-Sen 1000-bootstrap confidence intervals computed at `/api/climate/trends`. Filtered to Thompson-Okanagan bounding box."
          downloadUrl={`${API_BASE}/api/climate/ribbon?format=csv`}
          downloadName="fire_season_ribbon.csv"
        />
      }
    >
      <div
        style={{
          background: "hsl(220 30% 6% / 0.5)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid hsl(200 80% 50% / 0.12)",
          padding: 16,
          overflowX: "auto",
        }}
      >
        <svg width={width} height={height} style={{ minWidth: width, display: "block" }}>
          {/* month gridlines */}
          {MONTH_DOYS.map((m) => (
            <g key={m.label}>
              <line
                x1={xFor(m.doy)}
                y1={20}
                x2={xFor(m.doy)}
                y2={height - 20}
                stroke="hsl(220 20% 18%)"
                strokeOpacity={0.4}
              />
              <text
                x={xFor(m.doy)}
                y={14}
                fontFamily="var(--font-data)"
                fontSize={10}
                fill="hsl(40 12% 72%)"
                textAnchor="middle"
              >
                {m.label}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            if (d.start_doy == null || d.end_doy == null) return null;
            const x1 = xFor(d.start_doy);
            const x2 = xFor(d.end_doy);
            const y = 20 + i * (rowHeight + rowGap);
            return (
              <g key={d.year}>
                <text
                  x={left - 8}
                  y={y + rowHeight - 3}
                  fontFamily="var(--font-data)"
                  fontSize={10}
                  fill="hsl(40 12% 72%)"
                  textAnchor="end"
                >
                  {d.year}
                </text>
                <rect
                  x={x1}
                  y={y}
                  width={Math.max(2, x2 - x1)}
                  height={rowHeight}
                  fill={intensityColour(d.area_burned_ha ?? 0, maxArea)}
                  rx={2}
                  opacity={0.92}
                />
              </g>
            );
          })}
        </svg>

        <div style={{ display: "flex", gap: 12, marginTop: 12, fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-mid)" }}>
          <Legend colour="hsl(140 55% 50%)" label="< 33%" />
          <Legend colour="hsl(45 95% 58%)" label="33–66%" />
          <Legend colour="hsl(22 100% 56%)" label="66–90%" />
          <Legend colour="hsl(0 80% 52%)" label="≥ 90%" />
          <span style={{ marginLeft: "auto" }}>colour = √(area / max) — bar length = season length</span>
        </div>
      </div>
    </SectionShell>
  );
}

function Legend({ colour, label }: { colour: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
      <span style={{ width: 12, height: 8, background: colour, borderRadius: 2, display: "inline-block" }} />
      <span>{label}</span>
    </span>
  );
}
