import { useEffect, useState, type ReactNode } from "react";
import { motion } from "motion/react";

import {
  useEvacActive,
  useFiresCurrent,
  useFirmsHotspots,
  useFwiToday,
  useSmokeForecast,
} from "@/lib/api/hooks";
import { type LayerId, useLayersStore } from "@/stores/layers";

type LayerDef = {
  id: LayerId;
  label: string;
  glyph: string;
  /** Tailwind/CSS-var hue for the live-count badge. */
  accent: string;
  count: number | undefined;
};

function useLayerCounts(): LayerDef[] {
  const fires = useFiresCurrent();
  const hotspots = useFirmsHotspots(24);
  const evac = useEvacActive();
  const fwi = useFwiToday();
  const smoke = useSmokeForecast();

  return [
    {
      id: "fires",
      label: "Active Fires",
      glyph: "▲",
      accent: "var(--color-ember-500)",
      count: fires.data?.length,
    },
    {
      id: "hotspots",
      label: "Satellite Hotspots",
      glyph: "·",
      accent: "var(--color-ember-400)",
      count: hotspots.data?.length,
    },
    {
      id: "evac",
      label: "Evacuation",
      glyph: "◇",
      accent: "var(--risk-extreme)",
      count: evac.data?.length,
    },
    {
      id: "fwi",
      label: "Fire Weather Index",
      glyph: "⚡",
      accent: "var(--risk-moderate)",
      count: fwi.data?.length,
    },
    {
      id: "smoke",
      label: "Smoke Forecast",
      glyph: "≋",
      accent: "var(--color-cyan-glow)",
      count: smoke.data?.length,
    },
  ];
}

export function LayerToggleBar() {
  const layers = useLayerCounts();
  const visible = useLayersStore((s) => s.visible);
  const toggle = useLayersStore((s) => s.toggle);
  const [spotlight, setSpotlight] = useState<LayerId | null>(null);

  return (
    <motion.div
      initial={{ x: 32, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      transition={{ duration: 0.5, delay: 1.0, ease: [0.16, 1, 0.3, 1] }}
      style={{
        position: "absolute",
        right: 16,
        top: 16,
        display: "flex",
        flexDirection: "column",
        gap: 6,
        pointerEvents: "auto",
        zIndex: 20,
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 9,
          letterSpacing: "0.28em",
          textTransform: "uppercase",
          color: "var(--color-text-low)",
          padding: "0 6px 4px 6px",
          textAlign: "right",
        }}
      >
        Layers
      </div>
      {layers.map((layer) => (
        <LayerToggle
          key={layer.id}
          layer={layer}
          on={visible[layer.id]}
          dim={spotlight !== null && spotlight !== layer.id}
          onToggle={() => toggle(layer.id)}
          onOpenModal={() => useLayersStore.getState().openModal(layer.id)}
          onHoverStart={() => setSpotlight(layer.id)}
          onHoverEnd={() => setSpotlight(null)}
        />
      ))}
    </motion.div>
  );
}

function LayerToggle({
  layer,
  on,
  dim,
  onToggle,
  onOpenModal,
  onHoverStart,
  onHoverEnd,
}: {
  layer: LayerDef;
  on: boolean;
  dim: boolean;
  onToggle: () => void;
  onOpenModal: () => void;
  onHoverStart: () => void;
  onHoverEnd: () => void;
}) {
  return (
    <div
      onMouseEnter={onHoverStart}
      onMouseLeave={onHoverEnd}
      className="glass"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        padding: "10px 14px",
        borderRadius: "var(--radius-md)",
        minWidth: 240,
        opacity: dim ? 0.35 : 1,
        transition:
          "opacity var(--dur-base) var(--ease-out-expo), background var(--dur-fast) var(--ease-out-expo)",
        color: "var(--color-text-hi)",
      }}
    >
      <button
        type="button"
        onClick={onOpenModal}
        aria-label={`Browse ${layer.label}`}
        title="Click to browse all items in this layer"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          flex: 1,
          minWidth: 0,
          padding: 0,
          background: "transparent",
          border: "none",
          color: "inherit",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span
          aria-hidden
          style={{
            width: 22,
            height: 22,
            display: "grid",
            placeItems: "center",
            color: on ? layer.accent : "var(--color-text-low)",
            fontFamily: "var(--font-data)",
            fontSize: 14,
            transition: "color var(--dur-fast)",
            flexShrink: 0,
          }}
        >
          {layer.glyph}
        </span>
        <span
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 13,
            color: on ? "var(--color-text-hi)" : "var(--color-text-mid)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {layer.label}
        </span>
      </button>
      <Badge count={layer.count} on={on} accent={layer.accent} />
      <button
        type="button"
        onClick={onToggle}
        aria-label={`${on ? "Hide" : "Show"} ${layer.label}`}
        title={on ? "Hide layer" : "Show layer"}
        style={{
          padding: 0,
          background: "transparent",
          border: "none",
          cursor: "pointer",
          display: "flex",
          alignItems: "center",
        }}
      >
        <Switch on={on} accent={layer.accent} />
      </button>
    </div>
  );
}

function Badge({
  count,
  on,
  accent,
}: {
  count: number | undefined;
  on: boolean;
  accent: string;
}) {
  if (count == null) {
    return (
      <span
        className="tabular"
        style={{
          fontSize: 10,
          color: "var(--color-text-low)",
          letterSpacing: "0.06em",
        }}
      >
        —
      </span>
    );
  }
  return (
    <span
      className="tabular"
      style={{
        minWidth: 24,
        height: 18,
        padding: "0 6px",
        display: "grid",
        placeItems: "center",
        fontSize: 10,
        fontWeight: 600,
        borderRadius: "var(--radius-pill)",
        color: on ? accent : "var(--color-text-low)",
        background: on ? `color-mix(in oklab, ${accent} 16%, transparent)` : "transparent",
        border: `1px solid ${on ? `color-mix(in oklab, ${accent} 50%, transparent)` : "var(--color-stroke)"}`,
        letterSpacing: "0.04em",
      }}
    >
      {count}
    </span>
  );
}

function Switch({ on, accent }: { on: boolean; accent: string }): ReactNode {
  return (
    <span
      aria-hidden
      style={{
        width: 28,
        height: 16,
        borderRadius: "var(--radius-pill)",
        background: on ? accent : "var(--color-bg-3)",
        position: "relative",
        boxShadow: on ? `0 0 12px ${accent}55` : "none",
        transition: "background var(--dur-fast), box-shadow var(--dur-fast)",
      }}
    >
      <span
        style={{
          position: "absolute",
          top: 2,
          left: on ? 14 : 2,
          width: 12,
          height: 12,
          borderRadius: "50%",
          background: "var(--color-text-hi)",
          transition: "left var(--dur-fast) var(--ease-out-expo)",
        }}
      />
    </span>
  );
}

// react-effect listener: when the bar mounts, capture useEffect ref for future
// keyboard shortcuts (e.g. press `1`–`5` to toggle layers).
export function useLayerKeyboardShortcuts() {
  const toggle = useLayersStore((s) => s.toggle);
  useEffect(() => {
    const ids: LayerId[] = ["fires", "hotspots", "evac", "fwi", "smoke"];
    const onKey = (e: KeyboardEvent) => {
      if (document.activeElement?.tagName === "INPUT") return;
      const idx = "12345".indexOf(e.key);
      if (idx >= 0 && idx < ids.length) {
        e.preventDefault();
        toggle(ids[idx]);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [toggle]);
}
