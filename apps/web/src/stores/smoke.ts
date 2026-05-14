/**
 * Smoke-forecast scrubber state. Used by the SmokeLayer (Cesium) and the
 * SmokeBrowser (modal) so they stay in sync.
 */
import { create } from "zustand";

type SmokeState = {
  /** Index into the SmokeTimestep array (0 = first available, usually = now). */
  timestepIndex: number;
  setTimestepIndex: (i: number) => void;
};

export const useSmokeStore = create<SmokeState>((set) => ({
  timestepIndex: 0,
  setTimestepIndex: (i) => set({ timestepIndex: Math.max(0, i) }),
}));
