/**
 * Section 2 — "Hotter, drier, longer". Three stacked sparkline panels for
 * July temp, July-Aug precipitation, July-Aug VPD with Theil-Sen trend
 * lines and bootstrap-CI slope labels.
 */
import { Group } from "@visx/group";
import { scaleLinear } from "@visx/scale";
import { LinePath, Line } from "@visx/shape";

import { useClimateTrends, useSeasonalMetrics, type SeasonalRow, type TrendMetric } from "@/lib/api/hooks";

import { InfoChip } from "./InfoChip";
import { SectionShell } from "./SectionShell";

type Panel = {
  metric: keyof SeasonalRow;
  label: string;
  unit: string;
  fmt: (v: number) => string;
  colour: string;
};

const PANELS: Panel[] = [
  {
    metric: "mean_jul_temp_c",
    label: "Mean July daily max temperature",
    unit: "°C",
    fmt: (v) => `${v.toFixed(1)} °C`,
    colour: "hsl(18 95% 54%)",
  },
  {
    metric: "julaug_precip_mm",
    label: "July–August total precipitation",
    unit: "mm",
    fmt: (v) => `${v.toFixed(0)} mm`,
    colour: "hsl(185 90% 55%)",
  },
  {
    metric: "mean_julaug_vpd_kpa",
    label: "Mean July–August vapour pressure deficit",
    unit: "kPa",
    fmt: (v) => `${v.toFixed(2)} kPa`,
    colour: "hsl(45 95% 58%)",
  },
];

export function Section2_Trends() {
  const seasonal = useSeasonalMetrics();
  const trends = useClimateTrends();
  const data = seasonal.data ?? [];

  return (
    <SectionShell
      kicker="Section 2"
      title="Hotter, drier air."
      sub="Theil-Sen slopes (robust to outlier years) with 95% bootstrap confidence intervals over 1999–present at Kamloops Airport (ERA5 reanalysis via Open-Meteo). July daily-max temperature is climbing significantly; July–August precipitation has no significant trend, but vapour pressure deficit is rising — the air is getting thirstier even when rainfall holds steady."
      info={
        <InfoChip
          source="Open-Meteo ERA5 archive · Kamloops Airport"
          method="Theil-Sen median slope estimator. 1000-bootstrap 95% CI. Slope expressed per year; Δ-over-span = slope × (year_max − year_min)."
        />
      }
    >
      <div style={{ display: "grid", gap: 16 }}>
        {PANELS.map((p) => (
          <Sparkline
            key={p.metric as string}
            panel={p}
            data={data}
            trend={trends.data?.metrics[p.metric as string]}
          />
        ))}
      </div>
    </SectionShell>
  );
}

function Sparkline({
  panel,
  data,
  trend,
}: {
  panel: Panel;
  data: SeasonalRow[];
  trend?: TrendMetric;
}) {
  const width = 1080;
  const height = 110;
  const margin = { top: 18, right: 16, bottom: 22, left: 16 };
  const iw = width - margin.left - margin.right;
  const ih = height - margin.top - margin.bottom;

  const pts = data
    .map((d) => ({ year: d.year, val: d[panel.metric] as number | null }))
    .filter((d) => d.val != null) as { year: number; val: number }[];

  if (pts.length === 0) {
    return (
      <div
        style={{
          padding: 16,
          background: "hsl(220 30% 6% / 0.5)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid hsl(200 80% 50% / 0.12)",
          color: "var(--color-text-mid)",
          fontFamily: "var(--font-data)",
          fontSize: 12,
        }}
      >
        {panel.label}: no data
      </div>
    );
  }

  const xs = pts.map((p) => p.year);
  const ys = pts.map((p) => p.val);
  const xScale = scaleLinear({ domain: [Math.min(...xs), Math.max(...xs)], range: [0, iw] });
  const yScale = scaleLinear({
    domain: [Math.min(...ys) - 0.05 * Math.abs(Math.min(...ys)), Math.max(...ys) * 1.05],
    range: [ih, 0],
  });

  const trendLine =
    trend &&
    Number.isFinite(trend.slope_per_year) &&
    Number.isFinite(trend.intercept) && {
      x1: xs[0],
      y1: trend.slope_per_year * xs[0] + trend.intercept,
      x2: xs[xs.length - 1],
      y2: trend.slope_per_year * xs[xs.length - 1] + trend.intercept,
    };

  const deltaLabel =
    trend && Number.isFinite(trend.delta_over_span)
      ? `${trend.delta_over_span >= 0 ? "+" : ""}${trend.delta_over_span.toFixed(2)} ${panel.unit} since ${xs[0]}`
      : "";
  const ciLabel =
    trend && Number.isFinite(trend.slope_ci_lo)
      ? `CI ${trend.slope_ci_lo.toFixed(3)} → ${trend.slope_ci_hi.toFixed(3)} ${panel.unit}/yr`
      : "";

  return (
    <div
      style={{
        background: "hsl(220 30% 6% / 0.5)",
        borderRadius: "var(--radius-lg)",
        border: "1px solid hsl(200 80% 50% / 0.12)",
        padding: 16,
        display: "grid",
        gap: 4,
        overflowX: "auto",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div style={{ fontFamily: "var(--font-body)", fontSize: 13, color: "var(--color-text-hi)" }}>
          {panel.label}
        </div>
        <div style={{ fontFamily: "var(--font-data)", fontSize: 12, color: panel.colour }}>
          {deltaLabel}
          <span style={{ color: "var(--color-text-mid)", marginLeft: 10 }}>{ciLabel}</span>
        </div>
      </div>
      <svg width={width} height={height} style={{ minWidth: width, display: "block" }}>
        <Group left={margin.left} top={margin.top}>
          <LinePath
            data={pts}
            x={(d) => xScale(d.year)}
            y={(d) => yScale(d.val)}
            stroke={panel.colour}
            strokeWidth={1.5}
            strokeOpacity={0.85}
          />
          {pts.map((d) => (
            <circle
              key={d.year}
              cx={xScale(d.year)}
              cy={yScale(d.val)}
              r={2}
              fill={panel.colour}
            />
          ))}
          {trendLine && (
            <Line
              from={{ x: xScale(trendLine.x1), y: yScale(trendLine.y1) }}
              to={{ x: xScale(trendLine.x2), y: yScale(trendLine.y2) }}
              stroke="hsl(40 30% 96% / 0.5)"
              strokeWidth={1.5}
              strokeDasharray="3 4"
            />
          )}
          {/* x-axis labels at year endpoints */}
          <text
            x={0}
            y={ih + 14}
            fontFamily="var(--font-data)"
            fontSize={10}
            fill="hsl(40 12% 72%)"
          >
            {xs[0]}
          </text>
          <text
            x={iw}
            y={ih + 14}
            fontFamily="var(--font-data)"
            fontSize={10}
            fill="hsl(40 12% 72%)"
            textAnchor="end"
          >
            {xs[xs.length - 1]}
          </text>
        </Group>
      </svg>
    </div>
  );
}
