/**
 * Section 1 — "Three decades of fire". Annual area burned bars with
 * landmark annotations and a Linear / Log y-axis toggle so small years
 * remain visible alongside catastrophic ones (2021 = 663 k ha makes
 * everything ≤ 5 k ha invisible on a linear scale).
 */
import { useState } from "react";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear, scaleSymlog } from "@visx/scale";
import { Bar, Line } from "@visx/shape";

import { useSeasonalMetrics } from "@/lib/api/hooks";

import { InfoChip } from "./InfoChip";
import { SectionShell } from "./SectionShell";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

// Annotations checked against the TO bbox (-121.5°→-118.5° W, 50°→51.5° N).
// 2003: Okanagan Mountain Park (49.65 °N) is south of the bbox; the TO
//       total is dominated by the McLure / Barriere complex north of Kamloops.
// 2017: Elephant Hill (Cache Creek area) is inside the bbox.
// 2018: Province-wide record, but the largest fires (Tweedsmuir, Shovel Lake)
//       were in central interior, outside the TO bbox.
// 2021: Lytton (50.2 °N) and the White Rock Lake fire (~83 k ha) are inside.
// 2023: Bush Creek East and Adams Lake fires dominate the TO total.
const ANNOTATIONS: Record<number, string> = {
  2003: "McLure / Barriere — 26,420 ha, displaced ~10,000 residents (in-bbox)",
  2017: "Elephant Hill — 192,000 ha, largest BC fire of the modern era",
  2018: "Province-wide record (1.35 M ha); the giants were outside the TO bbox",
  2021: "Heat-dome season — White Rock Lake ~83 k ha; Lytton village lost in 15 min",
  2023: "Bush Creek East / Adams Lake complex during a record Canadian season",
};

type Scale = "linear" | "log";

export function Section1_AreaBurned() {
  const q = useSeasonalMetrics();
  const data = (q.data ?? []).filter((d) => d.area_burned_ha != null);

  return (
    <SectionShell
      kicker="Section 1"
      title="Three decades of fire."
      sub="Total area burned each year inside the Thompson-Okanagan bounding box, 1999 → today. The 1999–2010 baseline mean is the dashed line. Use the Log scale to see smaller seasons next to the catastrophic ones."
      info={
        <InfoChip
          source="BC Wildfire Service · DataBC historical fire polygons (PROT_HISTORICAL_FIRE_POLYS_SP)"
          method="Sum of fire-polygon hectares per fire_year, restricted to the Thompson-Okanagan bounding box (-121.5°→-118.5° W, 50°→51.5° N). Every year 1999–today has data — small bars are real, not missing."
          downloadUrl={`${API_BASE}/api/climate/seasonal?format=csv`}
          downloadName="seasonal_metrics.csv"
        />
      }
    >
      <Chart data={data} />
    </SectionShell>
  );
}

function Chart({ data }: { data: Array<{ year: number; area_burned_ha: number | null }> }) {
  const [scaleMode, setScaleMode] = useState<Scale>("linear");
  const [hovered, setHovered] = useState<number | null>(null);

  const width = 1080;
  const height = 400;
  const margin = { top: 24, right: 24, bottom: 40, left: 72 };
  const iw = width - margin.left - margin.right;
  const ih = height - margin.top - margin.bottom;

  if (data.length === 0)
    return (
      <div style={{ padding: 40, color: "var(--color-text-mid)" }}>
        Build `seasonal_metrics.parquet` first.
      </div>
    );

  const years = data.map((d) => d.year);
  const maxArea = Math.max(...data.map((d) => d.area_burned_ha ?? 0));

  const xScale = scaleBand({ domain: years, range: [0, iw], padding: 0.25 });
  const linearY = scaleLinear({ domain: [0, maxArea * 1.05], range: [ih, 0], nice: true });
  // symlog handles zero/very-small values cleanly. Constant 1 → behaves
  // linearly below 1 ha and logarithmically above.
  const logY = scaleSymlog({ domain: [0, maxArea * 1.05], range: [ih, 0], constant: 1 });
  const yScale = scaleMode === "log" ? logY : linearY;

  const baselineYears = data.filter((d) => d.year <= 2010);
  const baseline =
    baselineYears.reduce((s, d) => s + (d.area_burned_ha ?? 0), 0) /
    Math.max(1, baselineYears.length);
  const baselineY = yScale(baseline);

  const tickFormat = (v: number) => {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} M ha`;
    if (v >= 1_000) return `${Math.round(v / 1_000).toLocaleString()} k ha`;
    if (v >= 1) return `${Math.round(v).toLocaleString()} ha`;
    return "0";
  };
  const linearTicks = [0, 1_000, 10_000, 100_000, 500_000, maxArea].filter(
    (t) => t <= maxArea * 1.05,
  );
  const logTicks = [1, 10, 100, 1_000, 10_000, 100_000, 1_000_000].filter(
    (t) => t <= maxArea * 1.05,
  );
  const yTicks = scaleMode === "log" ? logTicks : linearTicks;

  return (
    <div
      style={{
        position: "relative",
        background: "hsl(220 30% 6% / 0.5)",
        borderRadius: "var(--radius-lg)",
        border: "1px solid hsl(200 80% 50% / 0.12)",
        padding: 16,
        overflowX: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8, gap: 4 }}>
        {(["linear", "log"] as const).map((m) => {
          const active = scaleMode === m;
          return (
            <button
              key={m}
              type="button"
              onClick={() => setScaleMode(m)}
              style={{
                padding: "4px 12px",
                background: active ? "hsl(18 95% 54% / 0.18)" : "hsl(220 30% 10% / 0.6)",
                color: active ? "var(--color-text-hi)" : "var(--color-text-mid)",
                border: `1px solid ${active ? "hsl(18 95% 54%)" : "hsl(200 80% 50% / 0.18)"}`,
                borderRadius: 999,
                fontFamily: "var(--font-data)",
                fontSize: 10,
                letterSpacing: "0.18em",
                textTransform: "uppercase",
                cursor: "pointer",
              }}
            >
              {m}
            </button>
          );
        })}
      </div>

      <svg width={width} height={height} style={{ minWidth: width, display: "block" }}>
        <Group left={margin.left} top={margin.top}>
          <GridRows
            scale={yScale}
            width={iw}
            tickValues={yTicks}
            stroke="hsl(220 20% 18%)"
            strokeOpacity={0.6}
          />
          {data.map((d) => {
            const value = d.area_burned_ha ?? 0;
            const ann = ANNOTATIONS[d.year];
            const bx = xScale(d.year) ?? 0;
            // Guarantee a 2-px minimum bar so the smallest real years
            // remain visible — the data is never zero in this dataset.
            const rawBy = yScale(value);
            const minBarHeight = 2;
            const by = Math.min(rawBy, ih - minBarHeight);
            return (
              <g
                key={d.year}
                onMouseEnter={() => setHovered(d.year)}
                onMouseLeave={() => setHovered((h) => (h === d.year ? null : h))}
              >
                <Bar
                  x={bx}
                  y={by}
                  width={xScale.bandwidth()}
                  height={ih - by}
                  fill={ann ? "hsl(18 95% 54%)" : "hsl(18 95% 54%)"}
                  opacity={hovered === d.year ? 1 : ann ? 1 : 0.78}
                  rx={2}
                />
                {ann && (
                  <Bar
                    x={bx}
                    y={by - 4}
                    width={xScale.bandwidth()}
                    height={3}
                    fill="hsl(45 95% 58%)"
                  />
                )}
                {/* Invisible hit-target spanning the full column for easy hover. */}
                <rect
                  x={bx}
                  y={0}
                  width={xScale.bandwidth()}
                  height={ih}
                  fill="transparent"
                />
              </g>
            );
          })}

          {Number.isFinite(baselineY) && baseline > 0 && (
            <Line
              from={{ x: 0, y: baselineY }}
              to={{ x: iw, y: baselineY }}
              stroke="hsl(40 30% 96% / 0.5)"
              strokeWidth={1}
              strokeDasharray="4 6"
            />
          )}

          <AxisBottom
            top={ih}
            scale={xScale}
            stroke="hsl(220 15% 32%)"
            tickStroke="hsl(220 15% 32%)"
            tickValues={years.filter((y) => y % 4 === 0)}
            tickLabelProps={() => ({
              fill: "hsl(40 12% 72%)",
              fontFamily: "var(--font-data)",
              fontSize: 10,
              textAnchor: "middle",
              dy: "0.25em",
            })}
          />
          <AxisLeft
            scale={yScale}
            stroke="hsl(220 15% 32%)"
            tickStroke="hsl(220 15% 32%)"
            tickValues={yTicks}
            tickFormat={(v) => tickFormat(Number(v))}
            tickLabelProps={() => ({
              fill: "hsl(40 12% 72%)",
              fontFamily: "var(--font-data)",
              fontSize: 10,
              textAnchor: "end",
              dx: "-0.4em",
              dy: "0.3em",
            })}
          />

          {/* Tooltip readout for the hovered year. */}
          {hovered !== null &&
            (() => {
              const row = data.find((r) => r.year === hovered);
              if (!row) return null;
              const bx = (xScale(hovered) ?? 0) + xScale.bandwidth() / 2;
              const by = Math.max(yScale(row.area_burned_ha ?? 0), 10) - 8;
              const value = (row.area_burned_ha ?? 0).toLocaleString(undefined, {
                maximumFractionDigits: 0,
              });
              return (
                <g pointerEvents="none">
                  <rect
                    x={bx - 60}
                    y={by - 30}
                    width={120}
                    height={26}
                    rx={4}
                    fill="hsl(220 30% 10% / 0.95)"
                    stroke="hsl(200 80% 50% / 0.35)"
                  />
                  <text
                    x={bx}
                    y={by - 13}
                    fontFamily="var(--font-data)"
                    fontSize={11}
                    fill="hsl(40 30% 96%)"
                    textAnchor="middle"
                  >
                    {hovered} · {value} ha
                  </text>
                </g>
              );
            })()}
        </Group>
      </svg>

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", fontFamily: "var(--font-data)", fontSize: 10, color: "var(--color-text-mid)", marginTop: 6 }}>
        <span>27 years · every year shown · hover a column for the exact hectares</span>
        <span>baseline (1999–2010 mean): {Math.round(baseline).toLocaleString()} ha</span>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8, marginTop: 16 }}>
        {Object.entries(ANNOTATIONS).map(([year, note]) => {
          const row = data.find((d) => d.year === Number(year));
          return (
            <div
              key={year}
              style={{
                padding: "8px 12px",
                background: "hsl(45 95% 58% / 0.08)",
                border: "1px solid hsl(45 95% 58% / 0.3)",
                borderRadius: 8,
                fontFamily: "var(--font-body)",
                fontSize: 11,
                lineHeight: 1.5,
                color: "var(--color-text-hi)",
              }}
            >
              <strong style={{ color: "hsl(45 95% 70%)" }}>{year}</strong>
              {row && row.area_burned_ha != null
                ? ` · ${row.area_burned_ha.toLocaleString(undefined, { maximumFractionDigits: 0 })} ha in TO`
                : ""}
              <div style={{ color: "var(--color-text-mid)", marginTop: 2 }}>{note}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
