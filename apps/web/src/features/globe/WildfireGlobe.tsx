import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Cartesian3,
  Color,
  Ion,
  IonImageryProvider,
  Math as CesiumMath,
  Terrain,
  UrlTemplateImageryProvider,
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
  SmokeLayer,
} from "./layers";

// Apply Ion token once at module load.
const _ionToken = getCesiumIonToken();
if (_ionToken) Ion.defaultAccessToken = _ionToken;

// Cesium Ion asset IDs:
//   2 = Bing Maps Aerial (no labels — labels come from Esri overlay below)
const BING_AERIAL_ASSET_ID = 2;

// Esri's free "Reference Overlay" — vector-rendered place names, country/state
// boundaries, road labels. Rendered at native zoom levels so labels stay
// crisp at every distance instead of getting upscaled-blurry like baked-in
// raster labels do.
const ESRI_REFERENCE_LABELS_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}";
const ESRI_TRANSPORT_URL =
  "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}";

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
        const aerial = await IonImageryProvider.fromAssetId(BING_AERIAL_ASSET_ID);
        if (cancelled) return;
        viewer.imageryLayers.removeAll();
        // Base imagery (no labels) — gives us clean satellite without baked-in
        // raster labels that blur when scaled.
        viewer.imageryLayers.addImageryProvider(aerial);

        // Vector-style label + boundary overlay from Esri. Free, no key.
        // Stays crisp at every zoom because it's tiled per-level rather than
        // a single fixed-resolution raster.
        const transport = new UrlTemplateImageryProvider({
          url: ESRI_TRANSPORT_URL,
          maximumLevel: 19,
          credit: "Roads © Esri",
        });
        const labels = new UrlTemplateImageryProvider({
          url: ESRI_REFERENCE_LABELS_URL,
          maximumLevel: 19,
          credit: "Place labels © Esri · GEBCO · NOAA",
        });
        const transportLayer = viewer.imageryLayers.addImageryProvider(transport);
        transportLayer.alpha = 0.85;
        const labelsLayer = viewer.imageryLayers.addImageryProvider(labels);
        labelsLayer.alpha = 1.0;
      } catch (err) {
        console.warn("[WildfireGlobe] could not load imagery", err);
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
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    viewer.resolutionScale = dpr;
    // Use anisotropic filtering on globe tiles so labels stay crisp when
    // viewed at oblique angles.
    viewer.scene.globe.maximumScreenSpaceError = 1.5; // default 2; lower = sharper
    viewer.scene.globe.preloadSiblings = true;
    viewer.scene.globe.tileCacheSize = 1000;

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
