/**
 * Per-layer filter state. The LayerDetailModal renders filter controls;
 * the layer components and modal item lists both read from here.
 */
import { create } from "zustand";

export type FiresFilter = {
  includeExtinguished: boolean;
  /** Only show fires whose status matches one of these (case-insensitive substring).
   *  Empty array = no status filter. */
  statuses: string[];
  /** Optional minimum hectares threshold. */
  minHectares: number;
};

export type HotspotsFilter = {
  /** Minimum confidence (0–100). */
  minConfidence: number;
  /** Which satellite sources to keep. Empty = all. */
  sources: string[];
  /** Hours back from now to include. */
  sinceHours: number;
};

export type EvacFilter = {
  /** Statuses to show. Empty = all. */
  statuses: string[];
  /** Hide rescinded / no-longer-active zones from both the list and the map. */
  hidePast: boolean;
};

export type FwiFilter = {
  /** Only stations with FWI >= this value. */
  minFwi: number;
};

type FiltersState = {
  fires: FiresFilter;
  hotspots: HotspotsFilter;
  evac: EvacFilter;
  fwi: FwiFilter;
  setFires: (p: Partial<FiresFilter>) => void;
  setHotspots: (p: Partial<HotspotsFilter>) => void;
  setEvac: (p: Partial<EvacFilter>) => void;
  setFwi: (p: Partial<FwiFilter>) => void;
};

export const useFiltersStore = create<FiltersState>((set) => ({
  fires: {
    includeExtinguished: false,
    statuses: [],
    minHectares: 0,
  },
  hotspots: {
    minConfidence: 30,
    sources: [],
    sinceHours: 72,
  },
  evac: {
    statuses: [],
    hidePast: true,
  },
  fwi: {
    minFwi: 0,
  },
  setFires: (p) => set((s) => ({ fires: { ...s.fires, ...p } })),
  setHotspots: (p) => set((s) => ({ hotspots: { ...s.hotspots, ...p } })),
  setEvac: (p) => set((s) => ({ evac: { ...s.evac, ...p } })),
  setFwi: (p) => set((s) => ({ fwi: { ...s.fwi, ...p } })),
}));
