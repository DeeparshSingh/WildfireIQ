/**
 * /air-quality — the AQ Monitor route.
 * Replaces the Phase 0 placeholder. Mounted via App's route map.
 *
 * Composition:
 *   ┌───────────────────────────────────────────┐
 *   │ [hero] AQHI dial + status + last update   │
 *   ├───────────────────────────────────────────┤
 *   │ [chart] 48h forecast q10–q90 + observed   │
 *   ├──────────────────────┬────────────────────┤
 *   │ [pollutants] 6 bars  │ [calendar] 90 days │
 *   ├──────────────────────┴────────────────────┤
 *   │ [guidance] health-band tabs + references  │
 *   └───────────────────────────────────────────┘
 */
import {
  useAqCalendar,
  useAqCurrent,
  useAqForecast,
  useHealthGuidance,
} from "@/lib/api/hooks";

import { AqhiDial } from "./AqhiDial";
import { ForecastChart } from "./ForecastChart";
import { HealthGuidance } from "./HealthGuidance";
import { PollutantBars } from "./PollutantBars";
import { SmokeCalendar } from "./SmokeCalendar";

function fmtTime(iso: string | undefined) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("en-CA", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
    timeZone: "America/Vancouver",
  }).format(d);
}

export function AirQualityRoute() {
  const current = useAqCurrent();
  const forecast = useAqForecast();
  const calendar = useAqCalendar(90);
  const guidance = useHealthGuidance();

  // Headline AQHI: use the highest-priority Kamloops station from GeoMet
  // (sorted observation_datetime_utc desc, dedupe per station via backend).
  const aqhi =
    current.data?.stations.find((s) =>
      s.station_name?.toLowerCase().includes("kamloops"),
    )?.aqhi ?? current.data?.stations[0]?.aqhi ?? null;

  const lastUpdated =
    current.data?.stations[0]?.observation_datetime_utc ?? undefined;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        pointerEvents: "auto",
        padding: "32px 48px 80px 48px",
        background:
          "radial-gradient(ellipse at top, hsl(220 25% 6% / 0.92), hsl(220 30% 2% / 0.96) 80%)",
      }}
    >
      <div style={{ maxWidth: 1280, margin: "0 auto" }}>
        <header
          style={{
            display: "flex",
            alignItems: "baseline",
            justifyContent: "space-between",
            marginBottom: 32,
          }}
        >
          <div>
            <div
              style={{
                fontFamily: "var(--font-data)",
                fontSize: 10,
                letterSpacing: "0.32em",
                textTransform: "uppercase",
                color: "var(--color-cyan-glow)",
                marginBottom: 8,
              }}
            >
              Air Quality Monitor · Kamloops
            </div>
            <h1
              style={{
                margin: 0,
                fontFamily: "var(--font-display)",
                fontSize: "clamp(2rem, 5vw, 3.2rem)",
                fontWeight: 700,
                letterSpacing: "-0.03em",
                color: "var(--color-text-hi)",
                lineHeight: 1.05,
              }}
            >
              Live AQHI + 48-hour PM2.5 forecast
            </h1>
          </div>
          <div
            className="tabular"
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--color-text-low)",
            }}
          >
            updated {fmtTime(lastUpdated)} YKA
          </div>
        </header>

        {/* Hero: dial */}
        <Card title="Current AQHI">
          {current.isLoading && <Skeleton h={280} />}
          {!current.isLoading && (
            <AqhiDial aqhi={aqhi} lastUpdated={fmtTime(lastUpdated)} />
          )}
        </Card>

        {/* Forecast chart */}
        <Card title="48-hour PM2.5 forecast (q10–q90 band)">
          {forecast.isLoading && <Skeleton h={280} />}
          {forecast.error && (
            <ErrorBox message={String(forecast.error)} />
          )}
          {forecast.data && <ForecastChart data={forecast.data} />}
          {forecast.data && (
            <div
              style={{
                marginTop: 16,
                paddingTop: 12,
                borderTop: "1px solid var(--color-stroke)",
                fontFamily: "var(--font-data)",
                fontSize: 10,
                letterSpacing: "0.16em",
                textTransform: "uppercase",
                color: "var(--color-text-low)",
              }}
            >
              Issued {fmtTime(forecast.data.issued_at_utc)} ·
              LightGBM quantile per horizon · trained on 92 days hourly
              Open-Meteo CAMS + co-located weather
            </div>
          )}
        </Card>

        {/* Two columns: pollutants + calendar */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(280px, 1fr) 2fr",
            gap: 24,
            alignItems: "stretch",
          }}
        >
          <Card title="Pollutant breakdown">
            {current.data?.pollutants ? (
              <PollutantBars pollutants={current.data.pollutants} />
            ) : (
              <Skeleton h={220} />
            )}
          </Card>

          <Card title="Smoke event calendar · 90 days">
            {calendar.data ? (
              <SmokeCalendar data={calendar.data} />
            ) : (
              <Skeleton h={120} />
            )}
          </Card>
        </div>

        {/* Health guidance */}
        <Card title="Health guidance">
          {guidance.data ? (
            <HealthGuidance guidance={guidance.data} currentAqhi={aqhi} />
          ) : (
            <Skeleton h={220} />
          )}
        </Card>

        <footer
          style={{
            marginTop: 24,
            paddingTop: 18,
            borderTop: "1px solid var(--color-stroke)",
            fontFamily: "var(--font-data)",
            fontSize: 10,
            letterSpacing: "0.14em",
            color: "var(--color-text-low)",
            lineHeight: 1.7,
          }}
        >
          Data sources: ECCC GeoMet AQHI · WAQI / AQICN pollutants · Open-Meteo CAMS
          European air-quality archive · Health Canada AQHI bands.
          <br />
          Informational only. In a wildfire smoke event, follow guidance from
          Interior Health and the BC Centre for Disease Control.
        </footer>
      </div>
    </div>
  );
}

function Card({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section
      className="glass"
      style={{
        marginBottom: 24,
        padding: "20px 24px",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-card)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 9,
          letterSpacing: "0.28em",
          textTransform: "uppercase",
          color: "var(--color-text-mid)",
          marginBottom: 16,
        }}
      >
        {title}
      </div>
      {children}
    </section>
  );
}

function Skeleton({ h }: { h: number }) {
  return (
    <div
      aria-hidden
      style={{
        height: h,
        borderRadius: 8,
        background: "linear-gradient(110deg, var(--color-bg-2), var(--color-bg-1), var(--color-bg-2))",
        backgroundSize: "200% 100%",
        animation: "shimmer 2s linear infinite",
      }}
    />
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div
      style={{
        padding: 16,
        border: "1px solid var(--risk-extreme)",
        borderRadius: 8,
        background: "color-mix(in oklab, var(--risk-extreme) 8%, transparent)",
        fontFamily: "var(--font-data)",
        fontSize: 12,
        color: "var(--color-text-hi)",
      }}
    >
      {message}
    </div>
  );
}
