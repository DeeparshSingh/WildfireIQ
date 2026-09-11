/**
 * API keys and the Settings panel that edits them.
 *
 * `keys` is the visitor's copy: the Cesium token and, if they brought one,
 * their own OpenRouter key. Both stay in this browser. `status` is what the
 * backend reports about the owner's server keys — booleans only, never
 * values — and it is what the notices in the app key off, since the server
 * keys drive work the browser never sees.
 *
 * Nothing is pushed on load. A visitor's keys are theirs; the owner's are
 * saved deliberately, through the panel's server section, with the admin
 * token when the deployment has one.
 */
import { create } from "zustand";

import {
  AdminTokenRejected,
  type Keys,
  type ServerKeyName,
  type ServerKeys,
  type ServerStatus,
  fetchServerStatus,
  pushServerKeys,
  readKeys,
  writeKeys,
} from "@/lib/keys";

type SaveResult = { ok: true; reloading: boolean } | { ok: false; message: string };
type ServerSaveResult = { ok: true } | { ok: false; message: string };

type KeysState = {
  keys: Keys;
  /** The owner's server keys, as the backend reports them. `null` until the first fetch answers. */
  status: ServerStatus | null;
  /** The backend could not be reached on the last status fetch. */
  offline: boolean;
  panelOpen: boolean;

  openPanel: () => void;
  closePanel: () => void;
  /** Refresh the server status. Safe to call repeatedly; sends nothing. */
  sync: () => Promise<void>;
  /** Save the visitor's keys to this browser. */
  saveBrowserKeys: (next: Keys) => SaveResult;
  /** Save the owner's server keys to the backend. */
  saveServerKeys: (changes: ServerKeys, adminToken: string) => Promise<ServerSaveResult>;
};

export const useKeysStore = create<KeysState>((set, get) => ({
  keys: readKeys(),
  status: null,
  offline: false,
  panelOpen: false,

  openPanel: () => set({ panelOpen: true }),
  closePanel: () => set({ panelOpen: false }),

  sync: async () => {
    try {
      set({ status: await fetchServerStatus(), offline: false });
    } catch {
      set({ offline: true });
    }
  },

  saveBrowserKeys: (next) => {
    const before = get().keys;
    if (!writeKeys(next)) {
      return {
        ok: false,
        message: "This browser would not store the keys. Check that site storage is allowed.",
      };
    }
    set({ keys: next });
    // Cesium reads its token once, when the globe module loads, so the honest
    // way to apply a new one is a reload — and the panel says so first.
    const cesiumChanged = before.cesium_ion_token !== next.cesium_ion_token;
    if (cesiumChanged) window.setTimeout(() => window.location.reload(), 350);
    return { ok: true, reloading: cesiumChanged };
  },

  saveServerKeys: async (changes, adminToken) => {
    try {
      set({ status: await pushServerKeys(changes, adminToken), offline: false });
      return { ok: true };
    } catch (err) {
      if (err instanceof AdminTokenRejected) {
        return {
          ok: false,
          message: "The admin token did not match. Server keys were not changed.",
        };
      }
      set({ offline: true });
      return { ok: false, message: "The API could not be reached. Server keys were not changed." };
    }
  },
}));

/** Is one of the owner's server keys missing? False while status is unknown. */
export function useKeyMissing(name: ServerKeyName): boolean {
  return useKeysStore((s) => s.status !== null && s.status.keys[name] === false);
}

/** The browser-held Cesium token; the globe cannot mount without it. */
export function useHasCesiumToken(): boolean {
  return useKeysStore((s) => Boolean(s.keys.cesium_ion_token));
}

/** The visitor's own OpenRouter key, if they brought one. */
export function useVisitorOpenRouterKey(): string {
  return useKeysStore((s) => s.keys.openrouter_api_key);
}
