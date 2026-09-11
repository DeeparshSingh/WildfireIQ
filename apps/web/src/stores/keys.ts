/**
 * API keys and the Settings panel that edits them.
 *
 * `keys` is the browser's copy, from local storage. `status` is what the
 * backend reports it holds — booleans only, never values — and is what the
 * notices in the app key off, since three of the four keys are used by
 * server-side work the browser never sees.
 *
 * On boot the browser pushes its copy to the backend. That is what keeps a
 * restarted server in step with a browser that already has the keys, and it
 * costs one small request.
 */
import { create } from "zustand";

import {
  type KeyName,
  type KeyStatus,
  type Keys,
  anyKeySet,
  fetchKeyStatus,
  pushKeys,
  readKeys,
  writeKeys,
} from "@/lib/keys";

type SaveResult = { ok: true; reloading: boolean } | { ok: false; message: string };

type KeysState = {
  keys: Keys;
  /** Backend view. `null` until the first fetch answers. */
  status: KeyStatus | null;
  /** The backend could not be reached on the last sync. */
  offline: boolean;
  panelOpen: boolean;

  openPanel: () => void;
  closePanel: () => void;
  /** Push the local keys and refresh status. Safe to call repeatedly. */
  sync: () => Promise<void>;
  /** Persist an edit locally and on the server. */
  save: (next: Keys) => Promise<SaveResult>;
};

export const useKeysStore = create<KeysState>((set, get) => ({
  keys: readKeys(),
  status: null,
  offline: false,
  panelOpen: false,

  openPanel: () => set({ panelOpen: true }),
  closePanel: () => set({ panelOpen: false }),

  sync: async () => {
    const { keys } = get();
    try {
      const status = anyKeySet(keys) ? await pushKeys(keys) : await fetchKeyStatus();
      set({ status, offline: false });
    } catch {
      set({ offline: true });
    }
  },

  save: async (next) => {
    const before = get().keys;
    const stored = writeKeys(next);
    set({ keys: next });

    // A different Cesium token needs a fresh viewer. Cesium reads its token
    // once, when the globe module loads, so the honest way to apply a new
    // one is to reload — and the panel says so before the reader clicks.
    const cesiumChanged = before.cesium_ion_token !== next.cesium_ion_token;

    try {
      const status = await pushKeys(next);
      set({ status, offline: false });
    } catch {
      set({ offline: true });
      if (!stored) {
        return {
          ok: false,
          message:
            "Neither this browser nor the server would take the keys. Check that storage is allowed and the API is running.",
        };
      }
      return {
        ok: false,
        message:
          "Saved in this browser, but the API could not be reached. They will be sent the next time the app loads.",
      };
    }

    if (cesiumChanged) {
      window.setTimeout(() => window.location.reload(), 350);
      return { ok: true, reloading: true };
    }
    return { ok: true, reloading: false };
  },
}));

/** Is a given key missing on the server? False while status is unknown. */
export function useKeyMissing(name: KeyName): boolean {
  return useKeysStore((s) => s.status !== null && s.status[name] === false);
}

/** The browser-held Cesium token; the globe cannot mount without it. */
export function useHasCesiumToken(): boolean {
  return useKeysStore((s) => Boolean(s.keys.cesium_ion_token));
}
