/**
 * /preparedness — Community Preparedness Hub (Phase 5).
 *
 * Entirely local-first. No accounts, no PII ever leaves the device:
 *   • Situation (dwelling type, season, coordinates) → localStorage
 *   • Completed checklist items → localStorage (`wfiq.firesmart.completed`)
 *   • Points + badges derived on the client; backend `/score` exists only as
 *     a consistency oracle if/when we want to share the ladder.
 *
 * The one network call besides the checklist itself is `/api/evac/check`,
 * which sends lat/lon (no name, no address) so we can answer "am I currently
 * inside an active evac order or alert polygon?"
 */
import { useEffect, useMemo, useState } from "react";

import {
  useEvacCheck,
  useFireSmartChecklist,
  type FireSmartItem,
  type FireSmartZone,
} from "@/lib/api/hooks";

const KAMLOOPS = { lat: 50.6745, lon: -120.3273 };
const STORAGE_KEY = "wfiq.firesmart.v1";

type Situation = {
  dwelling: "house" | "townhome" | "cabin" | "mobile";
  season: "any" | "spring" | "summer" | "fall";
  lat: number;
  lon: number;
  locationLabel: string;
};

type Persisted = Situation & { completed: string[] };

const DEFAULT: Persisted = {
  dwelling: "house",
  season: "summer",
  lat: KAMLOOPS.lat,
  lon: KAMLOOPS.lon,
  locationLabel: "Kamloops (default)",
  completed: [],
};

function loadState(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT;
    const parsed = JSON.parse(raw);
    return { ...DEFAULT, ...parsed };
  } catch {
    return DEFAULT;
  }
}

function saveState(s: Persisted) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    // localStorage may be unavailable in privacy modes — silently ignore
  }
}

function badgesFor(points: number, completed: number, total: number) {
  const out: { id: string; label: string; emoji: string }[] = [];
  if (completed >= 1) out.push({ id: "started", label: "Got Started", emoji: "🌱" });
  if (completed >= 5) out.push({ id: "ember_aware", label: "Ember-Aware", emoji: "🪵" });
  if (points >= 25) out.push({ id: "defensible", label: "Defensible Space", emoji: "🛡️" });
  if (total > 0 && completed / total >= 0.5)
    out.push({ id: "halfway", label: "Halfway There", emoji: "🚧" });
  if (total > 0 && completed === total)
    out.push({ id: "firesmart_home", label: "FireSmart Home", emoji: "🏆" });
  return out;
}

export function PreparednessRoute() {
  const [state, setState] = useState<Persisted>(() => loadState());
  useEffect(() => saveState(state), [state]);

  const { dwelling, season, lat, lon, completed } = state;

  const checklist = useFireSmartChecklist(dwelling, season);
  const evac = useEvacCheck(lat, lon);

  const items = checklist.data?.items ?? [];
  const zones = checklist.data?.zones ?? [];

  const completedSet = useMemo(() => new Set(completed), [completed]);
  const stats = useMemo(() => {
    const total = items.length;
    const done = items.filter((i) => completedSet.has(i.id)).length;
    const pts = items
      .filter((i) => completedSet.has(i.id))
      .reduce((a, b) => a + b.points, 0);
    const maxPts = items.reduce((a, b) => a + b.points, 0);
    return { total, done, pts, maxPts };
  }, [items, completedSet]);

  const badges = badgesFor(stats.pts, stats.done, stats.total);

  const toggle = (id: string) =>
    setState((s) => {
      const set = new Set(s.completed);
      if (set.has(id)) set.delete(id);
      else set.add(id);
      return { ...s, completed: Array.from(set) };
    });

  const useGeolocation = () => {
    if (!("geolocation" in navigator)) return;
    navigator.geolocation.getCurrentPosition(
      (p) =>
        setState((s) => ({
          ...s,
          lat: +p.coords.latitude.toFixed(5),
          lon: +p.coords.longitude.toFixed(5),
          locationLabel: "My current location",
        })),
      () => undefined,
      { maximumAge: 60_000, timeout: 10_000 },
    );
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        pointerEvents: "auto",
        padding: "32px 48px 80px",
        background:
          "radial-gradient(ellipse at top, hsl(220 25% 6% / 0.92), hsl(220 30% 2% / 0.96) 80%)",
      }}
    >
      <div style={{ maxWidth: 1180, margin: "0 auto" }}>
        <Header dwelling={dwelling} season={season} setState={setState} />

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 360px",
            gap: 24,
            alignItems: "start",
            marginTop: 24,
          }}
        >
          <main style={{ display: "grid", gap: 24 }}>
            <ScorePanel
              stats={stats}
              badges={badges}
              onReset={() =>
                setState((s) => ({ ...s, completed: [] }))
              }
            />
            {zones.map((z) => (
              <ZoneCard
                key={z.id}
                zone={z}
                items={items.filter((i) => i.zone === z.id)}
                completed={completedSet}
                onToggle={toggle}
              />
            ))}
          </main>

          <aside style={{ display: "grid", gap: 16, position: "sticky", top: 24 }}>
            <LocationCard
              lat={lat}
              lon={lon}
              label={state.locationLabel}
              onUseKamloops={() =>
                setState((s) => ({
                  ...s,
                  lat: KAMLOOPS.lat,
                  lon: KAMLOOPS.lon,
                  locationLabel: "Kamloops (default)",
                }))
              }
              onUseGeo={useGeolocation}
              onChange={(la, lo) =>
                setState((s) => ({
                  ...s,
                  lat: la,
                  lon: lo,
                  locationLabel: "Custom coordinates",
                }))
              }
            />
            <EvacCard
              loading={evac.isLoading}
              status={evac.data?.status ?? null}
              matches={evac.data?.matches ?? []}
            />
            <PrivacyNote />
          </aside>
        </div>
      </div>
    </div>
  );
}

// ───────────────────────────────────────────────────────────────────────
// Sub-components
// ───────────────────────────────────────────────────────────────────────

function Header({
  dwelling,
  season,
  setState,
}: {
  dwelling: Situation["dwelling"];
  season: Situation["season"];
  setState: React.Dispatch<React.SetStateAction<Persisted>>;
}) {
  return (
    <header
      style={{
        display: "flex",
        alignItems: "flex-end",
        justifyContent: "space-between",
        gap: 24,
      }}
    >
      <div>
        <div
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 11,
            letterSpacing: "0.28em",
            textTransform: "uppercase",
            color: "var(--color-cyan-glow)",
          }}
        >
          Phase 5 · Community Preparedness Hub
        </div>
        <h1
          style={{
            fontFamily: "var(--font-display)",
            fontSize: "clamp(2rem, 3.6vw, 2.8rem)",
            fontWeight: 700,
            letterSpacing: "-0.03em",
            margin: "8px 0 0",
            color: "var(--color-text-hi)",
            lineHeight: 1.05,
          }}
        >
          Make your home <em style={{ color: "var(--color-cyan-glow)", fontStyle: "normal" }}>FireSmart</em>.
        </h1>
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 15,
            lineHeight: 1.55,
            color: "var(--color-text-mid)",
            margin: "12px 0 0",
            maxWidth: 640,
          }}
        >
          A personalised Home Ignition Zone checklist, sourced from{" "}
          <strong style={{ color: "var(--color-text-hi)" }}>FireSmart Canada</strong>.
          Tick items as you finish them — points and badges stay on this
          device only.
        </p>
      </div>

      <div style={{ display: "flex", gap: 12 }}>
        <Select
          label="Dwelling"
          value={dwelling}
          onChange={(v) =>
            setState((s) => ({ ...s, dwelling: v as Situation["dwelling"] }))
          }
          options={[
            { value: "house", label: "Detached house" },
            { value: "townhome", label: "Townhome" },
            { value: "cabin", label: "Cabin / rural" },
            { value: "mobile", label: "Mobile home" },
          ]}
        />
        <Select
          label="Season"
          value={season}
          onChange={(v) =>
            setState((s) => ({ ...s, season: v as Situation["season"] }))
          }
          options={[
            { value: "any", label: "All year" },
            { value: "spring", label: "Spring" },
            { value: "summer", label: "Summer" },
            { value: "fall", label: "Fall" },
          ]}
        />
      </div>
    </header>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <label style={{ display: "grid", gap: 4 }}>
      <span
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 10,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--color-text-mid)",
        }}
      >
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          background: "hsl(220 30% 8% / 0.85)",
          color: "var(--color-text-hi)",
          border: "1px solid hsl(200 80% 50% / 0.25)",
          borderRadius: 8,
          padding: "8px 12px",
          fontFamily: "var(--font-body)",
          fontSize: 13,
          minWidth: 160,
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}

function ScorePanel({
  stats,
  badges,
  onReset,
}: {
  stats: { total: number; done: number; pts: number; maxPts: number };
  badges: { id: string; label: string; emoji: string }[];
  onReset: () => void;
}) {
  const pct =
    stats.maxPts > 0 ? Math.round((stats.pts / stats.maxPts) * 100) : 0;
  return (
    <section
      className="glass-strong"
      style={{
        padding: 24,
        borderRadius: "var(--radius-lg)",
        display: "grid",
        gap: 16,
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--color-text-mid)",
            }}
          >
            Your FireSmart Score
          </div>
          <div
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 36,
              fontWeight: 700,
              color: "var(--color-text-hi)",
              lineHeight: 1,
              marginTop: 6,
            }}
          >
            {stats.pts}{" "}
            <span
              style={{
                fontSize: 16,
                color: "var(--color-text-mid)",
                fontWeight: 400,
              }}
            >
              / {stats.maxPts} pts
            </span>
          </div>
          <div
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 13,
              color: "var(--color-text-mid)",
              marginTop: 4,
            }}
          >
            {stats.done} of {stats.total} actions complete ({pct}%)
          </div>
        </div>
        <button
          type="button"
          onClick={onReset}
          style={{
            background: "transparent",
            color: "var(--color-text-mid)",
            border: "1px solid hsl(200 80% 50% / 0.2)",
            borderRadius: 8,
            padding: "6px 12px",
            fontSize: 12,
            cursor: "pointer",
            fontFamily: "var(--font-body)",
          }}
        >
          Reset progress
        </button>
      </div>

      <div
        style={{
          height: 8,
          background: "hsl(220 30% 12%)",
          borderRadius: 8,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background:
              "linear-gradient(90deg, hsl(150 70% 50%), hsl(180 75% 55%), hsl(200 90% 60%))",
            transition: "width 0.3s ease",
          }}
        />
      </div>

      {badges.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {badges.map((b) => (
            <span
              key={b.id}
              style={{
                padding: "6px 10px",
                borderRadius: 999,
                background: "hsl(200 80% 50% / 0.12)",
                border: "1px solid hsl(200 80% 50% / 0.3)",
                fontSize: 12,
                fontFamily: "var(--font-body)",
                color: "var(--color-text-hi)",
                display: "inline-flex",
                gap: 6,
                alignItems: "center",
              }}
            >
              <span>{b.emoji}</span>
              <span>{b.label}</span>
            </span>
          ))}
        </div>
      )}
    </section>
  );
}

function ZoneCard({
  zone,
  items,
  completed,
  onToggle,
}: {
  zone: FireSmartZone;
  items: FireSmartItem[];
  completed: Set<string>;
  onToggle: (id: string) => void;
}) {
  if (items.length === 0) return null;
  const done = items.filter((i) => completed.has(i.id)).length;
  return (
    <section
      className="glass"
      style={{
        padding: 20,
        borderRadius: "var(--radius-lg)",
        display: "grid",
        gap: 12,
      }}
    >
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <div>
          <h2
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 20,
              fontWeight: 600,
              color: "var(--color-text-hi)",
              margin: 0,
            }}
          >
            {zone.label}
          </h2>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--color-cyan-glow)",
              marginTop: 4,
            }}
          >
            {zone.distance}
          </div>
        </div>
        <span
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 12,
            color: "var(--color-text-mid)",
          }}
        >
          {done} / {items.length}
        </span>
      </header>
      <p
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 13,
          lineHeight: 1.5,
          color: "var(--color-text-mid)",
          margin: 0,
        }}
      >
        {zone.blurb}
      </p>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "grid",
          gap: 8,
        }}
      >
        {items.map((i) => {
          const isDone = completed.has(i.id);
          return (
            <li key={i.id}>
              <button
                type="button"
                onClick={() => onToggle(i.id)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  display: "grid",
                  gridTemplateColumns: "auto 1fr auto",
                  gap: 12,
                  alignItems: "start",
                  padding: "12px 14px",
                  borderRadius: 10,
                  background: isDone
                    ? "hsl(150 60% 40% / 0.12)"
                    : "hsl(220 30% 10% / 0.6)",
                  border: `1px solid ${
                    isDone ? "hsl(150 70% 50% / 0.4)" : "hsl(200 80% 50% / 0.15)"
                  }`,
                  cursor: "pointer",
                  fontFamily: "var(--font-body)",
                  color: "var(--color-text-hi)",
                }}
              >
                <span
                  aria-hidden
                  style={{
                    width: 20,
                    height: 20,
                    borderRadius: 6,
                    border: `1.5px solid ${
                      isDone ? "hsl(150 70% 60%)" : "hsl(200 50% 60% / 0.5)"
                    }`,
                    background: isDone ? "hsl(150 70% 50%)" : "transparent",
                    display: "grid",
                    placeItems: "center",
                    color: "white",
                    fontSize: 14,
                    fontWeight: 700,
                    marginTop: 2,
                  }}
                >
                  {isDone ? "✓" : ""}
                </span>
                <span>
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 500,
                      textDecoration: isDone ? "line-through" : "none",
                      color: isDone ? "var(--color-text-mid)" : "var(--color-text-hi)",
                    }}
                  >
                    {i.title}
                  </div>
                  <div
                    style={{
                      fontSize: 12,
                      lineHeight: 1.5,
                      color: "var(--color-text-mid)",
                      marginTop: 4,
                    }}
                  >
                    {i.detail}
                  </div>
                </span>
                <span
                  style={{
                    fontFamily: "var(--font-data)",
                    fontSize: 11,
                    color: "var(--color-cyan-glow)",
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: "hsl(200 80% 50% / 0.1)",
                    border: "1px solid hsl(200 80% 50% / 0.2)",
                    whiteSpace: "nowrap",
                  }}
                >
                  +{i.points} pts
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function LocationCard({
  lat,
  lon,
  label,
  onUseKamloops,
  onUseGeo,
  onChange,
}: {
  lat: number;
  lon: number;
  label: string;
  onUseKamloops: () => void;
  onUseGeo: () => void;
  onChange: (lat: number, lon: number) => void;
}) {
  const [draftLat, setDraftLat] = useState(String(lat));
  const [draftLon, setDraftLon] = useState(String(lon));
  useEffect(() => {
    setDraftLat(String(lat));
    setDraftLon(String(lon));
  }, [lat, lon]);
  return (
    <section
      className="glass"
      style={{
        padding: 16,
        borderRadius: "var(--radius-lg)",
        display: "grid",
        gap: 10,
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 11,
          letterSpacing: "0.24em",
          textTransform: "uppercase",
          color: "var(--color-text-mid)",
        }}
      >
        Location · {label}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <input
          aria-label="Latitude"
          value={draftLat}
          onChange={(e) => setDraftLat(e.target.value)}
          onBlur={() => {
            const la = parseFloat(draftLat);
            const lo = parseFloat(draftLon);
            if (Number.isFinite(la) && Number.isFinite(lo)) onChange(la, lo);
          }}
          style={inputStyle}
        />
        <input
          aria-label="Longitude"
          value={draftLon}
          onChange={(e) => setDraftLon(e.target.value)}
          onBlur={() => {
            const la = parseFloat(draftLat);
            const lo = parseFloat(draftLon);
            if (Number.isFinite(la) && Number.isFinite(lo)) onChange(la, lo);
          }}
          style={inputStyle}
        />
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button type="button" onClick={onUseGeo} style={pillButton}>
          Use my location
        </button>
        <button type="button" onClick={onUseKamloops} style={pillButton}>
          Kamloops default
        </button>
      </div>
    </section>
  );
}

function EvacCard({
  loading,
  status,
  matches,
}: {
  loading: boolean;
  status: "clear" | "alert" | "order" | null;
  matches: { event_name?: string | null; issuing_agency?: string | null }[];
}) {
  const tone =
    status === "order"
      ? { bg: "hsl(0 70% 45% / 0.18)", border: "hsl(0 80% 55%)", text: "Evacuation ORDER", emoji: "🚨" }
      : status === "alert"
      ? { bg: "hsl(35 90% 50% / 0.18)", border: "hsl(35 90% 55%)", text: "Evacuation ALERT", emoji: "⚠️" }
      : { bg: "hsl(150 60% 40% / 0.15)", border: "hsl(150 70% 50%)", text: "No active orders or alerts", emoji: "✅" };

  return (
    <section
      className="glass"
      style={{
        padding: 16,
        borderRadius: "var(--radius-lg)",
        display: "grid",
        gap: 10,
        background: tone.bg,
        border: `1px solid ${tone.border}`,
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 11,
          letterSpacing: "0.24em",
          textTransform: "uppercase",
          color: "var(--color-text-mid)",
        }}
      >
        Live evac check
      </div>
      <div
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 18,
          fontWeight: 600,
          color: "var(--color-text-hi)",
          display: "flex",
          gap: 8,
          alignItems: "center",
        }}
      >
        <span>{tone.emoji}</span>
        <span>{loading ? "Checking…" : tone.text}</span>
      </div>
      {matches.length > 0 && (
        <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 4 }}>
          {matches.map((m, idx) => (
            <li
              key={idx}
              style={{
                fontFamily: "var(--font-body)",
                fontSize: 12,
                color: "var(--color-text-mid)",
              }}
            >
              · {m.event_name ?? "Unnamed event"} — {m.issuing_agency ?? "BC EMCR"}
            </li>
          ))}
        </ul>
      )}
      <div
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 11,
          color: "var(--color-text-mid)",
          lineHeight: 1.5,
        }}
      >
        Point-in-polygon check against active BC Emergency Management orders
        and alerts. Refreshes every 60 s. Informational only — follow BCEM
        and BC Wildfire Service for official direction.
      </div>
    </section>
  );
}

function PrivacyNote() {
  return (
    <section
      style={{
        padding: 14,
        borderRadius: "var(--radius-lg)",
        background: "hsl(220 30% 8% / 0.4)",
        border: "1px dashed hsl(200 80% 50% / 0.2)",
        fontFamily: "var(--font-body)",
        fontSize: 11,
        lineHeight: 1.6,
        color: "var(--color-text-mid)",
      }}
    >
      <strong style={{ color: "var(--color-text-hi)" }}>Private by design.</strong>{" "}
      Your dwelling type, season, and checklist progress live in this
      browser's localStorage only. Coordinates are sent to our backend solely
      to look up active evac polygons — they're not stored or logged with any
      identifier.
    </section>
  );
}

const inputStyle: React.CSSProperties = {
  background: "hsl(220 30% 8% / 0.85)",
  color: "var(--color-text-hi)",
  border: "1px solid hsl(200 80% 50% / 0.2)",
  borderRadius: 8,
  padding: "8px 10px",
  fontFamily: "var(--font-data)",
  fontSize: 12,
  width: "100%",
};

const pillButton: React.CSSProperties = {
  flex: 1,
  background: "hsl(200 80% 50% / 0.1)",
  color: "var(--color-text-hi)",
  border: "1px solid hsl(200 80% 50% / 0.3)",
  borderRadius: 8,
  padding: "8px 12px",
  fontSize: 12,
  fontFamily: "var(--font-body)",
  cursor: "pointer",
};
