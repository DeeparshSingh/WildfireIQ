/**
 * Glassmorphic popover anchored to the layer-info icon.
 * Shows the 1-2 paragraph plain-English explanation of how the layer works.
 * Click anywhere outside or press Escape to dismiss.
 */
import { useEffect, useRef } from "react";
import { motion } from "motion/react";

import { LAYER_INFO } from "./layerInfo";
import type { LayerId } from "@/stores/layers";

export function LayerInfoPopover({
  layer,
  onClose,
}: {
  layer: LayerId;
  onClose: () => void;
}) {
  const info = LAYER_INFO[layer];
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDocClick = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    // Run on next tick so the click that opened the popover doesn't immediately close it.
    const t = window.setTimeout(() => {
      document.addEventListener("mousedown", onDocClick);
    }, 0);
    document.addEventListener("keydown", onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <motion.div
      ref={ref}
      initial={{ opacity: 0, y: -4, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
      className="glass-strong"
      role="dialog"
      aria-label={`How ${layer} works`}
      style={{
        position: "absolute",
        top: "calc(100% + 6px)",
        right: 0,
        width: 360,
        padding: "16px 18px",
        borderRadius: "var(--radius-md)",
        boxShadow: "var(--shadow-elevated)",
        pointerEvents: "auto",
        zIndex: 50,
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 9,
          letterSpacing: "0.28em",
          textTransform: "uppercase",
          color: "var(--color-ember-400)",
          marginBottom: 10,
        }}
      >
        How this layer works
      </div>
      <p
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 13,
          lineHeight: 1.55,
          color: "var(--color-text-hi)",
          margin: 0,
        }}
      >
        {info.what}
      </p>
      <p
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 12,
          lineHeight: 1.55,
          color: "var(--color-text-mid)",
          margin: "12px 0 0 0",
        }}
      >
        {info.pipeline}
      </p>
      {info.caveat && (
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 11,
            lineHeight: 1.5,
            color: "var(--color-text-low)",
            margin: "10px 0 0 0",
            fontStyle: "italic",
          }}
        >
          {info.caveat}
        </p>
      )}
      <div
        style={{
          marginTop: 14,
          paddingTop: 12,
          borderTop: "1px solid var(--color-stroke)",
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          columnGap: 10,
          rowGap: 4,
          fontFamily: "var(--font-data)",
          fontSize: 10,
          letterSpacing: "0.06em",
        }}
      >
        <span style={{ color: "var(--color-text-low)" }}>Source</span>
        <span style={{ color: "var(--color-text-hi)" }}>{info.source}</span>
        <span style={{ color: "var(--color-text-low)" }}>Refresh</span>
        <span style={{ color: "var(--color-text-mid)" }}>{info.refresh}</span>
      </div>
    </motion.div>
  );
}
