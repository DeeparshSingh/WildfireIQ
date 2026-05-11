import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Cartesian3,
  Color,
  Ion,
  IonImageryProvider,
  Math as CesiumMath,
  Terrain,
} from "cesium";
import { Viewer } from "resium";
import type { CesiumComponentRef } from "resium";
import type { Viewer as CesiumViewer } from "cesium";

import { getCesiumIonToken } from "@/lib/cesium-helpers/init";
import { useGlobeStore } from "@/stores/globe";
import {
  ActiveFiresLayer,
  EvacLayer,
  FIRMSHotspotsLayer,
  FWIStationsLayer,
  RiskGridLayer,
  SmokeLayer,
} from "./layers";

// Apply Ion token once at module load.
const _ionToken = getCesiumIonToken();
if (_ionToken) Ion.defaultAccessToken = _ionToken;

// Cesium Ion asset IDs:
//   3 = Bing Maps Aerial with Labels (clean white labels baked into imagery)
const BING_AERIAL_WITH_LABELS_ASSET_ID = 3;

export function WildfireGlobe() {
  const [viewer, setViewerLocal] = useState<CesiumViewer | null>(null);
  const introPlayed = useGlobeStore((s) => s.introPlayed);
  const lastCamera = useGlobeStore((s) => s.lastCamera);
  const markIntroPlayed = useGlobeStore((s) => s.markIntroPlayed);
  const openDataGate = useGlobeStore((s) => s.openDataGate);
  const setLastCamera = useGlobeStore((s) => s.setLastCamera);
  const setViewer = useGlobeStore((s) => s.setViewer);

  const terrain = useMemo(() => Terrain.fromWorldTerrain({ requestVertexNormals: true }), []);

  const setViewerRef = useCallback(
    (node: CesiumComponentRef<CesiumViewer> | null) => {
      const v = node?.cesiumElement ?? null;
      if (v) {
        setViewerLocal(v);
        setViewer(v);
      }
    },
    [setViewer],
  );

  // ── Configure the viewer once it's attached. ──────────────────────
  useEffect(() => {
    if (!viewer) return;
    let cancelled = false;

    (async () => {
      try {
        const labeled = await IonImageryProvider.fromAssetId(
          BING_AERIAL_WITH_LABELS_ASSET_ID,
        );
        if (cancelled) return;
        viewer.imageryLayers.removeAll();
        viewer.imageryLayers.addImageryProvider(labeled);
      } catch (err) {
        console.warn("[WildfireGlobe] could not load labeled imagery", err);
      }
    })();

    // ── Atmosphere → moody tactical ─────────────────────────────────
    if (viewer.scene.skyAtmosphere) {
      viewer.scene.skyAtmosphere.hueShift = -0.08;
      viewer.scene.skyAtmosphere.saturationShift = -0.3;
      viewer.scene.skyAtmosphere.brightnessShift = -0.15;
    }
    viewer.scene.fog.enabled = true;
    viewer.scene.fog.density = 1.5e-4;
    viewer.scene.globe.enableLighting = false;
    viewer.scene.globe.baseColor = Color.fromCssColorString("hsl(220, 30%, 4%)");
    if (viewer.scene.sun) viewer.scene.sun.show = false;
    if (viewer.scene.moon) viewer.scene.moon.show = false;
    // Keep the Cesium-built-in skyBox ON — it ships with the Tycho-2 star
    // catalog, which gives a subtle but real "space" feel when zoomed out.
    if (viewer.scene.skyBox) viewer.scene.skyBox.show = true;
    viewer.scene.backgroundColor = Color.fromCssColorString("hsl(220, 30%, 2%)");
    viewer.scene.postProcessStages.fxaa.enabled = true;

    // ── Render at native device pixel density ───────────────────────
    // Cesium defaults to CSS pixels, which on a Retina display means
    // everything (especially text in imagery tiles) is scaled up 2× → blur.
    // Setting resolutionScale to devicePixelRatio renders at native pixels.
    // We cap at 1.5 (not full 2x) to keep retina sharpness without doubling
    // the pixel workload, which kept the globe smoother to navigate.
    const dpr = Math.min(window.devicePixelRatio || 1, 1.5);
    viewer.resolutionScale = dpr;
    // Defaults are deliberate: maximumScreenSpaceError stays at 2 (smoother
    // pan/zoom). preloadSiblings + large tileCacheSize were thrashing memory
    // and stuttering navigation.

    // ── Camera controller — sensible limits ────────────────────────
    const cc = viewer.scene.screenSpaceCameraController;
    cc.minimumZoomDistance = 500;
    cc.maximumZoomDistance = 50_000_000;
    cc.enableTilt = true;
    cc.enableLook = false;

    return () => {
      cancelled = true;
    };
  }, [viewer]);

  // ── Intro vs. restore: only one runs, depending on whether intro
  //    has already been played in this browser session. ─────────────
  useEffect(() => {
    if (!viewer) return;

    if (lastCamera && introPlayed) {
      // Restore the user's last position — no flight, no fanfare.
      viewer.camera.setView({
        destination: Cartesian3.fromDegrees(
          lastCamera.lon,
          lastCamera.lat,
          lastCamera.height,
        ),
        orientation: {
          heading: lastCamera.heading,
          pitch: lastCamera.pitch,
          roll: lastCamera.roll,
        },
      });
      viewer.scene.requestRenderMode = true;
      viewer.scene.maximumRenderTimeChange = Infinity;
      openDataGate(); // layers can render immediately on revisits
      return;
    }

    // First time this session — play the cinematic intro.
    viewer.scene.requestRenderMode = false;
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(-120.3273, 50.6745, 25_000_000),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-90),
        roll: 0,
      },
    });

    const flyTimeout = window.setTimeout(() => {
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(-120.3273, 50.6745, 250_000),
        orientation: {
          heading: CesiumMath.toRadians(0),
          pitch: CesiumMath.toRadians(-90),
          roll: 0,
        },
        duration: 4.5,
        complete: () => {
          viewer.scene.requestRenderMode = true;
          viewer.scene.maximumRenderTimeChange = Infinity;
          markIntroPlayed();
        },
      });
    }, 400);

    return () => window.clearTimeout(flyTimeout);
  }, [viewer, introPlayed, lastCamera, markIntroPlayed, openDataGate]);

  // ── Persist camera position on every move, throttled by Cesium's
  //    `percentageChanged` so we don't write on every frame. ─────────
  useEffect(() => {
    if (!viewer) return;
    viewer.camera.percentageChanged = 0.01;
    const onMove = () => {
      const c = viewer.camera.positionCartographic;
      setLastCamera({
        lon: CesiumMath.toDegrees(c.longitude),
        lat: CesiumMath.toDegrees(c.latitude),
        height: c.height,
        heading: viewer.camera.heading,
        pitch: viewer.camera.pitch,
        roll: viewer.camera.roll,
      });
    };
    const remove = viewer.camera.changed.addEventListener(onMove);
    return () => remove();
  }, [viewer, setLastCamera]);

  return (
    <div style={{ position: "absolute", inset: 0 }}>
      <Viewer
        ref={setViewerRef}
        full
        terrain={terrain}
        animation={false}
        baseLayerPicker={false}
        fullscreenButton={false}
        geocoder={false}
        homeButton={false}
        infoBox={false}
        navigationHelpButton={false}
        sceneModePicker={false}
        selectionIndicator={false}
        timeline={false}
        scene3DOnly
      />
      {/* Risk grid renders first (underneath) so points/icons paint above it. */}
      <RiskGridLayer />
      <ActiveFiresLayer />
      <FIRMSHotspotsLayer />
      <EvacLayer />
      <SmokeLayer />
      <FWIStationsLayer />
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          pointerEvents: "none",
          background:
            "radial-gradient(ellipse at center, transparent 50%, hsl(220 30% 2% / 0.55) 100%)",
        }}
      />
    </div>
  );
}
