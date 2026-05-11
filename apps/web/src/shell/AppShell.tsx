import { Suspense, lazy, type ReactNode } from "react";
import { motion } from "motion/react";

import { ErrorBoundary } from "./ErrorBoundary";
import { LeftRail } from "./LeftRail";
import { TopBar } from "./TopBar";
import { hasCesiumIonToken } from "@/lib/cesium-helpers/init";

// Globe is lazy-loaded so the initial JS bundle stays slim. It mounts once
// at the AppShell level and lives on across route changes.
const WildfireGlobe = lazy(() =>
  import("@/features/globe/WildfireGlobe").then((m) => ({ default: m.WildfireGlobe })),
);

export function AppShell({ children }: { children: ReactNode }) {
  const showGlobe = hasCesiumIonToken();

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        display: "grid",
        gridTemplateColumns: "72px 1fr",
        gridTemplateRows: "56px 1fr",
        gridTemplateAreas: `"rail top" "rail main"`,
      }}
    >
      <motion.div
        style={{ gridArea: "rail", zIndex: 10 }}
        initial={{ x: -32, opacity: 0 }}
        animate={{ x: 0, opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.9, ease: [0.16, 1, 0.3, 1] }}
      >
        <LeftRail />
      </motion.div>

      <motion.div
        style={{ gridArea: "top", zIndex: 10 }}
        initial={{ y: -16, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.6, delay: 0.9, ease: [0.16, 1, 0.3, 1] }}
      >
        <TopBar />
      </motion.div>

      <main
        style={{
          gridArea: "main",
          position: "relative",
          overflow: "hidden",
          background: "var(--color-bg-0)",
        }}
      >
        {/* The Cesium viewer lives here, always mounted, behind everything. */}
        {showGlobe && (
          <ErrorBoundary label="WildfireGlobe">
            <Suspense fallback={null}>
              <WildfireGlobe />
            </Suspense>
          </ErrorBoundary>
        )}

        {/* Route content overlays. */}
        <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
          {/* The "none" container lets clicks pass through to the globe by
              default; each overlay re-enables pointer events on itself. */}
          {children}
        </div>
      </main>
    </div>
  );
}
