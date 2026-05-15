/**
 * Section 4 — "What's coming." July temperature projections under
 * SSP1-2.6 / SSP2-4.5 / SSP5-8.5 with ensemble q10–q90 bands. User toggles
 * scenarios via segmented control.
 */
import { useState } from "react";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows } from "@visx/grid";
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { AreaClosed, LinePath } from "@visx/shape";

import { useProjectionsAll, type ProjectionRow } from "@/lib/api/hooks";

import { InfoChip } from "./InfoChip";
import { SectionShell } from "./SectionShell";

type Ssp = "ssp126" | "ssp245" | "ssp585";

const SCENARIOS: { id: Ssp; label: string; colour: string; band: string }[] = [
  { id: "ssp126", label: "SSP1-2.6 · low", colour: "hsl(140 55% 55%)", band: "hsl(140 55% 55% / 0.18)" },
  { id: "ssp245", label: "SSP2-4.5 · middle", colour: "hsl(45 95% 58%)", band: "hsl(45 95% 58% / 0.18)" },
  { id: "ssp585", label: "SSP5-8.5 · high", colour: "hsl(0 80% 55%)", band: "hsl(0 80% 55% / 0.18)" },
];

const VARIABLES = [
  { id: "tasmean", label: "Mean temperature (°C)" },
  { id: "tasmax", label: "Max temperature (°C)" },
  { id: "pr", label: "Annual precipitation (mm)" },
];

export function Section4_Projections() {
  const [variable, setVariable] = useState("tasmean");
  const [enabled, setEnabled] = useState<Set<Ssp>>(new Set(["ssp126", "ssp245", "ssp585"]));
  const q = useProjectionsAll(variable);

  const toggle = (s: Ssp) =>
    setEnabled((cur) => {
      const next = new Set(cur);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });

  return (
    <SectionShell
      kicker="Section 4"
      title="What's coming."
      sub="CMIP6-shape ensemble projections under three emission pathways. Bands show ensemble q10–q90 spread; line is the q50 (median) member. Observed = historical Kamloops record. ⚠ The projection rows in this build are a synthetic placeholder with the correct shape, not the live ClimateData.ca download — the trend direction is illustrative; absolute values shift when the real ensemble is dropped into `data/processed/climate_projections.parquet`."
      info={
        <InfoChip
          source="ClimateData.ca CMIP6 multi-model ensemble (placeholder in this build)"
          method="Per-scenario q10/q50/q90 members from the projection parquet. Phase 1 ships a synthetic placeholder with realistic shape; the real CMIP6 ensemble is a drop-in parquet replace."
        />
      }
    >
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginBottom: 12 }}>
        <select
          value={variable}
          onChange={(e) => setVariable(e.target.value)}
          style={selectStyle}
        >
          {VARIABLES.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
            </option>
          ))}
        </select>
        <div style={{ display: "flex", gap: 4 }}>
          {SCENARIOS.map((s) => {
            const on = enabled.has(s.id);
            return (
              <button
                key={s.id}
                type="button"
                onClick={() => toggle(s.id)}
                style={{
                  padding: "8px 14px",
                  borderRadius: 999,
                  background: on ? `${s.colour.replace(")", " / 0.18)").replace("hsl(", "hsl(")}` : "hsl(220 30% 10% / 0.6)",
                  border: `1px solid ${on ? s.colour : "hsl(200 80% 50% / 0.15)"}`,
                  color: on ? "var(--color-text-hi)" : "var(--color-text-mid)",
                  fontFamily: "var(--font-data)",
                  fontSize: 11,
                  letterSpacing: "0.08em",
                  cursor: "pointer",
                }}
              >
                {s.label}
              </button>
            );
          })}
        </div>
      </div>
      <Chart
        observed={q.data?.scenarios.observed ?? []}
        ssp126={enabled.has("ssp126") ? q.data?.scenarios.ssp126 ?? [] : []}
        ssp245={enabled.has("ssp245") ? q.data?.scenarios.ssp245 ?? [] : []}
        ssp585={enabled.has("ssp585") ? q.data?.scenarios.ssp585 ?? [] : []}
      />
    </SectionShell>
  );
}

function Chart({
  observed,
  ssp126,
  ssp245,
  ssp585,
}: {
  observed: ProjectionRow[];
  ssp126: ProjectionRow[];
  ssp245: ProjectionRow[];
  ssp585: ProjectionRow[];
}) {
  const width = 1080;
  const height = 380;
  const margin = { top: 20, right: 24, bottom: 36, left: 64 };
  const iw = width - margin.left - margin.right;
  const ih = height - margin.top - margin.bottom;

  const allRows = [...observed, ...ssp126, ...ssp245, ...ssp585];
  if (allRows.length === 0) {
    return <div style={{ padding: 40, color: "var(--color-text-mid)" }}>Loading projections…</div>;
  }

  const xMin = Math.min(...allRows.map((r) => r.year));
  const xMax = Math.max(...allRows.map((r) => r.year));
  const yMin = Math.min(...allRows.map((r) => r.q10));
  const yMax = Math.max(...allRows.map((r) => r.q90));

  const xScale = scaleLinear({ domain: [xMin, xMax], range: [0, iw] });
  const yScale = scaleLinear({ domain: [yMin - 0.5, yMax + 0.5], range: [ih, 0], nice: true });

  const renderScenario = (rows: ProjectionRow[], colour: string, band: string, key: string) => {
    if (rows.length === 0) return null;
    return (
      <g key={key}>
        <AreaClosed
          data={rows}
          x={(d) => xScale(d.year)}
          y0={(d) => yScale(d.q10)}
          y1={(d) => yScale(d.q90)}
          yScale={yScale}
          fill={band}
        />
        <LinePath
          data={rows}
          x={(d) => xScale(d.year)}
          y={(d) => yScale(d.q50)}
          stroke={colour}
          strokeWidth={2}
        />
      </g>
    );
  };

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
          <GridRows scale={yScale} width={iw} stroke="hsl(220 20% 18%)" strokeOpacity={0.5} />

          {renderScenario(ssp585, "hsl(0 80% 55%)", "hsl(0 80% 55% / 0.18)", "ssp585")}
          {renderScenario(ssp245, "hsl(45 95% 58%)", "hsl(45 95% 58% / 0.18)", "ssp245")}
          {renderScenario(ssp126, "hsl(140 55% 55%)", "hsl(140 55% 55% / 0.18)", "ssp126")}

          {observed.length > 0 && (
            <LinePath
              data={observed}
              x={(d) => xScale(d.year)}
              y={(d) => yScale(d.q50)}
              stroke="hsl(40 30% 96%)"
              strokeWidth={2.5}
            />
          )}

          <AxisBottom
            top={ih}
            scale={xScale}
            stroke="hsl(220 15% 32%)"
            tickStroke="hsl(220 15% 32%)"
            numTicks={6}
            tickFormat={(v) => `${v}`}
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
    </div>
  );
}

const selectStyle: React.CSSProperties = {
  background:
    "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path d='M1 1l4 4 4-4' stroke='%2399aabb' stroke-width='1.5' fill='none' stroke-linecap='round' stroke-linejoin='round'/></svg>\") no-repeat right 12px center / 10px 6px, hsl(220 30% 8% / 0.85)",
  color: "var(--color-text-hi)",
  border: "1px solid hsl(200 80% 50% / 0.25)",
  borderRadius: 8,
  padding: "8px 32px 8px 12px",
  fontFamily: "var(--font-body)",
  fontSize: 13,
  appearance: "none",
  WebkitAppearance: "none",
  MozAppearance: "none",
  cursor: "pointer",
};
