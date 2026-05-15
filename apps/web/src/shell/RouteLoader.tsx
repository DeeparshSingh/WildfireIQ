/**
 * Suspense fallback for code-split routes. Tactical-dark, no spinner —
 * a slow ember-coloured progress sweep and a single status line. Reduced
 * motion users get a static label.
 */
export function RouteLoader({ label = "Loading…" }: { label?: string }) {
  return (
    <div
      role="status"
      aria-busy
      aria-label={label}
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        placeItems: "center",
        pointerEvents: "none",
        background: "hsl(220 30% 4% / 0.4)",
      }}
    >
      <div style={{ display: "grid", gap: 14, placeItems: "center" }}>
        <svg
          width="44"
          height="44"
          viewBox="0 0 44 44"
          aria-hidden
          style={{ overflow: "visible" }}
        >
          <circle
            cx="22"
            cy="22"
            r="18"
            stroke="hsl(220 15% 22%)"
            strokeWidth="2"
            fill="none"
          />
          <circle
            cx="22"
            cy="22"
            r="18"
            stroke="hsl(18 95% 54%)"
            strokeWidth="2"
            fill="none"
            strokeDasharray="28 92"
            strokeLinecap="round"
            transform="rotate(-90 22 22)"
            style={{
              animation: "wfiq-route-spin 1.2s var(--ease-out-expo, ease-in-out) infinite",
              filter: "drop-shadow(0 0 6px hsl(18 95% 54% / 0.6))",
            }}
          />
        </svg>
        <span
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 11,
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--color-text-mid)",
          }}
        >
          {label}
        </span>
      </div>
      <style>{`
        @keyframes wfiq-route-spin {
          to { transform: rotate(360deg); transform-origin: 22px 22px; }
        }
        @media (prefers-reduced-motion: reduce) {
          [aria-busy] circle:last-child { animation: none !important; }
        }
      `}</style>
    </div>
  );
}
