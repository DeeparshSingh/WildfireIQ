import { useMemo } from "react";
import { Group } from "@visx/group";
import { AreaClosed, LinePath, Line, Circle } from "@visx/shape";
import { scaleLinear, scaleTime } from "@visx/scale";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridRows, GridColumns } from "@visx/grid";
import { curveMonotoneX } from "@visx/curve";

import type { AqForecast, AqObservation, AqForecastPoint } from "@/lib/api/hooks";
import { pm25ToAqhi, aqhiColor } from "./aqColors";

const W = 760;
const H = 280;
const M = { top: 12, right: 24, bottom: 32, left: 40 };
const innerW = W - M.left - M.right;
const innerH = H - M.top - M.bottom;

type Point = { time: Date; q10?: number; q50: number; q90?: number; observed?: boolean };

export function ForecastChart({ data }: { data: AqForecast }) {
  const points: Point[] = useMemo(() => {
    const obs: Point[] = data.observations.map((o: AqObservation) => ({
      time: new Date(o.time_utc),
      q50: o.pm2_5,
      observed: true,
    }));
    const fc: Point[] = data.forecasts.map((f: AqForecastPoint) => ({
      time: new Date(f.time_utc),
      q10: f.q10,
      q50: f.q50,
      q90: f.q90,
    }));
    return [...obs, ...fc];
  }, [data]);

  const issued = useMemo(() => new Date(data.issued_at_utc), [data]);

  const xScale = useMemo(
    () =>
      scaleTime<number>({
        domain: [points[0]?.time ?? new Date(), points[points.length - 1]?.time ?? new Date()],
        range: [0, innerW],
      }),
    [points],
  );

  const yMaxFromData = Math.max(
    20,
    ...points.map((p) => p.q90 ?? p.q50 ?? 0),
  );
  const yScale = useMemo(
    () => scaleLinear<number>({ domain: [0, yMaxFromData], range: [innerH, 0], nice: true }),
    [yMaxFromData],
  );

  const forecastOnly = points.filter((p) => !p.observed);
  const allPoints = points;

  return (
    <div style={{ width: "100%", overflowX: "auto" }}>
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="48-hour PM2.5 forecast">
        <Group left={M.left} top={M.top}>
          <GridRows
            scale={yScale}
            width={innerW}
            stroke="var(--color-stroke)"
            strokeOpacity={0.5}
            pointerEvents="none"
            numTicks={4}
          />
          <GridColumns
            scale={xScale}
            height={innerH}
            stroke="var(--color-stroke)"
            strokeOpacity={0.3}
            pointerEvents="none"
            numTicks={6}
          />

          {/* Quantile band (q10 → q90) for forecast points */}
          <AreaClosed<Point>
            data={forecastOnly}
            x={(p) => xScale(p.time)}
            y0={(p) => yScale(p.q10 ?? p.q50)}
            y1={(p) => yScale(p.q90 ?? p.q50)}
            yScale={yScale}
            fill="var(--color-cyan-glow)"
            fillOpacity={0.22}
            stroke="var(--color-cyan-glow)"
            strokeOpacity={0.4}
            strokeWidth={1}
            curve={curveMonotoneX}
          />

          {/* Median (q50) forecast line */}
          <LinePath<Point>
            data={forecastOnly}
            x={(p) => xScale(p.time)}
            y={(p) => yScale(p.q50)}
            stroke="var(--color-cyan-glow)"
            strokeWidth={2.5}
            curve={curveMonotoneX}
          />

          {/* Observed history line + dots */}
          <LinePath<Point>
            data={allPoints.filter((p) => p.observed)}
            x={(p) => xScale(p.time)}
            y={(p) => yScale(p.q50)}
            stroke="var(--color-text-hi)"
            strokeWidth={2}
            curve={curveMonotoneX}
          />
          {allPoints
            .filter((p) => p.observed)
            .map((p, i) => (
              <Circle
                key={`obs-${i}`}
                cx={xScale(p.time)}
                cy={yScale(p.q50)}
                r={3}
                fill={aqhiColor(pm25ToAqhi(p.q50))}
                stroke="var(--color-bg-0)"
                strokeWidth={1.2}
              />
            ))}

          {/* "Now" line at issued_at */}
          <Line
            from={{ x: xScale(issued), y: 0 }}
            to={{ x: xScale(issued), y: innerH }}
            stroke="var(--color-ember-500)"
            strokeWidth={1.5}
            strokeDasharray="6 4"
          />

          <AxisLeft
            scale={yScale}
            stroke="var(--color-stroke-strong)"
            tickStroke="var(--color-stroke)"
            numTicks={5}
            tickLabelProps={() => ({
              fill: "var(--color-text-mid)",
              fontSize: 10,
              fontFamily: "var(--font-data)",
              textAnchor: "end",
              dx: -4,
              dy: 3,
            })}
            label="PM2.5 µg/m³"
            labelProps={{
              fill: "var(--color-text-low)",
              fontSize: 10,
              fontFamily: "var(--font-data)",
              letterSpacing: "0.18em",
              textAnchor: "middle",
            }}
          />
          <AxisBottom
            top={innerH}
            scale={xScale}
            stroke="var(--color-stroke-strong)"
            tickStroke="var(--color-stroke)"
            numTicks={6}
            tickLabelProps={() => ({
              fill: "var(--color-text-mid)",
              fontSize: 10,
              fontFamily: "var(--font-data)",
              textAnchor: "middle",
            })}
            tickFormat={(d) => {
              const dt = d instanceof Date ? d : new Date(d.valueOf());
              return new Intl.DateTimeFormat("en-CA", {
                hour: "2-digit",
                hour12: false,
                month: "short",
                day: "numeric",
                timeZone: "America/Vancouver",
              }).format(dt);
            }}
          />
        </Group>
      </svg>
      <div
        style={{
          marginTop: 6,
          display: "flex",
          gap: 22,
          fontFamily: "var(--font-data)",
          fontSize: 10,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--color-text-low)",
        }}
      >
        <span><span style={{ color: "var(--color-text-hi)" }}>━</span> Observed (last 12h)</span>
        <span><span style={{ color: "var(--color-cyan-glow)" }}>━</span> Median forecast</span>
        <span><span style={{ color: "var(--color-cyan-glow)", opacity: 0.5 }}>▭</span> q10–q90 band</span>
        <span><span style={{ color: "var(--color-ember-500)" }}>┊</span> Now</span>
      </div>
    </div>
  );
}
