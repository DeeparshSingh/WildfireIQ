/**
 * Three-step inline wizard. Captures the user's neighbourhood, situation,
 * and notification prefs in < 60 s. Persists to localStorage on completion.
 */
import { useState } from "react";

import { useNeighbourhoods, type NeighbourhoodFeature } from "@/lib/api/hooks";

import {
  SITUATION_OPTIONS,
  type Dwelling,
  type PrepProfile,
  type Season,
  type SituationId,
  requestNotificationPermission,
} from "./state";

const KAMLOOPS_LAT = 50.6745;
const KAMLOOPS_LON = -120.3273;

export function OnboardingWizard({
  onComplete,
}: {
  onComplete: (p: PrepProfile) => void;
}) {
  const [step, setStep] = useState(0);
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<NeighbourhoodFeature | null>(null);
  const [dwelling, setDwelling] = useState<Dwelling>("house");
  const [situation, setSituation] = useState<SituationId[]>([]);
  const [aqhiThreshold, setAqhiThreshold] = useState(7);
  const [evacAlerts, setEvacAlerts] = useState(true);

  const neighbourhoods = useNeighbourhoods();
  const matches =
    query.length === 0
      ? neighbourhoods.data ?? []
      : (neighbourhoods.data ?? []).filter((n) =>
          n.properties.name.toLowerCase().includes(query.toLowerCase()),
        );

  const inferredSeason: Season = (() => {
    const m = new Date().getMonth() + 1;
    if (m >= 3 && m <= 5) return "spring";
    if (m >= 6 && m <= 8) return "summer";
    if (m >= 9 && m <= 11) return "fall";
    return "any";
  })();

  const finish = async () => {
    if (evacAlerts) await requestNotificationPermission();
    onComplete({
      version: "1",
      neighbourhood: selected?.properties.name ?? null,
      neighbourhoodLat: selected?.properties.centroid_lat ?? KAMLOOPS_LAT,
      neighbourhoodLon: selected?.properties.centroid_lon ?? KAMLOOPS_LON,
      dwelling,
      season: inferredSeason,
      situation,
      notify: { aqhiThreshold, evacAlerts },
      createdAt: new Date().toISOString(),
    });
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        pointerEvents: "auto",
        padding: "48px 24px 80px",
        background:
          "radial-gradient(ellipse at top, hsl(220 25% 6% / 0.92), hsl(220 30% 2% / 0.96) 80%)",
      }}
    >
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <header style={{ marginBottom: 32 }}>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--color-cyan-glow)",
            }}
          >
            Welcome
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
            Let's tailor your <em style={{ color: "var(--color-cyan-glow)", fontStyle: "normal" }}>FireSmart Hub</em>.
          </h1>
          <p
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 14,
              lineHeight: 1.6,
              color: "var(--color-text-mid)",
              marginTop: 12,
              maxWidth: 560,
            }}
          >
            Three quick questions. Nothing is sent anywhere — your answers
            live in this browser only. You can change them later.
          </p>
        </header>

        <Stepper step={step} />

        <section
          className="glass-strong"
          style={{
            padding: 28,
            borderRadius: "var(--radius-lg)",
            marginTop: 16,
          }}
        >
          {step === 0 && (
            <div style={{ display: "grid", gap: 16 }}>
              <h2 style={h2Style}>Pick your neighbourhood</h2>
              <p style={subStyle}>
                Used to map evacuation zones and to fly the globe view to
                your area. Choose any if you're elsewhere in the
                Thompson-Okanagan — the live data still works.
              </p>
              <input
                type="search"
                placeholder="Start typing… (e.g. Aberdeen, Sahali, Westsyde)"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                style={inputStyle}
              />
              <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "grid", gap: 6, maxHeight: 240, overflowY: "auto" }}>
                {matches.map((n) => {
                  const isSel = selected?.properties.name === n.properties.name;
                  return (
                    <li key={n.properties.name}>
                      <button
                        type="button"
                        onClick={() => setSelected(n)}
                        style={{
                          width: "100%",
                          textAlign: "left",
                          padding: "10px 14px",
                          background: isSel ? "hsl(200 80% 50% / 0.18)" : "hsl(220 30% 10% / 0.6)",
                          border: `1px solid ${
                            isSel ? "hsl(200 80% 50% / 0.5)" : "hsl(200 80% 50% / 0.15)"
                          }`,
                          borderRadius: 8,
                          color: "var(--color-text-hi)",
                          fontFamily: "var(--font-body)",
                          fontSize: 14,
                          cursor: "pointer",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                        }}
                      >
                        <span>{n.properties.name}</span>
                        <span style={{ fontFamily: "var(--font-data)", fontSize: 11, color: "var(--color-text-mid)" }}>
                          {n.properties.centroid_lat.toFixed(3)}, {n.properties.centroid_lon.toFixed(3)}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
              <div style={{ display: "flex", gap: 8 }}>
                <Select
                  label="Dwelling"
                  value={dwelling}
                  onChange={(v) => setDwelling(v as Dwelling)}
                  options={[
                    { value: "house", label: "Detached house" },
                    { value: "townhome", label: "Townhome / apartment" },
                    { value: "cabin", label: "Cabin / rural" },
                    { value: "mobile", label: "Mobile home" },
                  ]}
                />
              </div>
              <Footer
                back={null}
                next={() => setStep(1)}
                nextLabel="Continue"
              />
            </div>
          )}

          {step === 1 && (
            <div style={{ display: "grid", gap: 16 }}>
              <h2 style={h2Style}>Tell us your situation</h2>
              <p style={subStyle}>
                Multi-select. We use these to filter and re-order the
                checklist so you only see actions that apply to you. All
                optional.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                {SITUATION_OPTIONS.map((opt) => {
                  const on = situation.includes(opt.id);
                  return (
                    <button
                      key={opt.id}
                      type="button"
                      onClick={() =>
                        setSituation((cur) =>
                          on ? cur.filter((x) => x !== opt.id) : [...cur, opt.id],
                        )
                      }
                      style={{
                        padding: "10px 14px",
                        borderRadius: 999,
                        background: on ? "hsl(18 95% 54% / 0.18)" : "hsl(220 30% 10% / 0.6)",
                        border: `1px solid ${
                          on ? "hsl(18 95% 54% / 0.6)" : "hsl(200 80% 50% / 0.18)"
                        }`,
                        color: "var(--color-text-hi)",
                        fontFamily: "var(--font-body)",
                        fontSize: 13,
                        cursor: "pointer",
                      }}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
              <Footer back={() => setStep(0)} next={() => setStep(2)} nextLabel="Continue" />
            </div>
          )}

          {step === 2 && (
            <div style={{ display: "grid", gap: 16 }}>
              <h2 style={h2Style}>Notification preferences</h2>
              <p style={subStyle}>
                Browser Web Notifications, opt-in. We never push to a server
                — these fire from your browser when our refreshing data
                crosses a threshold.
              </p>

              <label style={{ display: "grid", gap: 8 }}>
                <span style={{ fontFamily: "var(--font-data)", fontSize: 11, letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--color-text-mid)" }}>
                  AQHI alert threshold · {aqhiThreshold}+
                </span>
                <input
                  type="range"
                  min={4}
                  max={10}
                  value={aqhiThreshold}
                  onChange={(e) => setAqhiThreshold(parseInt(e.target.value, 10))}
                  style={{ accentColor: "hsl(18 95% 54%)" }}
                />
              </label>

              <label style={{ display: "flex", gap: 10, alignItems: "center", cursor: "pointer" }}>
                <input
                  type="checkbox"
                  checked={evacAlerts}
                  onChange={(e) => setEvacAlerts(e.target.checked)}
                  style={{ accentColor: "hsl(0 80% 55%)", width: 18, height: 18 }}
                />
                <span style={{ fontFamily: "var(--font-body)", fontSize: 14, color: "var(--color-text-hi)" }}>
                  Notify me if my neighbourhood enters an evacuation Alert or Order
                </span>
              </label>

              <Footer back={() => setStep(1)} next={finish} nextLabel="Open my hub" />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Stepper({ step }: { step: number }) {
  return (
    <div style={{ display: "flex", gap: 8 }}>
      {[0, 1, 2].map((i) => (
        <div
          key={i}
          style={{
            flex: 1,
            height: 4,
            background: i <= step ? "hsl(18 95% 54%)" : "hsl(220 30% 14%)",
            borderRadius: 4,
            transition: "background 0.3s",
          }}
        />
      ))}
    </div>
  );
}

function Footer({
  back,
  next,
  nextLabel,
}: {
  back: (() => void) | null;
  next: () => void;
  nextLabel: string;
}) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
      <button
        type="button"
        onClick={back ?? undefined}
        disabled={!back}
        style={{
          padding: "10px 18px",
          background: "transparent",
          color: "var(--color-text-mid)",
          border: "1px solid hsl(200 80% 50% / 0.2)",
          borderRadius: 8,
          fontFamily: "var(--font-body)",
          fontSize: 13,
          cursor: back ? "pointer" : "default",
          opacity: back ? 1 : 0.3,
        }}
      >
        Back
      </button>
      <button
        type="button"
        onClick={next}
        style={{
          padding: "10px 22px",
          background: "hsl(18 95% 54%)",
          color: "white",
          border: "none",
          borderRadius: 8,
          fontFamily: "var(--font-body)",
          fontSize: 13,
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        {nextLabel} →
      </button>
    </div>
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
      <span style={{ fontFamily: "var(--font-data)", fontSize: 10, letterSpacing: "0.18em", textTransform: "uppercase", color: "var(--color-text-mid)" }}>
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
          minWidth: 200,
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

const h2Style: React.CSSProperties = {
  fontFamily: "var(--font-display)",
  fontSize: 22,
  fontWeight: 600,
  color: "var(--color-text-hi)",
  margin: 0,
};
const subStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: 13,
  lineHeight: 1.55,
  color: "var(--color-text-mid)",
  margin: 0,
};
const inputStyle: React.CSSProperties = {
  background: "hsl(220 30% 8% / 0.85)",
  color: "var(--color-text-hi)",
  border: "1px solid hsl(200 80% 50% / 0.2)",
  borderRadius: 8,
  padding: "10px 14px",
  fontFamily: "var(--font-body)",
  fontSize: 14,
};
