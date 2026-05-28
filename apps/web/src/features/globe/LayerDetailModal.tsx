import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";

import {
  type EvacZone,
  type Fire,
  isPastEvac,
  sortEvacByDateDesc,
  useEvacActive,
  useFiresCurrent,
  useFirmsHotspots,
  useFwiToday,
  useRiskGrid,
  useSmokeForecast,
} from "@/lib/api/hooks";
import { cinematicFlyTo } from "@/lib/cesium-helpers/cinematicFlyTo";
import { parseWkt, ringCentroid } from "@/lib/cesium-helpers/wkt";
import { useFiltersStore } from "@/stores/filters";
import { useGlobeStore } from "@/stores/globe";
import { type LayerId, useLayersStore } from "@/stores/layers";
import { useSmokeStore } from "@/stores/smoke";
import { LAYER_INFO } from "./layerInfo";

const LAYER_META: Record<LayerId, { label: string; accent: string }> = {
  fires: { label: "Active Fires", accent: "var(--color-ember-500)" },
  hotspots: { label: "Satellite Hotspots", accent: "var(--color-ember-400)" },
  evac: { label: "Evacuation Zones", accent: "var(--risk-extreme)" },
  fwi: { label: "Fire Weather Index", accent: "var(--risk-moderate)" },
  smoke: { label: "Smoke Forecast", accent: "var(--color-cyan-glow)" },
  risk: { label: "AI Risk Grid", accent: "var(--risk-high)" },
};

export function LayerDetailModal() {
  const open = useLayersStore((s) => s.modalOpen);
  const close = useLayersStore((s) => s.closeModal);

  // ESC to close
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, close]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={close}
          style={{
            position: "fixed",
            inset: 0,
            background: "hsl(220 30% 2% / 0.55)",
            backdropFilter: "blur(6px)",
            display: "grid",
            placeItems: "center",
            zIndex: 60,
            pointerEvents: "auto",
          }}
        >
          <motion.div
            key="card"
            initial={{ y: 16, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 8, opacity: 0, scale: 0.98 }}
            transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
            onClick={(e) => e.stopPropagation()}
            className="glass-strong"
            style={{
              width: "min(720px, 92vw)",
              maxHeight: "min(80vh, 720px)",
              borderRadius: "var(--radius-lg)",
              boxShadow: "var(--shadow-elevated)",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
            }}
            role="dialog"
            aria-modal="true"
            aria-label={`${LAYER_META[open].label} details`}
          >
            <ModalContent layer={open} onClose={close} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ModalContent({
  layer,
  onClose,
}: {
  layer: LayerId;
  onClose: () => void;
}) {
  const meta = LAYER_META[layer];
  const info = LAYER_INFO[layer];
  const [infoOpen, setInfoOpen] = useState(false);

  return (
    <>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "16px 24px",
          borderBottom: "1px solid var(--color-stroke)",
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 10,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: meta.accent,
            }}
          >
            Layer · Browse
          </div>
          <h2
            style={{
              margin: "4px 0 0 0",
              fontFamily: "var(--font-display)",
              fontSize: 22,
              fontWeight: 700,
              color: "var(--color-text-hi)",
              letterSpacing: "-0.02em",
            }}
          >
            {meta.label}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            width: 28,
            height: 28,
            border: "1px solid var(--color-stroke)",
            background: "transparent",
            color: "var(--color-text-mid)",
            borderRadius: "var(--radius-pill)",
            cursor: "pointer",
            fontFamily: "var(--font-data)",
            fontSize: 12,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </header>

      <CollapsibleInfo info={info} meta={meta} open={infoOpen} onToggle={() => setInfoOpen((v) => !v)} />

      {layer === "fires" && <FiresBrowser />}
      {layer === "hotspots" && <HotspotsBrowser />}
      {layer === "evac" && <EvacBrowser />}
      {layer === "fwi" && <FwiBrowser />}
      {layer === "smoke" && <SmokeBrowser />}
      {layer === "risk" && <RiskBrowser />}
    </>
  );
}

// ─── Shared helpers ───────────────────────────────────────────────

function CollapsibleInfo({
  info,
  meta,
  open,
  onToggle,
}: {
  info: (typeof LAYER_INFO)[LayerId];
  meta: { label: string; accent: string };
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      style={{
        borderBottom: "1px solid var(--color-stroke)",
        background: "var(--color-bg-1)",
      }}
    >
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        style={{
          width: "100%",
          padding: "10px 24px",
          background: "transparent",
          border: "none",
          display: "flex",
          alignItems: "center",
          gap: 12,
          cursor: "pointer",
          color: "var(--color-text-mid)",
          textAlign: "left",
          fontFamily: "var(--font-data)",
          fontSize: 10,
          letterSpacing: "0.22em",
          textTransform: "uppercase",
        }}
      >
        <span style={{ color: meta.accent }}>How this layer works</span>
        <span
          style={{
            flex: 1,
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            color: "var(--color-text-low)",
            textTransform: "none",
            letterSpacing: 0,
            fontFamily: "var(--font-body)",
            fontSize: 12,
          }}
        >
          {info.what}
        </span>
        <span
          aria-hidden
          style={{
            width: 18,
            height: 18,
            display: "grid",
            placeItems: "center",
            color: "var(--color-text-low)",
            transform: open ? "rotate(180deg)" : "none",
            transition: "transform var(--dur-fast) var(--ease-out-expo)",
            fontFamily: "var(--font-data)",
            fontSize: 10,
          }}
        >
          ▾
        </span>
      </button>
      {open && (
        <div style={{ padding: "0 24px 14px 24px" }}>
          <p
            style={{
              margin: 0,
              fontFamily: "var(--font-body)",
              fontSize: 12.5,
              lineHeight: 1.55,
              color: "var(--color-text-mid)",
            }}
          >
            {info.pipeline}
          </p>
          {info.caveat && (
            <p
              style={{
                margin: "8px 0 0 0",
                fontFamily: "var(--font-body)",
                fontSize: 11,
                lineHeight: 1.5,
                color: "var(--color-text-low)",
                fontStyle: "italic",
              }}
            >
              {info.caveat}
            </p>
          )}
          <div
            style={{
              marginTop: 10,
              fontFamily: "var(--font-data)",
              fontSize: 10,
              letterSpacing: "0.06em",
              color: "var(--color-text-low)",
            }}
          >
            <span style={{ color: "var(--color-text-low)" }}>Source: </span>
            <span style={{ color: "var(--color-text-mid)" }}>{info.source}</span>
            <span style={{ color: "var(--color-stroke-strong)" }}> · </span>
            <span style={{ color: "var(--color-text-low)" }}>Refresh: </span>
            <span style={{ color: "var(--color-text-mid)" }}>{info.refresh}</span>
          </div>
        </div>
      )}
    </div>
  );
}

function flyAndClose(lon: number, lat: number, height: number) {
  const viewer = useGlobeStore.getState().viewer;
  if (!viewer) return;
  cinematicFlyTo(viewer, { lon, lat, height });
  useLayersStore.getState().closeModal();
}

function Toolbar({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        padding: "12px 24px",
        display: "flex",
        gap: 14,
        alignItems: "center",
        flexWrap: "wrap",
        borderBottom: "1px solid var(--color-stroke)",
        background: "var(--color-bg-2)",
      }}
    >
      {children}
    </div>
  );
}

function FilterChip({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        padding: "4px 10px",
        fontFamily: "var(--font-data)",
        fontSize: 10,
        letterSpacing: "0.16em",
        textTransform: "uppercase",
        borderRadius: "var(--radius-pill)",
        border: `1px solid ${active ? "var(--color-ember-500)" : "var(--color-stroke)"}`,
        background: active ? "color-mix(in oklab, var(--color-ember-500) 12%, transparent)" : "transparent",
        color: active ? "var(--color-text-hi)" : "var(--color-text-mid)",
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}

function ResultsList<T>({
  items,
  empty,
  render,
}: {
  items: T[];
  empty: string;
  render: (item: T, i: number) => ReactNode;
}) {
  if (items.length === 0) {
    return (
      <div
        style={{
          padding: 48,
          textAlign: "center",
          color: "var(--color-text-low)",
          fontFamily: "var(--font-body)",
          fontSize: 14,
        }}
      >
        {empty}
      </div>
    );
  }
  return (
    <div style={{ flex: 1, overflowY: "auto" }}>
      {items.map((item, i) => render(item, i))}
    </div>
  );
}

function Row({
  onClick,
  primary,
  secondary,
  badge,
  badgeColor,
}: {
  onClick: () => void;
  primary: ReactNode;
  secondary: ReactNode;
  badge?: ReactNode;
  badgeColor?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 16,
        width: "100%",
        padding: "12px 24px",
        background: "transparent",
        border: "none",
        borderBottom: "1px solid var(--color-stroke)",
        color: "var(--color-text-hi)",
        cursor: "pointer",
        textAlign: "left",
        fontFamily: "var(--font-body)",
        transition: "background var(--dur-fast) var(--ease-out-expo)",
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-bg-3)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: 14,
            fontWeight: 500,
            color: "var(--color-text-hi)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {primary}
        </div>
        <div
          style={{
            fontSize: 11,
            color: "var(--color-text-low)",
            fontFamily: "var(--font-data)",
            letterSpacing: "0.06em",
            marginTop: 2,
          }}
        >
          {secondary}
        </div>
      </div>
      {badge != null && (
        <span
          className="tabular"
          style={{
            fontSize: 11,
            padding: "3px 10px",
            borderRadius: "var(--radius-pill)",
            border: `1px solid ${badgeColor ?? "var(--color-stroke)"}`,
            color: badgeColor ?? "var(--color-text-mid)",
            background: badgeColor
              ? `color-mix(in oklab, ${badgeColor} 12%, transparent)`
              : "transparent",
            fontFamily: "var(--font-data)",
            letterSpacing: "0.06em",
            flexShrink: 0,
          }}
        >
          {badge}
        </span>
      )}
      <span
        aria-hidden
        style={{
          color: "var(--color-text-low)",
          fontFamily: "var(--font-data)",
          fontSize: 14,
          flexShrink: 0,
        }}
      >
        →
      </span>
    </button>
  );
}

function SearchInput({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      style={{
        flex: 1,
        minWidth: 200,
        padding: "8px 12px",
        background: "var(--color-bg-1)",
        border: "1px solid var(--color-stroke)",
        borderRadius: "var(--radius-md)",
        color: "var(--color-text-hi)",
        fontFamily: "var(--font-body)",
        fontSize: 13,
        outline: "none",
      }}
    />
  );
}

// ─── Per-layer browsers ───────────────────────────────────────────

function fireCentroid(f: Fire): [number, number] | null {
  if (f.geom_wkt) {
    const parsed = parseWkt(f.geom_wkt);
    if (parsed && parsed.positions.length) {
      const c = ringCentroid(parsed.positions[0]);
      if (c) return c;
    }
  }
  if (f.longitude != null && f.latitude != null) return [f.longitude, f.latitude];
  return null;
}

function FiresBrowser() {
  const filter = useFiltersStore((s) => s.fires);
  const setFires = useFiltersStore((s) => s.setFires);
  // Always fetch with include_extinguished so we can toggle client-side.
  const { data: hooks } = useFiresCurrent();
  const [search, setSearch] = useState("");

  const items = useMemo(() => {
    const arr = hooks ?? [];
    return arr.filter((f) => {
      const status = (f.status ?? "").toLowerCase();
      const isOut = status === "out" || status === "extinguished";
      if (isOut && !filter.includeExtinguished) return false;
      if (filter.statuses.length > 0 && !filter.statuses.some((s) => status.includes(s.toLowerCase())))
        return false;
      if ((f.hectares ?? 0) < filter.minHectares) return false;
      if (search && !(f.fire_name ?? "").toLowerCase().includes(search.toLowerCase()))
        return false;
      return true;
    });
  }, [hooks, filter, search]);

  return (
    <>
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search by fire name…" />
        <FilterChip
          active={filter.includeExtinguished}
          onClick={() => setFires({ includeExtinguished: !filter.includeExtinguished })}
        >
          Include extinguished
        </FilterChip>
        <FilterChip
          active={filter.minHectares >= 10}
          onClick={() => setFires({ minHectares: filter.minHectares >= 10 ? 0 : 10 })}
        >
          ≥ 10 ha
        </FilterChip>
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-low)" }}>
          {items.length} match{items.length === 1 ? "" : "es"}
        </span>
      </Toolbar>
      <ResultsList
        items={items}
        empty="No fires match the current filters."
        render={(f) => {
          const c = fireCentroid(f);
          return (
            <Row
              key={f.fire_id}
              onClick={() => c && flyAndClose(c[0], c[1], 35_000)}
              primary={f.fire_name || `Fire ${f.fire_id}`}
              secondary={`${f.status ?? "—"} · ${f.stage_of_control ?? "—"}`}
              badge={f.hectares != null ? `${f.hectares.toLocaleString()} ha` : "—"}
              badgeColor="var(--color-ember-400)"
            />
          );
        }}
      />
    </>
  );
}

function HotspotsBrowser() {
  const filter = useFiltersStore((s) => s.hotspots);
  const setHotspots = useFiltersStore((s) => s.setHotspots);
  const { data: hooks } = useFirmsHotspots(filter.sinceHours);
  const [search, setSearch] = useState("");

  const items = useMemo(() => {
    const arr = hooks ?? [];
    return arr.filter((h) => {
      if ((h.confidence ?? 100) < filter.minConfidence) return false;
      if (filter.sources.length > 0 && !filter.sources.includes(h.source)) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!h.source.toLowerCase().includes(q) && !(h.satellite ?? "").toLowerCase().includes(q))
          return false;
      }
      return true;
    });
  }, [hooks, filter, search]);

  return (
    <>
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search satellite…" />
        <FilterChip
          active={filter.sinceHours === 24}
          onClick={() => setHotspots({ sinceHours: 24 })}
        >
          24h
        </FilterChip>
        <FilterChip
          active={filter.sinceHours === 72}
          onClick={() => setHotspots({ sinceHours: 72 })}
        >
          72h
        </FilterChip>
        <FilterChip
          active={filter.minConfidence >= 70}
          onClick={() => setHotspots({ minConfidence: filter.minConfidence >= 70 ? 30 : 70 })}
        >
          High confidence
        </FilterChip>
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-low)" }}>
          {items.length} hotspot{items.length === 1 ? "" : "s"}
        </span>
      </Toolbar>
      <ResultsList
        items={items}
        empty="No satellite hotspots match the current filters."
        render={(h, i) => (
          <Row
            key={`${h.latitude}-${h.longitude}-${h.acq_datetime_utc}-${i}`}
            onClick={() => flyAndClose(h.longitude, h.latitude, 12_000)}
            primary={`${h.source} · ${h.acq_datetime_utc}`}
            secondary={`${h.latitude.toFixed(3)}, ${h.longitude.toFixed(3)} · brightness ${h.brightness ?? "—"} K`}
            badge={h.frp != null ? `${h.frp.toFixed(1)} MW` : "—"}
            badgeColor="var(--color-ember-400)"
          />
        )}
      />
    </>
  );
}

function evacCentroid(z: EvacZone): [number, number] | null {
  if (!z.geom_wkt) return null;
  const parsed = parseWkt(z.geom_wkt);
  if (!parsed || !parsed.positions.length) return null;
  return ringCentroid(parsed.positions[0]);
}

function EvacBrowser() {
  const filter = useFiltersStore((s) => s.evac);
  const setEvac = useFiltersStore((s) => s.setEvac);
  const { data: hooks } = useEvacActive();
  const [search, setSearch] = useState("");

  const items = useMemo(() => {
    const arr = hooks ?? [];
    const filtered = arr.filter((z) => {
      if (filter.hidePast && isPastEvac(z)) return false;
      const status = (z.status ?? "").toLowerCase();
      if (filter.statuses.length > 0 && !filter.statuses.some((s) => status.includes(s.toLowerCase())))
        return false;
      if (search) {
        const q = search.toLowerCase();
        if (!(z.event_name ?? "").toLowerCase().includes(q)) return false;
      }
      return true;
    });
    // Newest issued first.
    return sortEvacByDateDesc(filtered);
  }, [hooks, filter, search]);

  const statusActive = (s: string) => filter.statuses.includes(s);
  const toggleStatus = (s: string) =>
    setEvac({
      statuses: statusActive(s)
        ? filter.statuses.filter((x) => x !== s)
        : [...filter.statuses, s],
    });

  return (
    <>
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search by event name…" />
        <FilterChip active={statusActive("Order")} onClick={() => toggleStatus("Order")}>Order</FilterChip>
        <FilterChip active={statusActive("Alert")} onClick={() => toggleStatus("Alert")}>Alert</FilterChip>
        <FilterChip active={statusActive("Rescind")} onClick={() => toggleStatus("Rescind")}>Rescind</FilterChip>
        <FilterChip active={filter.hidePast} onClick={() => setEvac({ hidePast: !filter.hidePast })}>
          {filter.hidePast ? "Hiding past" : "Show past"}
        </FilterChip>
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-low)" }}>
          {items.length} zone{items.length === 1 ? "" : "s"} · newest first
        </span>
      </Toolbar>
      <ResultsList
        items={items}
        empty="No evacuation zones match the current filters."
        render={(z, i) => {
          const c = evacCentroid(z);
          const status = (z.status ?? "").toLowerCase();
          const color = status.includes("order")
            ? "var(--risk-extreme)"
            : status.includes("alert")
            ? "var(--risk-high)"
            : "var(--risk-low)";
          return (
            <Row
              key={(z.event_id ?? z.event_name ?? "") + i}
              onClick={() => c && flyAndClose(c[0], c[1], 25_000)}
              primary={z.event_name || "Unnamed event"}
              secondary={`${z.issuing_agency ?? "—"} · ${z.issued_utc ?? "—"}`}
              badge={z.status ?? "—"}
              badgeColor={color}
            />
          );
        }}
      />
    </>
  );
}

function FwiBrowser() {
  const filter = useFiltersStore((s) => s.fwi);
  const setFwi = useFiltersStore((s) => s.setFwi);
  const { data: hooks } = useFwiToday();
  const [search, setSearch] = useState("");

  const items = useMemo(() => {
    const arr = hooks ?? [];
    return arr.filter((s) => {
      if ((s.fwi ?? 0) < filter.minFwi) return false;
      if (search && !(s.station_name ?? "").toLowerCase().includes(search.toLowerCase()))
        return false;
      return true;
    });
  }, [hooks, filter, search]);

  return (
    <>
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search station…" />
        <FilterChip active={filter.minFwi >= 5} onClick={() => setFwi({ minFwi: filter.minFwi >= 5 ? 0 : 5 })}>
          FWI ≥ 5
        </FilterChip>
        <FilterChip active={filter.minFwi >= 12} onClick={() => setFwi({ minFwi: filter.minFwi >= 12 ? 0 : 12 })}>
          FWI ≥ 12
        </FilterChip>
        <FilterChip active={filter.minFwi >= 19} onClick={() => setFwi({ minFwi: filter.minFwi >= 19 ? 0 : 19 })}>
          Extreme (≥ 19)
        </FilterChip>
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-low)" }}>
          {items.length} station{items.length === 1 ? "" : "s"}
        </span>
      </Toolbar>
      <ResultsList
        items={items}
        empty="No FWI stations available — CWFIS upstream may be down."
        render={(s) => {
          const fwi = s.fwi ?? 0;
          const color =
            fwi < 5
              ? "var(--risk-low)"
              : fwi < 12
              ? "var(--risk-moderate)"
              : fwi < 19
              ? "var(--risk-high)"
              : "var(--risk-extreme)";
          return (
            <Row
              key={s.station_id}
              onClick={() => flyAndClose(s.longitude, s.latitude, 35_000)}
              primary={s.station_name}
              secondary={`FFMC ${s.ffmc ?? "—"} · DMC ${s.dmc ?? "—"} · DC ${s.dc ?? "—"} · ${s.observation_date_local ?? "—"}`}
              badge={`FWI ${s.fwi ?? "—"}`}
              badgeColor={color}
            />
          );
        }}
      />
    </>
  );
}

function RiskBrowser() {
  const { data, isLoading } = useRiskGrid();
  const [search, setSearch] = useState("");
  const [classFilter, setClassFilter] = useState<string | null>("Extreme");

  if (isLoading || !data) {
    return (
      <div style={{ padding: 48, textAlign: "center", color: "var(--color-text-low)", fontFamily: "var(--font-body)" }}>
        Loading risk grid…
      </div>
    );
  }

  const items = data.cells.filter((c) => {
    if (classFilter && c.risk_class !== classFilter) return false;
    if (search && !c.h3_cell.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  const counts: Record<string, number> = { Low: 0, Moderate: 0, High: 0, Extreme: 0 };
  for (const c of data.cells) counts[c.risk_class] += 1;

  return (
    <>
      <Toolbar>
        <SearchInput value={search} onChange={setSearch} placeholder="Search cell id…" />
        {(["Extreme", "High", "Moderate", "Low"] as const).map((k) => (
          <FilterChip
            key={k}
            active={classFilter === k}
            onClick={() => setClassFilter(classFilter === k ? null : k)}
          >
            {k} · {counts[k]}
          </FilterChip>
        ))}
        <span style={{ marginLeft: "auto", fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-low)" }}>
          P(fire today) · region {(data.p_region * 100).toFixed(0)}%
          {data.cffdrs_class && (
            <>
              <span style={{ color: "var(--color-stroke-strong)" }}> · </span>
              CFFDRS{" "}
              <span style={{ color: "var(--color-text-hi)" }}>
                {data.cffdrs_class}
              </span>
              {data.fwi_today != null && (
                <span style={{ color: "var(--color-text-low)" }}>
                  {" "}(FWI {data.fwi_today.toFixed(1)})
                </span>
              )}
            </>
          )}
        </span>
      </Toolbar>
      <ResultsList
        items={items}
        empty="No cells match the current filter."
        render={(c) => {
          const color =
            c.risk_class === "Extreme"
              ? "var(--risk-extreme)"
              : c.risk_class === "High"
              ? "var(--risk-high)"
              : c.risk_class === "Moderate"
              ? "var(--risk-moderate)"
              : "var(--risk-low)";
          return (
            <Row
              key={c.h3_cell}
              onClick={() => flyAndClose(c.centroid_lon, c.centroid_lat, 35_000)}
              primary={`${c.h3_cell.slice(0, 8)}… · ${c.centroid_lat.toFixed(3)}, ${c.centroid_lon.toFixed(3)}`}
              secondary={`P(cell) ${(c.p_cell * 100).toFixed(1)}% · historical fires ${c.hist_fire_count}`}
              badge={c.risk_class}
              badgeColor={color}
            />
          );
        }}
      />
    </>
  );
}

function SmokeBrowser() {
  const { data, isLoading } = useSmokeForecast();
  const timestepIndex = useSmokeStore((s) => s.timestepIndex);
  const setTimestepIndex = useSmokeStore((s) => s.setTimestepIndex);
  const setLayerOn = useLayersStore((s) => s.set);
  const smokeVisible = useLayersStore((s) => s.visible.smoke);

  // When the user opens this modal we autoturn-on the smoke layer so the
  // scrubber's changes are visible on the globe immediately.
  useEffect(() => {
    if (!smokeVisible) setLayerOn("smoke", true);
  }, [setLayerOn, smokeVisible]);

  if (isLoading || !data) {
    return (
      <div style={{ padding: 48, textAlign: "center", color: "var(--color-text-low)", fontFamily: "var(--font-body)" }}>
        Loading forecast timesteps…
      </div>
    );
  }
  if (data.length === 0) {
    return (
      <div style={{ padding: 48, textAlign: "center", color: "var(--color-text-low)", fontFamily: "var(--font-body)" }}>
        No smoke forecast timesteps available right now.
      </div>
    );
  }

  const safeIndex = Math.min(Math.max(0, timestepIndex), data.length - 1);
  const current = data[safeIndex];

  const fmt = (iso: string) => {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return new Intl.DateTimeFormat("en-CA", {
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "America/Vancouver",
    }).format(d);
  };

  const hoursFromNow = (iso: string) => {
    const d = new Date(iso).getTime();
    const now = Date.now();
    const hrs = Math.round((d - now) / 3_600_000);
    if (hrs === 0) return "now";
    if (hrs > 0) {
      if (hrs < 24) return `+${hrs} h`;
      return `+${Math.round(hrs / 24)} d`;
    }
    const past = Math.abs(hrs);
    if (past < 24) return `${past} h ago`;
    return `${Math.round(past / 24)} d ago`;
  };

  // Colour-coded PM2.5 badge tracking US-EPA AQI breakpoints.
  const pm25Color = (v: number | null | undefined) => {
    if (v == null) return "var(--color-stroke)";
    if (v < 12) return "var(--aq-3)";
    if (v < 35) return "var(--aq-5)";
    if (v < 55) return "var(--aq-7)";
    if (v < 150) return "var(--aq-9)";
    return "var(--aq-plus)";
  };
  const pm25Label = (v: number | null | undefined) =>
    v == null ? "no data" : `${v.toFixed(1)} µg/m³`;

  return (
    <>
      <Toolbar>
        <FilterChip
          active={false}
          onClick={() => setTimestepIndex(Math.max(0, safeIndex - 1))}
        >
          ← Prev
        </FilterChip>
        <FilterChip
          active={false}
          onClick={() => setTimestepIndex(Math.min(data.length - 1, safeIndex + 1))}
        >
          Next →
        </FilterChip>
        <div
          className="tabular"
          style={{
            flex: 1,
            display: "flex",
            alignItems: "center",
            gap: 12,
            fontFamily: "var(--font-data)",
            fontSize: 11,
            color: "var(--color-text-low)",
            letterSpacing: "0.08em",
          }}
        >
          <input
            type="range"
            min={0}
            max={data.length - 1}
            value={safeIndex}
            onChange={(e) => setTimestepIndex(Number(e.target.value))}
            aria-label="Forecast timestep"
            style={{
              flex: 1,
              accentColor: "var(--color-cyan-glow)",
            }}
          />
          <span style={{ color: "var(--color-text-hi)", whiteSpace: "nowrap" }}>
            {fmt(current.valid_time_utc)}
          </span>
          <span style={{ color: "var(--color-cyan-glow)", whiteSpace: "nowrap" }}>
            {hoursFromNow(current.valid_time_utc)}
          </span>
          <span
            className="tabular"
            style={{
              padding: "3px 10px",
              borderRadius: "var(--radius-pill)",
              border: `1px solid ${pm25Color(current.pm25_at_kamloops)}`,
              color: pm25Color(current.pm25_at_kamloops),
              background: `color-mix(in oklab, ${pm25Color(current.pm25_at_kamloops)} 14%, transparent)`,
              fontSize: 10,
              letterSpacing: "0.06em",
              whiteSpace: "nowrap",
            }}
            title="Open-Meteo CAMS PM2.5 forecast at Kamloops centroid for this hour"
          >
            PM2.5 {pm25Label(current.pm25_at_kamloops)}
          </span>
        </div>
      </Toolbar>
      <div
        style={{
          padding: "8px 24px",
          fontFamily: "var(--font-body)",
          fontSize: 11.5,
          color: "var(--color-text-low)",
          background: "var(--color-bg-2)",
          borderBottom: "1px solid var(--color-stroke)",
          lineHeight: 1.5,
        }}
      >
        The WMS overlay is mostly transparent when PM2.5 is low — that's the
        truth, not a missing image. The colour-coded PM2.5 badge on each
        timestep below shows the Open-Meteo CAMS forecast value at Kamloops
        so you can see what the ECCC model is actually predicting.
      </div>
      <div style={{ flex: 1, overflowY: "auto" }}>
        {data.map((step, i) => {
          const active = i === safeIndex;
          return (
            <button
              key={`${step.valid_time_utc}-${i}`}
              type="button"
              onClick={() => setTimestepIndex(i)}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                width: "100%",
                padding: "12px 24px",
                background: active ? "var(--color-bg-3)" : "transparent",
                border: "none",
                borderBottom: "1px solid var(--color-stroke)",
                borderLeft: active
                  ? "3px solid var(--color-cyan-glow)"
                  : "3px solid transparent",
                cursor: "pointer",
                fontFamily: "var(--font-body)",
                textAlign: "left",
                transition: "background var(--dur-fast)",
              }}
              onMouseEnter={(e) => {
                if (!active) e.currentTarget.style.background = "var(--color-bg-2)";
              }}
              onMouseLeave={(e) => {
                if (!active) e.currentTarget.style.background = "transparent";
              }}
            >
              <div style={{ flex: 1 }}>
                <div
                  style={{
                    fontSize: 13,
                    color: active ? "var(--color-text-hi)" : "var(--color-text-mid)",
                  }}
                >
                  {fmt(step.valid_time_utc)}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    fontFamily: "var(--font-data)",
                    color: "var(--color-text-low)",
                    letterSpacing: "0.06em",
                    marginTop: 2,
                  }}
                >
                  {step.layer_name}
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 4,
                  alignItems: "flex-end",
                }}
              >
                <span
                  className="tabular"
                  style={{
                    fontSize: 11,
                    padding: "3px 10px",
                    borderRadius: "var(--radius-pill)",
                    border: `1px solid ${pm25Color(step.pm25_at_kamloops)}`,
                    color: pm25Color(step.pm25_at_kamloops),
                    background: `color-mix(in oklab, ${pm25Color(step.pm25_at_kamloops)} 14%, transparent)`,
                    fontFamily: "var(--font-data)",
                    letterSpacing: "0.06em",
                    whiteSpace: "nowrap",
                  }}
                >
                  {pm25Label(step.pm25_at_kamloops)}
                </span>
                <span
                  className="tabular"
                  style={{
                    fontSize: 9,
                    letterSpacing: "0.18em",
                    color: active ? "var(--color-cyan-glow)" : "var(--color-text-low)",
                    fontFamily: "var(--font-data)",
                    textTransform: "uppercase",
                  }}
                >
                  {hoursFromNow(step.valid_time_utc)}
                </span>
              </div>
            </button>
          );
        })}
      </div>
    </>
  );
}

// avoid unused-import lint for refs we may use in keyboard nav later
export const _LayerDetailModalUnused = useRef;
