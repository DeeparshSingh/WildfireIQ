/**
 * Section 6 — "TRU campus carbon." Renders only when both:
 *   1. `VITE_ENABLE_TRU_CARBON=true` is set, and
 *   2. The backend reports `data.available === true` (i.e.
 *      `data/tru_carbon.csv` exists).
 * Otherwise this component returns null — the section is fully hidden, not
 * left as an empty husk.
 */
import { AxisBottom, AxisLeft } from "@visx/axis";
import { Group } from "@visx/group";
import { scaleLinear, scaleBand } from "@visx/scale";
import { Bar, Line } from "@visx/shape";

import { useTruCarbon } from "@/lib/api/hooks";

import { InfoChip } from "./InfoChip";
import { SectionShell } from "./SectionShell";

export function Section6_TruCarbon() {
  const flag = import.meta.env.VITE_ENABLE_TRU_CARBON === "true";
  const q = useTruCarbon();
  if (!flag) return null;
  if (!q.data?.available) return null;

  const rows = (q.data.rows as { year: number; tco2e: number; target?: number }[]) ?? [];
  if (rows.length === 0) return null;

  return (
    <SectionShell
      kicker="Section 6"
      title="TRU campus carbon."
      sub="Annual reported tonnes of CO₂-equivalent emissions for Thompson Rivers University. The dashed line is the Sustainability Office target."
      info={
        <InfoChip
          source="TRU Sustainability Office"
          method="Direct read of institutional carbon disclosures."
        />
      }
    >
      <Chart rows={rows} />
    </SectionShell>
  );
}

function Chart({ rows }: { rows: { year: number; tco2e: number; target?: number }[] }) {
  const width = 1080;
  const height = 320;
  const margin = { top: 20, right: 24, bottom: 36, left: 64 };
  const iw = width - margin.left - margin.right;
  const ih = height - margin.top - margin.bottom;

  const years = rows.map((r) => r.year);
  const yMax = Math.max(...rows.map((r) => r.tco2e), ...rows.map((r) => r.target ?? 0));

  const xScale = scaleBand({ domain: years, range: [0, iw], padding: 0.25 });
  const yScale = scaleLinear({ domain: [0, yMax * 1.1], range: [ih, 0], nice: true });

  return (
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
        <Group left={margin.left} top={margin.top}>
          {rows.map((r) => {
            const bx = xScale(r.year) ?? 0;
            const by = yScale(r.tco2e);
            return (
              <Bar
                key={r.year}
                x={bx}
                y={by}
                width={xScale.bandwidth()}
                height={ih - by}
                fill="hsl(265 60% 60%)"
                rx={2}
              />
            );
          })}
          {rows[0]?.target != null && (
            <Line
              from={{ x: 0, y: yScale(rows[0].target!) }}
              to={{ x: iw, y: yScale(rows[rows.length - 1].target ?? rows[0].target!) }}
              stroke="hsl(40 30% 96% / 0.7)"
              strokeWidth={1.5}
              strokeDasharray="4 6"
            />
          )}
          <AxisBottom top={ih} scale={xScale} stroke="hsl(220 15% 32%)" tickStroke="hsl(220 15% 32%)" tickLabelProps={() => ({ fill: "hsl(40 12% 72%)", fontFamily: "var(--font-data)", fontSize: 10, textAnchor: "middle", dy: "0.25em" })} />
          <AxisLeft scale={yScale} stroke="hsl(220 15% 32%)" tickStroke="hsl(220 15% 32%)" numTicks={5} tickLabelProps={() => ({ fill: "hsl(40 12% 72%)", fontFamily: "var(--font-data)", fontSize: 10, textAnchor: "end", dx: "-0.4em", dy: "0.3em" })} />
        </Group>
      </svg>
    </div>
  );
}
