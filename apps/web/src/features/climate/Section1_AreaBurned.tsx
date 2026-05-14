/**
 * Section 1 — "Three decades of fire". Annual area burned bars + landmark
 * annotations for 2003, 2017, 2018, 2021, 2023.
 */
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear } from "@visx/scale";
import { Bar, Line } from "@visx/shape";

import { useSeasonalMetrics } from "@/lib/api/hooks";

import { InfoChip } from "./InfoChip";
import { SectionShell } from "./SectionShell";

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const ANNOTATIONS: Record<number, string> = {
  2003: "Okanagan Mountain Park fire — 25,600 ha, 239 homes",
  2017: "Elephant Hill — 192,000 ha, largest BC fire of the modern era",
  2018: "Worst on record at the time — 1.35 M ha province-wide",
  2021: "Lytton heat dome — village destroyed in 15 min",
  2023: "Record Canadian season — 15 M ha nationwide",
};

export function Section1_AreaBurned() {
  const q = useSeasonalMetrics();
  const data = (q.data ?? []).filter((d) => d.area_burned_ha != null);

  return (
    <SectionShell
      kicker="Section 1"
      title="Three decades of fire."
      sub="Total area burned each year in the Thompson-Okanagan, 1999 → today. The 1999–2010 baseline mean is drawn as the dashed reference line."
      info={
        <InfoChip
          source="BC Wildfire Service · DataBC historical fire polygons (PROT_HISTORICAL_FIRE_POLYS_SP)"
          method="Sum of fire polygon hectares per fire_year, filtered to the Thompson-Okanagan bounding box."
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
  const width = 1080;
  const height = 380;
  const margin = { top: 24, right: 24, bottom: 40, left: 64 };
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
  const yScale = scaleLinear({ domain: [0, maxArea * 1.05], range: [ih, 0], nice: true });

  // Baseline mean 1999-2010
  const baseline =
    data.filter((d) => d.year <= 2010).reduce((s, d) => s + (d.area_burned_ha ?? 0), 0) /
    Math.max(1, data.filter((d) => d.year <= 2010).length);
  const baselineY = yScale(baseline);

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
      <svg width={width} height={height} style={{ minWidth: width, display: "block" }}>
        <Group left={margin.left} top={margin.top}>
          <GridRows scale={yScale} width={iw} stroke="hsl(220 20% 18%)" strokeOpacity={0.6} />
          {data.map((d) => {
            const ann = ANNOTATIONS[d.year];
            const bx = xScale(d.year) ?? 0;
            const by = yScale(d.area_burned_ha ?? 0);
            return (
              <g key={d.year}>
                <Bar
                  x={bx}
                  y={by}
                  width={xScale.bandwidth()}
                  height={ih - by}
                  fill="hsl(18 95% 54%)"
                  opacity={ann ? 1 : 0.78}
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
              </g>
            );
          })}
          {Number.isFinite(baselineY) && (
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
            numTicks={5}
            tickFormat={(v) => {
              const n = Number(v);
              if (n >= 1000) return `${(n / 1000).toFixed(0)} k ha`;
              return `${n.toFixed(0)} ha`;
            }}
            tickLabelProps={() => ({
              fill: "hsl(40 12% 72%)",
              fontFamily: "var(--font-data)",
              fontSize: 10,
              textAnchor: "end",
              dx: "-0.4em",
              dy: "0.3em",
            })}
          />
        </Group>
      </svg>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 8, marginTop: 12 }}>
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
                ? ` · ${row.area_burned_ha.toLocaleString(undefined, { maximumFractionDigits: 0 })} ha`
                : ""}
              <div style={{ color: "var(--color-text-mid)", marginTop: 2 }}>{note}</div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
