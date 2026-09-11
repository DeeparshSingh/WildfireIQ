/**
 * Cesium token helpers. Intentionally does NOT import "cesium" — that would
 * pull the entire Cesium module graph into every route. The actual Ion token
 * application happens inside WildfireGlobe (the only Cesium-using component),
 * which is lazy-loaded.
 *
 * The token is the one the reader entered in the Settings panel, read from
 * local storage. For a React component that must re-render when it changes,
 * use `useHasCesiumToken` from the keys store instead of these.
 *
 * window.CESIUM_BASE_URL is set in index.html before any module loads.
 */
import { readKeys } from "@/lib/keys";

export function getCesiumIonToken(): string {
  return readKeys().cesium_ion_token;
}

export function hasCesiumIonToken(): boolean {
  return Boolean(getCesiumIonToken());
}
