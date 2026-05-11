import type { ReactNode } from "react";

export function PlaceholderCard({
  phase,
  title,
  blurb,
  children,
}: {
  phase: string;
  title: string;
  blurb: string;
  children?: ReactNode;
}) {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        placeItems: "center",
        padding: 24,
        // The shell's overlay container has pointer-events: none so clicks
        // pass to the globe by default. Each route surface enables its own.
        pointerEvents: "auto",
        background: "hsl(220 30% 3% / 0.65)",
        backdropFilter: "blur(8px) saturate(1.1)",
      }}
    >
      <div
        className="glass-strong"
        style={{
          maxWidth: 640,
          width: "100%",
          padding: 40,
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
            color: "var(--color-cyan-glow)",
            marginBottom: 12,
          }}
        >
          {phase}
        </div>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2rem, 4vw, 3rem)",
            fontWeight: 700,
            letterSpacing: "-0.03em",
            margin: 0,
            color: "var(--color-text-hi)",
            lineHeight: 1.05,
          }}
        >
          {title}
        </h1>
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 16,
            lineHeight: 1.6,
            color: "var(--color-text-mid)",
            marginTop: 20,
          }}
        >
          {blurb}
        </p>
        {children}
      </div>
    </div>
  );
}
