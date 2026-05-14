/**
 * Left column — live situational readouts for the user's neighbourhood.
 *
 *   • Evacuation status (point-in-polygon)  — `/api/evac/check`
 *   • Current AQHI                          — `/api/aq/current` (Kamloops station)
 *   • Highest local FWI                     — `/api/fwi/today`
 *   • Days since 5 mm+ rain                 — `/api/firesmart/season-context`
 *   • Days to historical fire-season peak   — derived from same endpoint
 */
import {
  useAqCurrent,
  useEvacCheck,
  useFwiToday,
  useSeasonContext,
} from "@/lib/api/hooks";

function evacTone(status: "clear" | "alert" | "order" | null | undefined) {
  if (status === "order")
    return { bg: "hsl(0 70% 45% / 0.18)", border: "hsl(0 80% 55%)", label: "ORDER", text: "Evacuation Order active", emoji: "🚨" };
  if (status === "alert")
    return { bg: "hsl(35 90% 50% / 0.18)", border: "hsl(35 90% 55%)", label: "ALERT", text: "Evacuation Alert", emoji: "⚠️" };
  return { bg: "hsl(150 60% 40% / 0.15)", border: "hsl(150 70% 50%)", label: "CLEAR", text: "No active orders or alerts", emoji: "✅" };
}

function aqhiBand(aqhi: number | null) {
  if (aqhi === null) return { label: "—", color: "hsl(220 10% 50%)" };
  if (aqhi <= 3) return { label: "Low", color: "hsl(140 55% 50%)" };
  if (aqhi <= 6) return { label: "Moderate", color: "hsl(45 95% 58%)" };
  if (aqhi <= 10) return { label: "High", color: "hsl(22 100% 56%)" };
  return { label: "Very High", color: "hsl(0 80% 55%)" };
}

function fwiClass(fwi: number | null) {
  if (fwi === null) return { label: "—", color: "hsl(220 10% 50%)" };
  if (fwi <= 1) return { label: "Low", color: "hsl(140 55% 50%)" };
  if (fwi <= 4) return { label: "Moderate", color: "hsl(45 95% 58%)" };
  if (fwi <= 12) return { label: "High", color: "hsl(22 100% 56%)" };
  if (fwi <= 20) return { label: "Very High", color: "hsl(14 92% 50%)" };
  return { label: "Extreme", color: "hsl(0 80% 55%)" };
}

function daysToPeak(month: number, day: number): number {
  const now = new Date();
  let peak = new Date(now.getFullYear(), month - 1, day);
  if (peak.getTime() < now.getTime()) peak = new Date(now.getFullYear() + 1, month - 1, day);
  return Math.round((peak.getTime() - now.getTime()) / 86_400_000);
}

export function LiveStatusPanel({
  lat,
  lon,
  neighbourhood,
}: {
  lat: number;
  lon: number;
  neighbourhood: string | null;
}) {
  const evac = useEvacCheck(lat, lon);
  const aq = useAqCurrent();
  const fwi = useFwiToday();
  const ctx = useSeasonContext();

  const aqhi =
    aq.data?.stations.find((s) => s.station_name?.toLowerCase().includes("kamloops"))?.aqhi ??
    aq.data?.stations[0]?.aqhi ??
    null;
  const aqBand = aqhiBand(typeof aqhi === "number" ? aqhi : null);

  // Highest FWI from the nearest few stations to user
  const nearestFwi =
    fwi.data
      ?.map((s) => ({
        ...s,
        dist:
          Math.hypot(
            (s.latitude ?? 0) - lat,
            (s.longitude ?? 0) - lon,
          ),
      }))
      .sort((a, b) => a.dist - b.dist)
      .slice(0, 3) ?? [];
  const maxFwi =
    nearestFwi.length > 0
      ? Math.max(...nearestFwi.map((s) => s.fwi ?? -1).filter((x) => x >= 0), -1)
      : -1;
  const fwiBand = fwiClass(maxFwi >= 0 ? maxFwi : null);

  const tone = evacTone(evac.data?.status);
  const dtp = ctx.data ? daysToPeak(ctx.data.peak_month, ctx.data.peak_day) : null;

  return (
    <section style={{ display: "grid", gap: 12 }}>
      <SectionHeader>Live situation</SectionHeader>

      {/* Evac status — top, prominent */}
      <div
        style={{
          padding: 16,
          borderRadius: "var(--radius-lg)",
          background: tone.bg,
          border: `1px solid ${tone.border}`,
          display: "grid",
          gap: 6,
        }}
      >
        <div style={labelStyle}>Evacuation · {neighbourhood ?? "your area"}</div>
        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 18,
            fontWeight: 600,
            color: "var(--color-text-hi)",
            display: "flex",
            gap: 8,
            alignItems: "center",
          }}
        >
          <span>{tone.emoji}</span>
          <span>{evac.isLoading ? "Checking…" : tone.text}</span>
        </div>
        {(evac.data?.matches ?? []).slice(0, 2).map((m, i) => (
          <div key={i} style={{ fontSize: 11, color: "var(--color-text-mid)" }}>
            · {m.event_name ?? "Unnamed event"}
          </div>
        ))}
      </div>

      <Stat label="AQHI · Kamloops" value={aqhi !== null ? String(aqhi) : "—"} sub={aqBand.label} color={aqBand.color} />
      <Stat
        label="Max FWI nearby"
        value={maxFwi >= 0 ? maxFwi.toFixed(1) : "—"}
        sub={fwiBand.label}
        color={fwiBand.color}
      />
      <Stat
        label="Days since 5 mm+ rain"
        value={ctx.data?.days_since_5mm_rain != null ? String(ctx.data.days_since_5mm_rain) : "—"}
        sub="Open-Meteo daily"
        color="hsl(185 90% 55%)"
      />
      <Stat
        label="Days to fire-season peak"
        value={dtp != null ? String(dtp) : "—"}
        sub={
          ctx.data
            ? `${["", "Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][ctx.data.peak_month]} ${ctx.data.peak_day}`
            : "—"
        }
        color="hsl(22 100% 56%)"
      />
    </section>
  );
}

function Stat({
  label,
  value,
  sub,
  color,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
}) {
  return (
    <div
      className="glass"
      style={{
        padding: 14,
        borderRadius: "var(--radius-lg)",
        display: "grid",
        gap: 2,
      }}
    >
      <div style={labelStyle}>{label}</div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 28,
          fontWeight: 700,
          color: "var(--color-text-hi)",
          lineHeight: 1,
          marginTop: 4,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 11,
          color,
          textTransform: "uppercase",
          letterSpacing: "0.16em",
          marginTop: 2,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "var(--font-data)",
        fontSize: 11,
        letterSpacing: "0.28em",
        textTransform: "uppercase",
        color: "var(--color-text-mid)",
      }}
    >
      {children}
    </div>
  );
}

const labelStyle: React.CSSProperties = {
  fontFamily: "var(--font-data)",
  fontSize: 10,
  letterSpacing: "0.2em",
  textTransform: "uppercase",
  color: "var(--color-text-mid)",
};
