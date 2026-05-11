/**
 * Per-layer visibility + selected feature state. Survives route changes
 * because it lives in Zustand at app scope (re-mounting WildfireGlobe's
 * children does not reset it).
 */
import { create } from "zustand";

export type LayerId = "fires" | "hotspots" | "evac" | "smoke" | "fwi";

export type SelectedFeature =
  | { kind: "fire"; id: string }
  | { kind: "hotspot"; id: string }
  | { kind: "evac"; id: string }
  | { kind: "fwi"; id: string };

type LayersState = {
  visible: Record<LayerId, boolean>;
  toggle: (id: LayerId) => void;
  set: (id: LayerId, on: boolean) => void;
  selected: SelectedFeature | null;
  select: (s: SelectedFeature | null) => void;
};

export const useLayersStore = create<LayersState>((set) => ({
  visible: {
    fires: true,
    hotspots: true,
    evac: true,
    smoke: false,
    fwi: false,
  },
  toggle: (id) =>
    set((state) => ({
      visible: { ...state.visible, [id]: !state.visible[id] },
    })),
  set: (id, on) =>
    set((state) => ({
      visible: { ...state.visible, [id]: on },
    })),
  selected: null,
  select: (s) => set({ selected: s }),
}));
