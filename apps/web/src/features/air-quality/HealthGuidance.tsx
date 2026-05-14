import { useState } from "react";

import type { HealthGuidance as HG } from "@/lib/api/hooks";
import { aqhiColor } from "./aqColors";

type Audience = "general" | "at_risk" | "outdoor_workers";

const AUDIENCE_LABELS: Record<Audience, string> = {
  general: "General",
  at_risk: "At-risk groups",
  outdoor_workers: "Outdoor workers",
};

export function HealthGuidance({
  guidance,
  currentAqhi,
}: {
  guidance: HG;
  currentAqhi: number | null;
}) {
  const [audience, setAudience] = useState<Audience>("general");

  const activeBand = guidance.bands.find(
    (b) =>
      currentAqhi != null && currentAqhi >= b.aqhi_min && currentAqhi <= b.aqhi_max,
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div
        style={{
          display: "flex",
          gap: 8,
          flexWrap: "wrap",
        }}
      >
        {(["general", "at_risk", "outdoor_workers"] as Audience[]).map((a) => (
          <button
            key={a}
            type="button"
            onClick={() => setAudience(a)}
            style={{
              padding: "5px 12px",
              fontSize: 10,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              fontFamily: "var(--font-data)",
              borderRadius: "var(--radius-pill)",
              cursor: "pointer",
              background: audience === a ? "var(--color-bg-3)" : "transparent",
              color:
                audience === a ? "var(--color-text-hi)" : "var(--color-text-mid)",
              border: `1px solid ${
                audience === a ? "var(--color-ember-500)" : "var(--color-stroke)"
              }`,
            }}
          >
            {AUDIENCE_LABELS[a]}
          </button>
        ))}
      </div>

      {guidance.bands.map((band) => {
        const isActive = band === activeBand;
        const color = aqhiColor((band.aqhi_min + band.aqhi_max) / 2);
        return (
          <div
            key={band.label}
            style={{
              display: "flex",
              gap: 16,
              padding: "12px 16px",
              borderRadius: "var(--radius-md)",
              background: isActive ? "var(--color-bg-3)" : "var(--color-bg-1)",
              border: `1px solid ${isActive ? color : "var(--color-stroke)"}`,
              boxShadow: isActive ? `0 0 16px ${color}33` : "none",
              transition: "background var(--dur-base), border-color var(--dur-base)",
            }}
          >
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: "50%",
                background: color,
                color: "var(--color-bg-0)",
                fontFamily: "var(--font-data)",
                fontWeight: 700,
                fontSize: 14,
                display: "grid",
                placeItems: "center",
                flexShrink: 0,
                boxShadow: isActive ? `0 0 16px ${color}` : "none",
              }}
            >
              {band.aqhi_min}–{band.aqhi_max === 999 ? "11+" : band.aqhi_max}
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 15,
                  fontWeight: 600,
                  color: isActive ? "var(--color-text-hi)" : "var(--color-text-mid)",
                }}
              >
                {band.label}
              </div>
              <p
                style={{
                  margin: "6px 0 0 0",
                  fontFamily: "var(--font-body)",
                  fontSize: 13,
                  lineHeight: 1.5,
                  color: isActive
                    ? "var(--color-text-hi)"
                    : "var(--color-text-mid)",
                }}
              >
                {band[audience]}
              </p>
            </div>
          </div>
        );
      })}

      <div
        style={{
          marginTop: 8,
          paddingTop: 14,
          borderTop: "1px solid var(--color-stroke)",
          fontFamily: "var(--font-data)",
          fontSize: 10,
          letterSpacing: "0.16em",
          color: "var(--color-text-low)",
        }}
      >
        <div style={{ marginBottom: 6, textTransform: "uppercase" }}>References</div>
        {guidance.links.map((l) => (
          <a
            key={l.url}
            href={l.url}
            target="_blank"
            rel="noreferrer"
            style={{
              display: "block",
              color: "var(--color-text-mid)",
              textDecoration: "none",
              padding: "3px 0",
            }}
          >
            → {l.title}
          </a>
        ))}
      </div>
    </div>
  );
}
