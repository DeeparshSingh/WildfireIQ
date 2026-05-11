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
import { CameraPresetBar } from "./CameraPresets";
import { CoordinateReadout } from "./CoordinateReadout";
import { LocationSearch } from "./LocationSearch";

// Apply Ion token once at module load.
const _ionToken = getCesiumIonToken();
if (_ionToken) Ion.defaultAccessToken = _ionToken;

// Cesium Ion asset IDs:
//   2 = Bing Maps Aerial
//   3 = Bing Maps Aerial with Labels (countries, cities, roads)
const BING_AERIAL_WITH_LABELS_ASSET_ID = 3;

export function WildfireGlobe() {
  const [viewer, setViewer] = useState<CesiumViewer | null>(null);

  // Stable terrain reference — without useMemo a new Terrain instance per
  // render forces Resium to destroy+recreate the entire Viewer.
  const terrain = useMemo(() => Terrain.fromWorldTerrain({ requestVertexNormals: true }), []);

  const setViewerRef = useCallback((node: CesiumComponentRef<CesiumViewer> | null) => {
    const v = node?.cesiumElement ?? null;
    if (v) setViewer(v);
  }, []);

  useEffect(() => {
    if (!viewer) return;
    let cancelled = false;

    // ── Swap default imagery → Bing Aerial WITH labels ──────────────
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
    if (viewer.scene.skyBox) viewer.scene.skyBox.show = false;
    viewer.scene.backgroundColor = Color.TRANSPARENT;
    viewer.scene.postProcessStages.fxaa.enabled = true;

    // Camera controller — sensible limits, full Earth visible at max zoom-out.
    const cc = viewer.scene.screenSpaceCameraController;
    cc.minimumZoomDistance = 500;             // 500 m — closest the camera can get
    cc.maximumZoomDistance = 50_000_000;      // 50,000 km — well past full-Earth view
    cc.enableTilt = true;
    cc.enableLook = false;

    // requestRenderMode OFF during flight; will turn on when it completes.
    viewer.scene.requestRenderMode = false;

    // ── Start from full Earth in space view ─────────────────────────
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(-120.3273, 50.6745, 25_000_000),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-90),
        roll: 0,
      },
    });

    // ── Cinematic flyTo → top-down over Kamloops ────────────────────
    const flyTimeout = window.setTimeout(() => {
      if (cancelled) return;
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
        },
      });
    }, 400);

    return () => {
      cancelled = true;
      window.clearTimeout(flyTimeout);
    };
  }, [viewer]);

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
      <LocationSearch viewer={viewer} />
      <CameraPresetBar viewer={viewer} />
      <CoordinateReadout viewer={viewer} />
    </div>
  );
}
