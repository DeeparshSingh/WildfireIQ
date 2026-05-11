/**
 * Globe view state — shared across the whole app so the Cesium viewer
 * can live in AppShell while route components access it.
 *
 * Survives React re-mounts within the same browser session (reload resets
 * everything). Lets us play the cinematic intro only once per page load.
 */
import { create } from "zustand";
import type { Viewer as CesiumViewer } from "cesium";

export type CameraSnapshot = {
  lon: number;
  lat: number;
  height: number;
  heading: number;
  pitch: number;
  roll: number;
};

type GlobeState = {
  viewer: CesiumViewer | null;
  introPlayed: boolean;
  /** True once intro flyTo has landed OR when intro was skipped because a
   *  prior camera state was restored. Data layers wait for this. */
  dataGateOpen: boolean;
  lastCamera: CameraSnapshot | null;
  setViewer: (v: CesiumViewer | null) => void;
  markIntroPlayed: () => void;
  openDataGate: () => void;
  setLastCamera: (c: CameraSnapshot) => void;
};

export const useGlobeStore = create<GlobeState>((set) => ({
  viewer: null,
  introPlayed: false,
  dataGateOpen: false,
  lastCamera: null,
  setViewer: (v) => set({ viewer: v }),
  markIntroPlayed: () => set({ introPlayed: true, dataGateOpen: true }),
  openDataGate: () => set({ dataGateOpen: true }),
  setLastCamera: (c) => set({ lastCamera: c }),
}));
