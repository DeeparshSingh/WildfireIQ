/**
 * Methodology popover — the small (i) chip that opens a card with source,
 * method, and a "Download CSV" button. Used by every chart in /climate.
 */
import { useEffect, useRef, useState } from "react";

export function InfoChip({
  source,
  method,
  downloadUrl,
  downloadName,
}: {
  source: string;
  method: string;
  downloadUrl?: string;
  downloadName?: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <div ref={ref} style={{ position: "relative", display: "inline-block" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Methodology"
        style={{
          width: 22,
          height: 22,
          borderRadius: 999,
          border: "1px solid hsl(200 80% 50% / 0.35)",
          background: "hsl(220 30% 10% / 0.7)",
          color: "var(--color-cyan-glow)",
          fontFamily: "var(--font-data)",
          fontSize: 11,
          fontWeight: 700,
          cursor: "pointer",
        }}
      >
        i
      </button>
      {open && (
        <div
          className="glass-strong"
          style={{
            position: "absolute",
            right: 0,
            top: 30,
            minWidth: 280,
            maxWidth: 360,
            zIndex: 30,
            padding: 14,
            borderRadius: 10,
            display: "grid",
            gap: 8,
          }}
        >
          <div style={{ fontFamily: "var(--font-data)", fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--color-text-mid)" }}>
            Source
          </div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: 12, lineHeight: 1.5, color: "var(--color-text-hi)" }}>
            {source}
          </div>
          <div style={{ fontFamily: "var(--font-data)", fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--color-text-mid)", marginTop: 4 }}>
            Method
          </div>
          <div style={{ fontFamily: "var(--font-body)", fontSize: 12, lineHeight: 1.5, color: "var(--color-text-mid)" }}>
            {method}
          </div>
          {downloadUrl && (
            <a
              href={downloadUrl}
              download={downloadName ?? "climate.csv"}
              style={{
                marginTop: 6,
                padding: "8px 12px",
                background: "hsl(18 95% 54%)",
                color: "white",
                border: "none",
                borderRadius: 6,
                fontFamily: "var(--font-body)",
                fontSize: 12,
                fontWeight: 600,
                textDecoration: "none",
                textAlign: "center",
              }}
            >
              ↓ Download CSV
            </a>
          )}
        </div>
      )}
    </div>
  );
}
