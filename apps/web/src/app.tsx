import { lazy, Suspense, useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "./shell/AppShell";
import { RouteLoader } from "./shell/RouteLoader";
import { Splash } from "./shell/Splash";
import { GlobeView } from "./features/globe/GlobeView";

// The globe is the front door — keep it eager.
// Every other route is code-split so the initial JS payload stays small.
const AirQualityRoute = lazy(() =>
  import("./features/air-quality/AirQualityRoute").then((m) => ({ default: m.AirQualityRoute })),
);
const PreparednessRoute = lazy(() =>
  import("./features/preparedness/PreparednessRoute").then((m) => ({ default: m.PreparednessRoute })),
);
const SharedView = lazy(() =>
  import("./features/preparedness/SharedView").then((m) => ({ default: m.SharedView })),
);
const ClimateRoute = lazy(() =>
  import("./features/climate/ClimateRoute").then((m) => ({ default: m.ClimateRoute })),
);
const AboutView = lazy(() =>
  import("./features/about/AboutView").then((m) => ({ default: m.AboutView })),
);

export function App() {
  const [splashDone, setSplashDone] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ms = reduce ? 400 : 1400;
    const t = setTimeout(() => setSplashDone(true), ms);
    return () => clearTimeout(t);
  }, []);

  // After the splash, idle-prefetch the heaviest non-globe routes so
  // navigating to them feels instant. The dynamic imports are no-ops if
  // the chunks are already loaded.
  useEffect(() => {
    if (!splashDone) return;
    const ric =
      (window as { requestIdleCallback?: (cb: () => void) => number }).requestIdleCallback ??
      ((cb: () => void) => window.setTimeout(cb, 1500));
    ric(() => {
      void import("./features/air-quality/AirQualityRoute");
      void import("./features/climate/ClimateRoute");
      void import("./features/preparedness/PreparednessRoute");
    });
  }, [splashDone]);

  return (
    <>
      {!splashDone && <Splash />}
      <AppShell>
        <Routes>
          <Route path="/" element={<GlobeView />} />
          <Route
            path="/air-quality"
            element={
              <Suspense fallback={<RouteLoader label="Loading air quality" />}>
                <AirQualityRoute />
              </Suspense>
            }
          />
          <Route
            path="/preparedness"
            element={
              <Suspense fallback={<RouteLoader label="Loading preparedness hub" />}>
                <PreparednessRoute />
              </Suspense>
            }
          />
          <Route
            path="/preparedness/shared"
            element={
              <Suspense fallback={<RouteLoader label="Loading shared progress" />}>
                <SharedView />
              </Suspense>
            }
          />
          <Route
            path="/climate"
            element={
              <Suspense fallback={<RouteLoader label="Loading climate trends" />}>
                <ClimateRoute />
              </Suspense>
            }
          />
          <Route
            path="/about"
            element={
              <Suspense fallback={<RouteLoader label="Loading about" />}>
                <AboutView />
              </Suspense>
            }
          />
        </Routes>
      </AppShell>
    </>
  );
}
