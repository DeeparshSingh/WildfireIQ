import { useEffect, useState } from "react";

function useClock() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return now;
}

function fmt(d: Date, tz: string) {
  return new Intl.DateTimeFormat("en-CA", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: tz,
  }).format(d);
}

export function TopBar() {
  const now = useClock();
  return (
    <header
      style={{
        height: "100%",
        background: "var(--color-bg-1)",
        borderBottom: "1px solid var(--color-stroke)",
        display: "flex",
        alignItems: "center",
        padding: "0 24px",
        gap: 24,
        fontFamily: "var(--font-data)",
        fontSize: 12,
        color: "var(--color-text-mid)",
        letterSpacing: "0.04em",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 14,
          letterSpacing: "-0.02em",
          color: "var(--color-text-hi)",
          fontWeight: 600,
        }}
      >
        WildfireIQ <span style={{ color: "var(--color-text-low)" }}>Kamloops</span>
      </div>
      <div style={{ flex: 1 }} />
      <div className="tabular" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span className="live-dot" aria-hidden />
        <span style={{ color: "var(--color-text-low)" }}>UTC</span>
        <span style={{ color: "var(--color-text-hi)" }}>{fmt(now, "UTC")}</span>
        <span style={{ color: "var(--color-stroke-strong)" }}>·</span>
        <span style={{ color: "var(--color-text-low)" }}>YKA</span>
        <span style={{ color: "var(--color-text-hi)" }}>{fmt(now, "America/Vancouver")}</span>
      </div>
      <div
        className="tabular"
        style={{
          color: "var(--color-text-low)",
          padding: "4px 10px",
          border: "1px solid var(--color-stroke)",
          borderRadius: "var(--radius-pill)",
        }}
      >
        v1.0.0
      </div>
    </header>
  );
}
