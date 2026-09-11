import { useEffect, useState } from "react";

import { AssistantTrigger } from "@/features/assistant/AssistantTrigger";
import { useKeysStore } from "@/stores/keys";

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
  const openSettings = useKeysStore((s) => s.openPanel);
  // Flags a missing server key; a visitor's own OpenRouter key covers that one.
  const anyMissing = useKeysStore((s) => {
    if (s.status === null) return false;
    const k = s.status.keys;
    return (
      !k.firms_map_key || !k.waqi_token || (!k.openrouter_api_key && !s.keys.openrouter_api_key)
    );
  });
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
      <AssistantTrigger />
      <button
        type="button"
        onClick={openSettings}
        aria-label={anyMissing ? "Settings: some API keys are not set" : "Settings"}
        title="API keys"
        style={{
          position: "relative",
          display: "grid",
          placeItems: "center",
          width: 28,
          height: 26,
          borderRadius: "var(--radius-pill)",
          border: "1px solid var(--color-stroke)",
          background: "transparent",
          color: "var(--color-text-mid)",
          cursor: "pointer",
        }}
      >
        <svg
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <circle cx="7.5" cy="15.5" r="4.5" />
          <path d="m21 2-9.6 9.6M15.5 7.5l3 3L22 7l-3-3" />
        </svg>
        {anyMissing && (
          <span
            aria-hidden="true"
            style={{
              position: "absolute",
              top: -2,
              right: -2,
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "var(--color-ember-500)",
              boxShadow: "var(--glow-ember)",
            }}
          />
        )}
      </button>
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
