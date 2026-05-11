/**
 * Shown when no Cesium Ion token is configured. Phase 0 graceful fallback.
 */
export function GlobeSetupNotice() {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        placeItems: "center",
        background:
          "radial-gradient(ellipse at center, hsl(220 25% 6%) 0%, hsl(220 30% 2%) 70%)",
        padding: 24,
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
          Setup required · Phase 0
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
          Add your Cesium Ion token
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
          The 3D globe needs a free Cesium Ion access token to stream world terrain and 3D
          buildings. Sign up, copy your default token, and drop it into{" "}
          <code
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 13,
              color: "var(--color-text-hi)",
              background: "var(--color-bg-2)",
              padding: "2px 6px",
              borderRadius: 4,
            }}
          >
            .env
          </code>{" "}
          as{" "}
          <code
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 13,
              color: "var(--color-text-hi)",
              background: "var(--color-bg-2)",
              padding: "2px 6px",
              borderRadius: 4,
            }}
          >
            VITE_CESIUM_ION_TOKEN
          </code>
          , then restart{" "}
          <code
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 13,
              color: "var(--color-text-hi)",
              background: "var(--color-bg-2)",
              padding: "2px 6px",
              borderRadius: 4,
            }}
          >
            pnpm dev
          </code>
          .
        </p>
        <a
          href="https://ion.cesium.com/signin/"
          target="_blank"
          rel="noreferrer"
          style={{
            display: "inline-block",
            marginTop: 24,
            padding: "10px 18px",
            background: "var(--color-ember-500)",
            color: "white",
            fontFamily: "var(--font-data)",
            fontSize: 12,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            textDecoration: "none",
            borderRadius: "var(--radius-md)",
            boxShadow: "var(--glow-ember-soft)",
          }}
        >
          Get a free Ion token →
        </a>
      </div>
    </div>
  );
}
