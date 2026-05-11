/**
 * Cesium env helpers. Intentionally does NOT import "cesium" — that would pull
 * the entire Cesium module graph into every route. The actual Ion token
 * application happens inside WildfireGlobe (the only Cesium-using component),
 * which is lazy-loaded.
 *
 * window.CESIUM_BASE_URL is set in index.html before any module loads.
 */

export function getCesiumIonToken(): string {
  return import.meta.env.VITE_CESIUM_ION_TOKEN ?? "";
}

export function hasCesiumIonToken(): boolean {
  return Boolean(getCesiumIonToken());
}
