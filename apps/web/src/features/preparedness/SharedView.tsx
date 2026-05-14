/**
 * /preparedness/shared#<base64> — read-only view of someone else's
 * encoded progress. The data is in the URL hash, not on a server. No
 * mutations, no photos (those never leave the source device).
 */
import { useLocation } from "react-router-dom";

import { useFireSmartAchievements } from "@/lib/api/hooks";

import { decodeShare } from "./state";

export function SharedView() {
  const location = useLocation();
  const hash = location.hash.startsWith("#") ? location.hash.slice(1) : location.hash;
  const payload = hash ? decodeShare(hash) : null;
  const achievements = useFireSmartAchievements();

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        pointerEvents: "auto",
        padding: "48px 24px 80px",
        background:
          "radial-gradient(ellipse at top, hsl(220 25% 6% / 0.92), hsl(220 30% 2% / 0.96) 80%)",
      }}
    >
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <header style={{ marginBottom: 24 }}>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--color-cyan-glow)",
            }}
          >
            Shared FireSmart progress
          </div>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(1.6rem, 3vw, 2.4rem)",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              margin: "8px 0 0",
              color: "var(--color-text-hi)",
              lineHeight: 1.1,
            }}
          >
            {payload?.p.neighbourhood
              ? `A ${payload.p.dwelling} in ${payload.p.neighbourhood}`
              : "Someone shared their progress with you"}
          </h1>
          <p
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 13,
              lineHeight: 1.55,
              color: "var(--color-text-mid)",
              marginTop: 10,
              maxWidth: 560,
            }}
          >
            All data on this page was decoded from the URL hash. Nothing
            was fetched from a server. This is a read-only view.
          </p>
        </header>

        {!payload ? (
          <section
            className="glass-strong"
            style={{ padding: 28, borderRadius: "var(--radius-lg)", color: "var(--color-text-mid)" }}
          >
            No valid shared payload in the URL. Ask the sharer for the link again.
          </section>
        ) : (
          <>
            <section
              className="glass-strong"
              style={{
                padding: 24,
                borderRadius: "var(--radius-lg)",
                display: "grid",
                gap: 12,
                marginBottom: 16,
              }}
            >
              <div style={{ fontFamily: "var(--font-data)", fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--color-text-mid)" }}>
                Completed actions
              </div>
              <div style={{ fontFamily: "var(--font-display)", fontSize: 36, fontWeight: 700, color: "var(--color-text-hi)", lineHeight: 1 }}>
                {payload.g.completedActions.length}
              </div>
              <div style={{ fontFamily: "var(--font-body)", fontSize: 12, color: "var(--color-text-mid)" }}>
                🔥 {payload.g.streakDays} day streak · {payload.g.earnedAchievements.length} badges earned
              </div>
            </section>

            <section style={{ display: "grid", gap: 8 }}>
              <div style={{ fontFamily: "var(--font-data)", fontSize: 11, letterSpacing: "0.28em", textTransform: "uppercase", color: "var(--color-text-mid)" }}>
                Badges earned
              </div>
              {(achievements.data ?? []).map((a) => {
                const got = payload.g.earnedAchievements.includes(a.id);
                return (
                  <div
                    key={a.id}
                    style={{
                      padding: "10px 12px",
                      borderRadius: 10,
                      background: got ? "hsl(45 95% 58% / 0.10)" : "hsl(220 30% 10% / 0.5)",
                      border: `1px solid ${got ? "hsl(45 95% 58% / 0.45)" : "hsl(200 80% 50% / 0.10)"}`,
                      opacity: got ? 1 : 0.4,
                      display: "grid",
                      gridTemplateColumns: "auto 1fr",
                      gap: 10,
                      alignItems: "center",
                    }}
                  >
                    <span style={{ fontSize: 22 }}>{a.emoji}</span>
                    <div>
                      <div style={{ fontFamily: "var(--font-body)", fontSize: 13, fontWeight: 600, color: "var(--color-text-hi)" }}>
                        {a.label}
                      </div>
                      <div style={{ fontFamily: "var(--font-body)", fontSize: 11, color: "var(--color-text-mid)", lineHeight: 1.4, marginTop: 2 }}>
                        {a.blurb}
                      </div>
                    </div>
                  </div>
                );
              })}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
