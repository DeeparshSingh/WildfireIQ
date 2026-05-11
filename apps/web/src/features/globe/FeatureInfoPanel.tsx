import { useMemo } from "react";
import { AnimatePresence, motion } from "motion/react";

import {
  type EvacZone,
  type Fire,
  type FwiStation,
  type Hotspot,
  useEvacActive,
  useFiresCurrent,
  useFirmsHotspots,
  useFwiToday,
} from "@/lib/api/hooks";
import { type SelectedFeature, useLayersStore } from "@/stores/layers";

export function FeatureInfoPanel() {
  const selected = useLayersStore((s) => s.selected);
  const close = () => useLayersStore.getState().select(null);

  return (
    <AnimatePresence>
      {selected && (
        <motion.aside
          key={`${selected.kind}-${selected.id}`}
          initial={{ x: 32, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 32, opacity: 0 }}
          transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
          className="glass-strong"
          style={{
            position: "absolute",
            top: 16,
            right: 16,
            bottom: 16,
            width: 380,
            padding: 0,
            borderRadius: "var(--radius-lg)",
            overflow: "hidden",
            boxShadow: "var(--shadow-elevated)",
            display: "flex",
            flexDirection: "column",
            pointerEvents: "auto",
            zIndex: 25,
          }}
          aria-live="polite"
        >
          <header
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "14px 20px",
              borderBottom: "1px solid var(--color-stroke)",
            }}
          >
            <span
              style={{
                fontFamily: "var(--font-data)",
                fontSize: 10,
                letterSpacing: "0.28em",
                textTransform: "uppercase",
                color: "var(--color-ember-400)",
              }}
            >
              {kindLabel(selected.kind)}
            </span>
            <button
              type="button"
              onClick={close}
              aria-label="Close"
              style={{
                width: 28,
                height: 28,
                border: "1px solid var(--color-stroke)",
                background: "transparent",
                color: "var(--color-text-mid)",
                borderRadius: "var(--radius-pill)",
                fontFamily: "var(--font-data)",
                fontSize: 12,
                cursor: "pointer",
                lineHeight: 1,
              }}
            >
              ×
            </button>
          </header>
          <div style={{ flex: 1, overflowY: "auto", padding: "20px 24px" }}>
            <PanelBody selected={selected} />
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

function kindLabel(kind: SelectedFeature["kind"]): string {
  switch (kind) {
    case "fire":
      return "Active fire";
    case "hotspot":
      return "Satellite hotspot";
    case "evac":
      return "Evacuation zone";
    case "fwi":
      return "FWI station";
  }
}

function PanelBody({ selected }: { selected: SelectedFeature }) {
  switch (selected.kind) {
    case "fire":
      return <FireDetail id={selected.id} />;
    case "hotspot":
      return <HotspotDetail id={selected.id} />;
    case "evac":
      return <EvacDetail id={selected.id} />;
    case "fwi":
      return <FwiDetail id={selected.id} />;
  }
}

// ─── Fire ────────────────────────────────────────────────────────────

function FireDetail({ id }: { id: string }) {
  const { data } = useFiresCurrent();
  const fire = useMemo<Fire | undefined>(
    () => data?.find((f) => f.fire_id === id),
    [data, id],
  );
  if (!fire) return <Empty label="Fire not found" />;

  return (
    <div>
      <Title>{fire.fire_name || `Fire ${fire.fire_id}`}</Title>
      <Subtitle>{fire.stage_of_control || fire.status || "—"}</Subtitle>
      <Stats
        rows={[
          ["Size", fire.hectares != null ? `${fmt(fire.hectares)} ha` : "—"],
          ["Status", fire.status ?? "—"],
          ["Discovered", fmtDate(fire.discovery_date_utc)],
          [
            "Coordinates",
            fire.latitude != null && fire.longitude != null
              ? `${fire.latitude.toFixed(4)}, ${fire.longitude.toFixed(4)}`
              : "—",
          ],
          ["Geometry", fire.geom_kind ?? "—"],
        ]}
      />
      <Attribution>BC Wildfire Service · DataBC</Attribution>
    </div>
  );
}

// ─── Hotspot ────────────────────────────────────────────────────────

function HotspotDetail({ id }: { id: string }) {
  const { data } = useFirmsHotspots(24);
  const h = useMemo<Hotspot | undefined>(
    () =>
      data?.find(
        (x) => `${x.latitude}-${x.longitude}-${x.acq_datetime_utc}` === id,
      ),
    [data, id],
  );
  if (!h) return <Empty label="Hotspot not found" />;

  return (
    <div>
      <Title>FIRMS hotspot</Title>
      <Subtitle>{h.source || h.satellite || "Satellite detection"}</Subtitle>
      <Stats
        rows={[
          ["Detected", fmtDate(h.acq_datetime_utc)],
          ["Coordinates", `${h.latitude.toFixed(4)}, ${h.longitude.toFixed(4)}`],
          ["Brightness", h.brightness != null ? `${h.brightness.toFixed(1)} K` : "—"],
          ["FRP", h.frp != null ? `${h.frp.toFixed(1)} MW` : "—"],
          ["Confidence", h.confidence != null ? `${h.confidence}` : "—"],
          ["Day / Night", h.daynight ?? "—"],
        ]}
      />
      <Attribution>NASA FIRMS · VIIRS / MODIS NRT</Attribution>
    </div>
  );
}

// ─── Evac ────────────────────────────────────────────────────────────

function EvacDetail({ id }: { id: string }) {
  const { data } = useEvacActive();
  const z = useMemo<EvacZone | undefined>(
    () => data?.find((e) => (e.event_id || e.event_name || "") === id),
    [data, id],
  );
  if (!z) return <Empty label="Zone not found" />;

  const statusColour = ((z.status || "").toLowerCase().includes("order")
    ? "var(--risk-extreme)"
    : (z.status || "").toLowerCase().includes("alert")
    ? "var(--risk-high)"
    : "var(--risk-low)") as string;

  return (
    <div>
      <Title>{z.event_name || "Unnamed event"}</Title>
      <Subtitle style={{ color: statusColour, textShadow: `0 0 12px ${statusColour}55` }}>
        {z.status?.toUpperCase() || "—"}
      </Subtitle>
      <Stats
        rows={[
          ["Issuing agency", z.issuing_agency ?? "—"],
          ["Issued", fmtDate(z.issued_utc)],
          ["Area", z.area_hectares != null ? `${fmt(z.area_hectares)} ha` : "—"],
          ["Last update", fmtDate(z.fetched_at_utc)],
        ]}
      />
      <Attribution>BC Emergency Management Climate Readiness</Attribution>
    </div>
  );
}

// ─── FWI ────────────────────────────────────────────────────────────

function FwiDetail({ id }: { id: string }) {
  const { data } = useFwiToday();
  const s = useMemo<FwiStation | undefined>(
    () => data?.find((x) => x.station_id === id || x.station_name === id),
    [data, id],
  );
  if (!s) return <Empty label="Station not found" />;

  return (
    <div>
      <Title>{s.station_name}</Title>
      <Subtitle>Fire Weather Index · {fmtDate(s.observation_date_local)}</Subtitle>
      <Stats
        rows={[
          ["FFMC", fmt(s.ffmc)],
          ["DMC", fmt(s.dmc)],
          ["DC", fmt(s.dc)],
          ["ISI", fmt(s.isi)],
          ["BUI", fmt(s.bui)],
          ["FWI", fmt(s.fwi)],
          ["DSR", fmt(s.dsr)],
          ["—", ""],
          ["Temp", s.temp_c != null ? `${fmt(s.temp_c)} °C` : "—"],
          ["RH", s.rh_pct != null ? `${fmt(s.rh_pct)} %` : "—"],
          ["Wind", s.wind_kmh != null ? `${fmt(s.wind_kmh)} km/h` : "—"],
          ["Precip", s.precip_mm != null ? `${fmt(s.precip_mm)} mm` : "—"],
        ]}
      />
      <Attribution>Natural Resources Canada · CWFIS</Attribution>
    </div>
  );
}

// ─── Shared primitives ──────────────────────────────────────────────

function Title({ children }: { children: React.ReactNode }) {
  return (
    <h2
      style={{
        fontFamily: "var(--font-display)",
        fontSize: 22,
        fontWeight: 700,
        letterSpacing: "-0.02em",
        margin: 0,
        color: "var(--color-text-hi)",
        lineHeight: 1.15,
      }}
    >
      {children}
    </h2>
  );
}

function Subtitle({
  children,
  style,
}: {
  children: React.ReactNode;
  style?: React.CSSProperties;
}) {
  return (
    <div
      style={{
        marginTop: 6,
        fontFamily: "var(--font-data)",
        fontSize: 11,
        letterSpacing: "0.22em",
        textTransform: "uppercase",
        color: "var(--color-text-mid)",
        ...style,
      }}
    >
      {children}
    </div>
  );
}

function Stats({ rows }: { rows: Array<[string, string | number | null | undefined]> }) {
  return (
    <dl
      style={{
        marginTop: 22,
        display: "grid",
        gridTemplateColumns: "100px 1fr",
        rowGap: 8,
        columnGap: 16,
        fontFamily: "var(--font-body)",
        fontSize: 13,
      }}
    >
      {rows.map(([k, v], i) => {
        const isSep = k === "—" && v === "";
        return (
          <div
            key={`${i}-${k}`}
            style={{
              display: "contents",
            }}
          >
            {isSep ? (
              <div
                style={{
                  gridColumn: "1 / -1",
                  height: 1,
                  background: "var(--color-stroke)",
                  margin: "8px 0",
                }}
              />
            ) : (
              <>
                <dt
                  style={{
                    color: "var(--color-text-low)",
                    fontFamily: "var(--font-data)",
                    fontSize: 10,
                    letterSpacing: "0.18em",
                    textTransform: "uppercase",
                    alignSelf: "center",
                  }}
                >
                  {k}
                </dt>
                <dd
                  className="tabular"
                  style={{
                    margin: 0,
                    color: "var(--color-text-hi)",
                  }}
                >
                  {v ?? "—"}
                </dd>
              </>
            )}
          </div>
        );
      })}
    </dl>
  );
}

function Attribution({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        marginTop: 28,
        paddingTop: 16,
        borderTop: "1px solid var(--color-stroke)",
        fontFamily: "var(--font-data)",
        fontSize: 10,
        letterSpacing: "0.18em",
        textTransform: "uppercase",
        color: "var(--color-text-low)",
      }}
    >
      {children}
    </div>
  );
}

function Empty({ label }: { label: string }) {
  return (
    <div style={{ color: "var(--color-text-low)", fontFamily: "var(--font-body)", fontSize: 13 }}>
      {label}
    </div>
  );
}

function fmt(n: number | null | undefined, decimals = 1): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1000) return n.toFixed(0);
  return n.toFixed(decimals);
}

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "America/Vancouver",
  }).format(d);
}
