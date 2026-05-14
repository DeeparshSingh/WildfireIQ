import { motion } from "motion/react";

import { aqhiBand, aqhiColor } from "./aqColors";

/**
 * Bespoke AQHI dial — 320px desktop, scales fluidly. Filled arc animates
 * from 0 to the current value, colour-mapped to the AQHI band. Pulses
 * subtly when fresh data lands.
 */
export function AqhiDial({
  aqhi,
  lastUpdated,
}: {
  aqhi: number | null;
  lastUpdated?: string;
}) {
  const value = aqhi ?? 0;
  const clamped = Math.max(0, Math.min(11, value));
  const color = aqhi == null ? "var(--color-text-low)" : aqhiColor(clamped);
  const band = aqhi == null ? "—" : aqhiBand(clamped);

  // 270° arc spanning bottom-left → top → bottom-right.
  const R = 130;
  const startAngle = 135; // degrees, measured from 3 o'clock
  const sweep = 270;
  const cx = 160;
  const cy = 160;

  // Convert a value v∈[0,11] to an arc end-angle.
  const angleFor = (v: number) => startAngle + (Math.min(v, 11) / 11) * sweep;

  const polar = (angle: number, r: number = R) => {
    const rad = ((angle - 90) * Math.PI) / 180; // SVG 0° points right
    return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
  };

  const arcPath = (fromDeg: number, toDeg: number) => {
    const start = polar(fromDeg);
    const end = polar(toDeg);
    const large = toDeg - fromDeg > 180 ? 1 : 0;
    return `M ${start.x} ${start.y} A ${R} ${R} 0 ${large} 1 ${end.x} ${end.y}`;
  };

  const backgroundPath = arcPath(startAngle, startAngle + sweep);
  const filledPath = arcPath(startAngle, angleFor(clamped));

  // Tick marks at integer AQHI values.
  const ticks = Array.from({ length: 11 }, (_, i) => i + 1);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: "8px 0",
      }}
    >
      <svg width={320} height={320} viewBox="0 0 320 320" aria-hidden>
        <title>{`Current AQHI ${aqhi ?? "unknown"}`}</title>
        {/* Background arc */}
        <path
          d={backgroundPath}
          fill="none"
          stroke="var(--color-stroke)"
          strokeWidth={10}
          strokeLinecap="round"
        />

        {/* Tick marks at each AQHI integer */}
        {ticks.map((t) => {
          const angle = angleFor(t);
          const outer = polar(angle, R + 12);
          const inner = polar(angle, R + 4);
          return (
            <line
              key={t}
              x1={inner.x}
              y1={inner.y}
              x2={outer.x}
              y2={outer.y}
              stroke="var(--color-stroke-strong)"
              strokeWidth={1}
            />
          );
        })}

        {/* Tick labels at 1, 4, 7, 11 */}
        {[1, 4, 7, 11].map((t) => {
          const angle = angleFor(t);
          const lbl = polar(angle, R + 26);
          return (
            <text
              key={t}
              x={lbl.x}
              y={lbl.y}
              textAnchor="middle"
              dominantBaseline="central"
              fontSize={10}
              fontFamily="var(--font-data)"
              letterSpacing="0.18em"
              fill="var(--color-text-low)"
            >
              {t === 11 ? "11+" : t}
            </text>
          );
        })}

        {/* Filled arc (animated) */}
        <motion.path
          key={clamped}
          d={filledPath}
          fill="none"
          stroke={color}
          strokeWidth={12}
          strokeLinecap="round"
          initial={{ pathLength: 0, opacity: 0.4 }}
          animate={{ pathLength: 1, opacity: 1 }}
          transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
          style={{
            filter:
              aqhi != null && aqhi >= 7
                ? "drop-shadow(0 0 12px " + color + ")"
                : undefined,
          }}
        />
      </svg>

      {/* Centre overlay (above the SVG via negative margin trick) */}
      <div
        style={{
          marginTop: -200,
          marginBottom: 60,
          textAlign: "center",
          fontFamily: "var(--font-data)",
          color: "var(--color-text-hi)",
        }}
      >
        <div
          className="tabular"
          style={{
            fontSize: 84,
            fontWeight: 600,
            lineHeight: 1,
            color: color,
            textShadow:
              aqhi != null && aqhi >= 7 ? `0 0 24px ${color}` : "none",
          }}
        >
          {aqhi == null ? "—" : Math.round(aqhi)}
        </div>
        <div
          style={{
            marginTop: 6,
            fontFamily: "var(--font-display)",
            fontSize: 14,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--color-text-mid)",
          }}
        >
          {band}
        </div>
        {lastUpdated && (
          <div
            style={{
              marginTop: 8,
              fontFamily: "var(--font-data)",
              fontSize: 10,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--color-text-low)",
            }}
          >
            updated {lastUpdated}
          </div>
        )}
      </div>
    </div>
  );
}
