/**
 * /about — what the platform is, where its data comes from, what it can and
 * cannot tell you, and how to cite it.
 *
 * Attribution is a licensing obligation for several upstream feeds (Cesium
 * Ion, NASA FIRMS, WAQI, Open-Meteo), so the source table here is part of
 * the product rather than decoration.
 */
import type { ReactNode } from "react";

const APP_VERSION = "1.0.0";

type Source = { name: string; used: string; terms: string };

const SOURCES: Source[] = [
  {
    name: "BC Wildfire Service (DataBC)",
    used: "Active fires and the 1999-onward historical record",
    terms: "Open Government Licence, British Columbia",
  },
  {
    name: "NASA FIRMS (VIIRS, MODIS)",
    used: "Satellite heat detections, last 72 hours",
    terms: "Free public use, attribution required",
  },
  {
    name: "BC Emergency Management Climate Readiness",
    used: "Evacuation orders, alerts, and rescinds",
    terms: "Open data",
  },
  {
    name: "Environment and Climate Change Canada",
    used: "Air Quality Health Index and the RAQDPS-FW smoke forecast",
    terms: "Open Government Licence, Canada",
  },
  {
    name: "Open-Meteo",
    used: "Weather, ERA5 reanalysis history, and CAMS air quality",
    terms: "CC-BY 4.0",
  },
  {
    name: "Natural Resources Canada CWFIS",
    used: "Fire Weather Index, when the service is reachable",
    terms: "Open public access",
  },
  {
    name: "World Air Quality Index (WAQI)",
    used: "Pollutant breakdown for Kamloops",
    terms: "Free with API token, attribution required",
  },
  {
    name: "ClimateData.ca",
    used: "CMIP6 projection structure",
    terms: "Open Government Licence, Canada",
  },
  {
    name: "Cesium Ion, OpenStreetMap",
    used: "Globe terrain, imagery, and building tiles",
    terms: "Free tier, attribution required",
  },
];

const LIMITS: string[] = [
  "The risk grid is a planning aid, not a warning. Within an area, differences between hexagons come from that spot's fire history rather than separate local weather.",
  "Air quality forecasting covers a single point (Kamloops). It cannot see smoke arriving from outside the region until local readings begin to rise.",
  "The climate projections are a placeholder with the correct shape, not the live ClimateData.ca download. The page says so where it matters.",
  "A satellite heat detection is a signal worth investigating, not a confirmed fire.",
];

export function AboutView() {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        pointerEvents: "auto",
        padding: "32px 32px 80px",
        background:
          "radial-gradient(ellipse at top, hsl(220 25% 6% / 0.92), hsl(220 30% 2% / 0.96) 80%)",
      }}
    >
      <div style={{ maxWidth: 860, margin: "0 auto" }}>
        <header style={{ paddingBottom: 24, borderBottom: "1px solid var(--color-stroke)" }}>
          <Kicker>About this platform</Kicker>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(2rem, 4vw, 2.9rem)",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              margin: "10px 0 0",
              color: "var(--color-text-hi)",
              lineHeight: 1.05,
            }}
          >
            WildfireIQ Kamloops
          </h1>
          <p
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 15,
              lineHeight: 1.65,
              color: "var(--color-text-mid)",
              margin: "14px 0 0",
            }}
          >
            Wildfire risk, air quality, and community preparedness for the
            Thompson-Okanagan region of British Columbia, built from public
            data. Created by Deeparsh Singh Dang at Thompson Rivers University
            with support from the TRU Sustainability Research Grant for
            Students, 2025-2026.
          </p>
          <div
            style={{
              display: "flex",
              gap: 10,
              flexWrap: "wrap",
              marginTop: 18,
              fontFamily: "var(--font-data)",
              fontSize: 11,
            }}
          >
            <Pill>Version {APP_VERSION}</Pill>
            <Pill>MIT licensed code</Pill>
            <Pill>CC-BY-4.0 content</Pill>
            <Pill>No personal data stored</Pill>
          </div>
        </header>

        <Section title="What it does">
          <Grid>
            <Card
              heading="Live map"
              body="Fires, satellite heat detections, evacuation zones, fire-weather stations, and an hour-by-hour smoke forecast across British Columbia."
            />
            <Card
              heading="AI risk grid"
              body="A daily wildfire-risk estimate for four areas: Thompson-Okanagan, Central Okanagan, the Lower Mainland, and Prince George. Each is scored on its own local weather."
            />
            <Card
              heading="Air quality"
              body="Live Air Quality Health Index, a 48-hour forecast with an honest uncertainty band, a pollutant breakdown, and a year of smoke history."
            />
            <Card
              heading="Preparedness"
              body="A FireSmart checklist tailored to your home and season, a live evacuation check, and progress tracking that never leaves your device."
            />
          </Grid>
        </Section>

        <Section title="How the models were tested">
          <p style={pStyle}>
            Both models were trained on records up to 2021 and then evaluated
            on the 2022 and 2023 fire seasons, which were held out of training
            entirely. On the unseen 2023 season the wildfire risk model reaches
            a precision-recall score of 0.72 in the Thompson-Okanagan and 0.61
            in Prince George, ahead of the conventional Fire Weather Index
            threshold method at 0.37. The air quality forecaster beats a
            &ldquo;tomorrow equals today&rdquo; baseline at the 6, 12, 36, and
            48-hour horizons. Full training data, method, and known failure
            modes are published in the model cards that ship with the code.
          </p>
        </Section>

        <Section title="What it cannot tell you">
          <ul style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 10 }}>
            {LIMITS.map((l) => (
              <li key={l} style={{ ...pStyle, margin: 0 }}>
                {l}
              </li>
            ))}
          </ul>
          <Callout>
            Always follow the BC Wildfire Service and BC Emergency Management
            Climate Readiness for official direction. This platform is
            informational and does not replace them.
          </Callout>
        </Section>

        <Section title="Data sources and attribution">
          <div
            style={{
              border: "1px solid var(--color-stroke)",
              borderRadius: "var(--radius-lg)",
              overflow: "hidden",
            }}
          >
            {SOURCES.map((s, i) => (
              <div
                key={s.name}
                style={{
                  display: "grid",
                  gridTemplateColumns: "minmax(190px, 1fr) 1.5fr",
                  gap: 16,
                  padding: "14px 18px",
                  borderTop: i === 0 ? "none" : "1px solid var(--color-stroke)",
                  background: i % 2 ? "transparent" : "hsl(220 28% 10% / 0.4)",
                }}
              >
                <div>
                  <div
                    style={{
                      fontFamily: "var(--font-body)",
                      fontSize: 13.5,
                      fontWeight: 500,
                      color: "var(--color-text-hi)",
                    }}
                  >
                    {s.name}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--font-data)",
                      fontSize: 10.5,
                      color: "var(--color-text-low)",
                      marginTop: 4,
                      letterSpacing: "0.04em",
                    }}
                  >
                    {s.terms}
                  </div>
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-body)",
                    fontSize: 12.5,
                    lineHeight: 1.55,
                    color: "var(--color-text-mid)",
                  }}
                >
                  {s.used}
                </div>
              </div>
            ))}
          </div>
        </Section>

        <Section title="Privacy">
          <p style={pStyle}>
            There are no accounts and no analytics. The preparedness hub keeps
            your neighbourhood, checklist progress, and any photos you attach
            in your own browser, using local storage and IndexedDB. Photos
            never leave your device. The one thing sent to the backend is a
            coordinate pair, used only to test whether that point falls inside
            an active evacuation polygon; it is not stored or logged against
            any identifier.
          </p>
        </Section>

        <footer
          style={{
            marginTop: 40,
            paddingTop: 20,
            borderTop: "1px solid var(--color-stroke)",
            fontFamily: "var(--font-data)",
            fontSize: 11,
            lineHeight: 1.7,
            color: "var(--color-text-low)",
          }}
        >
          To cite this work, see CITATION.cff in the repository. Engineering
          notes, the per-layer data reference, the data dictionary, and both
          model cards live in the documents folder alongside the code.
        </footer>
      </div>
    </div>
  );
}

// ─── Small presentational helpers ─────────────────────────────────────

const pStyle: React.CSSProperties = {
  fontFamily: "var(--font-body)",
  fontSize: 14,
  lineHeight: 1.7,
  color: "var(--color-text-mid)",
  margin: 0,
};

function Kicker({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "var(--font-data)",
        fontSize: 11,
        letterSpacing: "0.28em",
        textTransform: "uppercase",
        color: "var(--color-cyan-glow)",
      }}
    >
      {children}
    </div>
  );
}

function Pill({ children }: { children: ReactNode }) {
  return (
    <span
      style={{
        padding: "5px 12px",
        borderRadius: "var(--radius-pill)",
        border: "1px solid var(--color-stroke-strong)",
        color: "var(--color-text-mid)",
        letterSpacing: "0.06em",
      }}
    >
      {children}
    </span>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section style={{ marginTop: 36 }}>
      <h2
        style={{
          fontFamily: "var(--font-display)",
          fontSize: 20,
          fontWeight: 600,
          color: "var(--color-text-hi)",
          margin: "0 0 14px",
        }}
      >
        {title}
      </h2>
      {children}
    </section>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
        gap: 12,
      }}
    >
      {children}
    </div>
  );
}

function Card({ heading, body }: { heading: string; body: string }) {
  return (
    <div
      style={{
        padding: "16px 18px",
        borderRadius: "var(--radius-lg)",
        border: "1px solid var(--color-stroke)",
        background: "hsl(220 28% 10% / 0.5)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 14,
          fontWeight: 600,
          color: "var(--color-text-hi)",
        }}
      >
        {heading}
      </div>
      <div
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 12.5,
          lineHeight: 1.6,
          color: "var(--color-text-mid)",
          marginTop: 6,
        }}
      >
        {body}
      </div>
    </div>
  );
}

function Callout({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        marginTop: 16,
        padding: "14px 18px",
        borderRadius: "var(--radius-lg)",
        border: "1px dashed hsl(18 95% 54% / 0.4)",
        background: "hsl(18 95% 54% / 0.06)",
        fontFamily: "var(--font-body)",
        fontSize: 13,
        lineHeight: 1.6,
        color: "var(--color-text-hi)",
      }}
    >
      {children}
    </div>
  );
}
