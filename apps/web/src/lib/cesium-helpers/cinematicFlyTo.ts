/**
 * Cinematic flyTo — arcs the camera UP into space, then back DOWN to the
 * destination, scaled by the great-circle distance between current camera
 * position and target. Mimics the Google Earth / Apple Maps "zoom out,
 * traverse, zoom in" feel.
 */
import { Cartesian3, Math as CesiumMath, Rectangle } from "cesium";
import type { Viewer as CesiumViewer } from "cesium";

/** Haversine great-circle distance in km between two lon/lat pairs. */
function haversineKm(lonA: number, latA: number, lonB: number, latB: number): number {
  const R = 6371; // Earth radius in km
  const toRad = (d: number) => (d * Math.PI) / 180;
  const dLat = toRad(latB - latA);
  const dLon = toRad(lonB - lonA);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(latA)) * Math.cos(toRad(latB)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.asin(Math.sqrt(a));
}

/** Apex altitude scaled by horizontal distance — keeps animations cinematic without being slow on local moves. */
function chooseApexMeters(distanceKm: number): number {
  if (distanceKm < 25) return 60_000;           // ~60 km — block-to-block
  if (distanceKm < 100) return 250_000;         // 250 km — across a city/region
  if (distanceKm < 500) return 1_200_000;       // 1,200 km — within province
  if (distanceKm < 2_000) return 4_500_000;     // 4,500 km — cross-country
  if (distanceKm < 8_000) return 12_000_000;    // 12,000 km — continental
  return 22_000_000;                            // 22,000 km — space view, true global hop
}

/** Total animation duration in seconds, scaled by distance. Bounded so very long hops don't feel sluggish. */
function chooseDurationSec(distanceKm: number, override?: number): number {
  if (typeof override === "number") return override;
  if (distanceKm < 5) return 1.4;
  if (distanceKm < 100) return 2.2;
  if (distanceKm < 1_000) return 3.0;
  if (distanceKm < 5_000) return 4.0;
  return 4.8;
}

type FlyToOpts = {
  /** Destination longitude in degrees. */
  lon: number;
  /** Destination latitude in degrees. */
  lat: number;
  /** Final camera altitude in metres above the ellipsoid. */
  height: number;
  /** Final pitch in degrees. -90 = top-down. */
  pitch?: number;
  /** Final heading in degrees. */
  heading?: number;
  /** Override duration in seconds. */
  duration?: number;
  /** Fired when the animation settles. */
  onComplete?: () => void;
};

/**
 * Drives a cinematic flyTo with arc + scaled duration. Disables
 * requestRenderMode for the flight and re-enables it after landing.
 */
export function cinematicFlyTo(viewer: CesiumViewer, opts: FlyToOpts) {
  const c = viewer.camera.positionCartographic;
  const fromLon = CesiumMath.toDegrees(c.longitude);
  const fromLat = CesiumMath.toDegrees(c.latitude);

  const distanceKm = haversineKm(fromLon, fromLat, opts.lon, opts.lat);
  const apexMeters = chooseApexMeters(distanceKm);
  const duration = chooseDurationSec(distanceKm, opts.duration);

  viewer.scene.requestRenderMode = false;

  viewer.camera.flyTo({
    destination: Cartesian3.fromDegrees(opts.lon, opts.lat, opts.height),
    orientation: {
      heading: CesiumMath.toRadians(opts.heading ?? 0),
      pitch: CesiumMath.toRadians(opts.pitch ?? -90),
      roll: 0,
    },
    duration,
    maximumHeight: apexMeters,
    easingFunction: (t) => {
      // Smoother than Cesium's default linear interpolation across long arcs.
      // Quintic ease-in-out.
      return t < 0.5 ? 16 * t ** 5 : 1 - (-2 * t + 2) ** 5 / 2;
    },
    complete: () => {
      viewer.scene.requestRenderMode = true;
      viewer.scene.maximumRenderTimeChange = Infinity;
      opts.onComplete?.();
    },
  });
}

/**
 * Variant for area destinations (rectangles from geocoder results).
 * Frames the area top-down with the same cinematic arc.
 */
export function cinematicFlyToRectangle(
  viewer: CesiumViewer,
  rect: Rectangle,
  onComplete?: () => void,
) {
  // Use the rectangle's centre as the "to" lon/lat for arc calculation.
  const centerLon = CesiumMath.toDegrees((rect.west + rect.east) / 2);
  const centerLat = CesiumMath.toDegrees((rect.south + rect.north) / 2);

  const c = viewer.camera.positionCartographic;
  const fromLon = CesiumMath.toDegrees(c.longitude);
  const fromLat = CesiumMath.toDegrees(c.latitude);
  const distanceKm = haversineKm(fromLon, fromLat, centerLon, centerLat);
  const apexMeters = chooseApexMeters(distanceKm);
  const duration = chooseDurationSec(distanceKm);

  viewer.scene.requestRenderMode = false;
  viewer.camera.flyTo({
    destination: rect,
    orientation: {
      heading: CesiumMath.toRadians(0),
      pitch: CesiumMath.toRadians(-90),
      roll: 0,
    },
    duration,
    maximumHeight: apexMeters,
    easingFunction: (t) => (t < 0.5 ? 16 * t ** 5 : 1 - (-2 * t + 2) ** 5 / 2),
    complete: () => {
      viewer.scene.requestRenderMode = true;
      viewer.scene.maximumRenderTimeChange = Infinity;
      onComplete?.();
    },
  });
}
