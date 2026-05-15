/**
 * Section 5 — "What this means for fire weather." Decade-by-decade
 * projection of `days FWI ≥ 19` (extreme threshold) under three SSP
 * scenarios. Explicitly disclosed as a coarse extrapolation.
 */
import { AxisBottom, AxisLeft } from "@visx/axis";
import { Group } from "@visx/group";
import { scaleBand, scaleLinear } from "@visx/scale";
import { Bar } from "@visx/shape";

import { useFwiProjection } from "@/lib/api/hooks";

import { InfoChip } from "./InfoChip";
import { SectionShell } from "./SectionShell";

const SCENARIOS = [
  { id: "ssp126", label: "SSP1-2.6", colour: "hsl(140 55% 55%)" },
  { id: "ssp245", label: "SSP2-4.5", colour: "hsl(45 95% 58%)" },
  { id: "ssp585", label: "SSP5-8.5", colour: "hsl(0 80% 55%)" },
];

const DECADES = [2000, 2010, 2020, 2030, 2040];

export function Section5_FwiProjection() {
  const q = useFwiProjection();
  const data = q.data;

  const width = 1080;
  const height = 360;
  const margin = { top: 20, right: 24, bottom: 60, left: 64 };
  const iw = width - margin.left - margin.right;
  const ih = height - margin.top - margin.bottom;

  const xOuter = scaleBand({ domain: DECADES.map(String), range: [0, iw], padding: 0.2 });
  const xInner = scaleBand({ domain: SCENARIOS.map((s) => s.id), range: [0, xOuter.bandwidth()], padding: 0.1 });

  const allValues: number[] = [];
  if (data?.scenarios) {
    for (const s of SCENARIOS) {
      for (const row of data.scenarios[s.id] ?? []) {
        allValues.push(row.days_fwi_ge_19);
      }
    }
  }
  const yMax = Math.max(180, ...allValues);
  const yScale = scaleLinear({ domain: [0, yMax * 1.1], range: [ih, 0], nice: true });

  return (
    <SectionShell
      kicker="Section 5"
      title="What this means for fire weather."
      sub="Days per year with FWI ≥ 19 — the CFFDRS threshold for likely crown-fire behaviour. Observed 2000s, 2010s, 2020s come from running our Van Wagner port on real ERA5 weather and counting threshold-crossing days. Projected 2030s and 2040s use a coarse linear extrapolation (one predictor, July temperature) — disclosed in full under the (i) chip. Not a physics-driven projection."
      info={
        <InfoChip
          source="WildfireIQ derived from Open-Meteo ERA5 + Van Wagner FWI port + ClimateData.ca CMIP6 placeholder"
          method={
            data?.method ??
            "Linear regression of historical July mean temp → days FWI≥19, evaluated on per-decade projected July temperatures. Coarse heuristic — not a physics-driven projection."
          }
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
          <Group left={margin.left} top={margin.top}>
            {DECADES.map((dec) => {
              const dx = xOuter(String(dec)) ?? 0;
              return (
                <g key={dec} transform={`translate(${dx}, 0)`}>
                  {SCENARIOS.map((s) => {
                    const row = data?.scenarios[s.id]?.find((r) => r.decade === dec);
                    if (!row) return null;
                    const bw = xInner.bandwidth();
                    const bx = xInner(s.id) ?? 0;
                    const by = yScale(row.days_fwi_ge_19);
                    return (
                      <g key={s.id}>
                        <Bar
                          x={bx}
                          y={by}
                          width={bw}
                          height={ih - by}
                          fill={s.colour}
                          opacity={row.observed ? 0.95 : 0.6}
                          rx={2}
                        />
                        {!row.observed && (
                          <Bar
                            x={bx}
                            y={by}
                            width={bw}
                            height={ih - by}
                            fill="url(#stripe)"
                            opacity={0.25}
                          />
                        )}
                        <text
                          x={bx + bw / 2}
                          y={by - 4}
                          fontFamily="var(--font-data)"
                          fontSize={9}
                          fill="var(--color-text-mid)"
                          textAnchor="middle"
                        >
                          {row.days_fwi_ge_19}
                        </text>
                      </g>
                    );
                  })}
                </g>
              );
            })}

            <defs>
              <pattern id="stripe" patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
                <line x1="0" y1="0" x2="0" y2="6" stroke="white" strokeWidth="2" />
              </pattern>
            </defs>

            <AxisBottom
              top={ih}
              scale={xOuter}
              stroke="hsl(220 15% 32%)"
              tickStroke="hsl(220 15% 32%)"
              tickFormat={(v) => `${v}s`}
              tickLabelProps={() => ({
                fill: "hsl(40 12% 72%)",
                fontFamily: "var(--font-data)",
                fontSize: 11,
                textAnchor: "middle",
                dy: "0.5em",
              })}
            />
            <AxisLeft
              scale={yScale}
              stroke="hsl(220 15% 32%)"
              tickStroke="hsl(220 15% 32%)"
              numTicks={5}
              label="Days FWI ≥ 19"
              labelProps={{ fill: "hsl(40 12% 72%)", fontFamily: "var(--font-data)", fontSize: 11, textAnchor: "middle" }}
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

        <div style={{ display: "flex", gap: 16, marginTop: 12, flexWrap: "wrap", fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-mid)" }}>
          {SCENARIOS.map((s) => (
            <span key={s.id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
              <span style={{ width: 12, height: 8, background: s.colour, borderRadius: 2, display: "inline-block" }} />
              {s.label}
            </span>
          ))}
          <span style={{ marginLeft: "auto" }}>solid = observed · striped = projected (heuristic)</span>
        </div>
      </div>
    </SectionShell>
  );
}
