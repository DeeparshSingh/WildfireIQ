/**
 * /climate — Climate Trend Module (Phase 6).
 *
 * A six-section scrollytelling page that opens with the historical record
 * and closes with projected fire-weather days. Each section is wrapped in
 * a `SectionShell` that fades in on scroll via IntersectionObserver. Print
 * stylesheet at the bottom produces a clean four-page PDF when the user
 * hits Cmd-P.
 */
import { Section1_AreaBurned } from "./Section1_AreaBurned";
import { Section2_Trends } from "./Section2_Trends";
import { Section3_Ribbon } from "./Section3_Ribbon";
import { Section4_Projections } from "./Section4_Projections";
import { Section5_FwiProjection } from "./Section5_FwiProjection";
import { Section6_TruCarbon } from "./Section6_TruCarbon";
import { TopoBackdrop } from "./TopoBackdrop";

export function ClimateRoute() {
  return (
    <div
      className="climate-root"
      style={{
        position: "absolute",
        inset: 0,
        overflowY: "auto",
        pointerEvents: "auto",
        background:
          "radial-gradient(ellipse at top, hsl(220 25% 6% / 0.92), hsl(220 30% 2% / 0.96) 80%)",
      }}
    >
      <TopoBackdrop />

      <div
        style={{
          position: "relative",
          maxWidth: 1180,
          margin: "0 auto",
          padding: "32px 32px 96px",
        }}
      >
        <header style={{ paddingBottom: 24, borderBottom: "1px solid hsl(220 15% 22%)" }}>
          <div
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 11,
              letterSpacing: "0.28em",
              textTransform: "uppercase",
              color: "var(--color-cyan-glow)",
            }}
          >
            Climate Trend Module
          </div>
          <h1
            style={{
              fontFamily: "var(--font-display)",
              fontSize: "clamp(2.2rem, 4.2vw, 3.4rem)",
              fontWeight: 700,
              letterSpacing: "-0.03em",
              margin: "10px 0 0",
              color: "var(--color-text-hi)",
              lineHeight: 1.02,
            }}
          >
            How the Thompson-Okanagan's <em style={{ color: "var(--color-ember-500, hsl(18 95% 54%))", fontStyle: "normal" }}>fire seasons</em> have changed — and where they're going.
          </h1>
          <p
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 15,
              lineHeight: 1.6,
              color: "var(--color-text-mid)",
              margin: "16px 0 0",
              maxWidth: 720,
            }}
          >
            Six sections built from BC Wildfire Service incident records,
            Open-Meteo ERA5 reanalysis weather, our Van Wagner FWI port, and
            the ClimateData.ca CMIP6 ensemble. Every chart has its source,
            method, and a CSV download under the (i) chip.
          </p>
        </header>

        <Section1_AreaBurned />
        <Section2_Trends />
        <Section3_Ribbon />
        <Section4_Projections />
        <Section5_FwiProjection />
        <Section6_TruCarbon />

        <footer
          style={{
            marginTop: 48,
            padding: 18,
            borderRadius: 12,
            border: "1px dashed hsl(200 80% 50% / 0.2)",
            background: "hsl(220 30% 8% / 0.4)",
            fontFamily: "var(--font-body)",
            fontSize: 12,
            lineHeight: 1.6,
            color: "var(--color-text-mid)",
          }}
        >
          <strong style={{ color: "var(--color-text-hi)" }}>Informational only.</strong>{" "}
          This page is a research artifact, not operational guidance. For
          official forecasts and emergency direction consult BC Wildfire
          Service, BC Emergency Management Climate Readiness, and the
          Pacific Climate Impacts Consortium (PCIC).
        </footer>
      </div>

      {/* Print stylesheet — clean 4-page PDF when the user hits Cmd-P */}
      <style>{`
        @media print {
          .climate-root { position: static !important; overflow: visible !important; background: white !important; color: black !important; }
          .climate-root * { color: black !important; box-shadow: none !important; }
          .climate-root section { page-break-inside: avoid; padding: 24px 0 !important; }
          .climate-root svg { max-width: 100% !important; height: auto !important; }
          .climate-root [class*="glass"], .climate-root [style*="hsl(220 30% 6%"] { background: white !important; border: 1px solid #ccc !important; }
          .topo-backdrop { display: none !important; }
        }
      `}</style>
    </div>
  );
}
