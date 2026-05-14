import { useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";

import { AppShell } from "./shell/AppShell";
import { Splash } from "./shell/Splash";
import { GlobeView } from "./features/globe/GlobeView";
import { AirQualityRoute } from "./features/air-quality/AirQualityRoute";
import { PreparednessRoute } from "./features/preparedness/PreparednessRoute";
import { SharedView } from "./features/preparedness/SharedView";
import { ClimatePlaceholder } from "./features/climate/ClimatePlaceholder";
import { AboutView } from "./features/about/AboutView";

export function App() {
  const [splashDone, setSplashDone] = useState(false);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ms = reduce ? 400 : 1400;
    const t = setTimeout(() => setSplashDone(true), ms);
    return () => clearTimeout(t);
  }, []);

  return (
    <>
      {!splashDone && <Splash />}
      <AppShell>
        <Routes>
          <Route path="/" element={<GlobeView />} />
          <Route path="/air-quality" element={<AirQualityRoute />} />
          <Route path="/preparedness" element={<PreparednessRoute />} />
          <Route path="/preparedness/shared" element={<SharedView />} />
          <Route path="/climate" element={<ClimatePlaceholder />} />
          <Route path="/about" element={<AboutView />} />
        </Routes>
      </AppShell>
    </>
  );
}
