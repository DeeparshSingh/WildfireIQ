import { Suspense, lazy } from "react";

import { ErrorBoundary } from "@/shell/ErrorBoundary";
import { hasCesiumIonToken } from "@/lib/cesium-helpers/init";
import { GlobeSetupNotice } from "./GlobeSetupNotice";

const WildfireGlobe = lazy(() =>
  import("./WildfireGlobe").then((m) => ({ default: m.WildfireGlobe })),
);

export function GlobeView() {
  if (!hasCesiumIonToken()) {
    return <GlobeSetupNotice />;
  }
  return (
    <ErrorBoundary label="WildfireGlobe">
      <Suspense fallback={<GlobeLoading />}>
        <WildfireGlobe />
      </Suspense>
    </ErrorBoundary>
  );
}

function GlobeLoading() {
  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "grid",
        placeItems: "center",
        background:
          "radial-gradient(ellipse at center, hsl(220 25% 6%) 0%, hsl(220 30% 2%) 70%)",
        fontFamily: "var(--font-data)",
        fontSize: 12,
        letterSpacing: "0.32em",
        textTransform: "uppercase",
        color: "var(--color-text-low)",
      }}
    >
      <div>Initializing Globe…</div>
    </div>
  );
}
