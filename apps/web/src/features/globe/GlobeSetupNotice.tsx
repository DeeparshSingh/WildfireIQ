/**
 * Shown in place of the globe when no Cesium Ion token has been entered.
 *
 * The other routes work without the token; this one cannot draw. So the
 * notice says exactly that, and its one button opens the Settings panel
 * where the token goes. The page reloads after a save so Cesium starts with
 * the new token, which the panel says before the reader clicks.
 */
import { useKeysStore } from "@/stores/keys";

const code: React.CSSProperties = {
  fontFamily: "var(--font-data)",
  fontSize: 13,
  color: "var(--color-text-hi)",
  background: "var(--color-bg-2)",
  padding: "2px 6px",
  borderRadius: 4,
};

export function GlobeSetupNotice() {
  const openSettings = useKeysStore((s) => s.openPanel);

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        placeItems: "center",
        background: "radial-gradient(ellipse at center, hsl(220 25% 6%) 0%, hsl(220 30% 2%) 70%)",
        padding: 24,
        pointerEvents: "auto",
      }}
    >
      <div
        className="glass"
        style={{
          maxWidth: 560,
          padding: 32,
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-elevated)",
        }}
      >
        <div
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 11,
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--color-ember-400)",
            marginBottom: 12,
          }}
        >
          One key to add
        </div>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 32,
            fontWeight: 700,
            letterSpacing: "-0.03em",
            margin: 0,
            color: "var(--color-text-hi)",
          }}
        >
          The globe needs a Cesium Ion token
        </h1>
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 15,
            lineHeight: 1.55,
            color: "var(--color-text-mid)",
            marginTop: 16,
          }}
        >
          World terrain and aerial imagery stream from Cesium Ion, and that needs an access token of
          your own. Sign in at Cesium Ion, copy the default token from{" "}
          <span style={code}>Access Tokens</span>, and paste it into Settings. Every other page
          works without it.
        </p>
        <div style={{ display: "flex", gap: 12, marginTop: 24, flexWrap: "wrap" }}>
          <button
            type="button"
            onClick={openSettings}
            style={{
              padding: "10px 18px",
              background: "var(--color-ember-500)",
              color: "#0b0e14",
              border: "none",
              fontFamily: "var(--font-data)",
              fontSize: 12,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              fontWeight: 700,
              borderRadius: "var(--radius-md)",
              boxShadow: "var(--glow-ember-soft)",
              cursor: "pointer",
            }}
          >
            Open settings
          </button>
          <a
            href="https://ion.cesium.com/tokens"
            target="_blank"
            rel="noreferrer"
            style={{
              display: "inline-block",
              padding: "10px 18px",
              border: "1px solid var(--color-stroke-strong)",
              color: "var(--color-text-mid)",
              fontFamily: "var(--font-data)",
              fontSize: 12,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              textDecoration: "none",
              borderRadius: "var(--radius-md)",
            }}
          >
            Get a token ↗
          </a>
        </div>
      </div>
    </div>
  );
}
