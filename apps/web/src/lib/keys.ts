/**
 * The four third-party API keys, entered in the app rather than in a file.
 *
 * Each key unlocks one feature; the platform runs without any of them. The
 * reader types them once into the Settings panel. They are kept in this
 * browser's local storage — so they survive a reload and never travel with
 * a share link — and pushed to the backend, which needs three of them for
 * work that happens with no browser attached: the scheduled hotspot and
 * pollutant pulls, and the assistant.
 *
 * Nothing here imports Cesium or React. `getCesiumIonToken` in
 * cesium-helpers/init reads through this module, and that file must stay
 * free of the Cesium import so the token check does not pull the whole
 * globe into every route.
 */
import { API_BASE } from "@/lib/api/client";

export const KEY_NAMES = [
  "cesium_ion_token",
  "firms_map_key",
  "waqi_token",
  "openrouter_api_key",
] as const;

export type KeyName = (typeof KEY_NAMES)[number];
export type Keys = Record<KeyName, string>;

export type KeyDef = {
  name: KeyName;
  label: string;
  provider: string;
  /** The feature the key switches on, in the reader's words. */
  unlocks: string;
  /** Where to obtain one. */
  url: string;
  /** Whether the browser itself uses the value (as opposed to only the backend). */
  browserUses: boolean;
};

export const KEY_DEFS: readonly KeyDef[] = [
  {
    name: "cesium_ion_token",
    label: "Cesium Ion access token",
    provider: "Cesium Ion",
    unlocks: "the 3D globe: world terrain and aerial imagery",
    url: "https://ion.cesium.com/tokens",
    browserUses: true,
  },
  {
    name: "firms_map_key",
    label: "NASA FIRMS map key",
    provider: "NASA FIRMS",
    unlocks: "the satellite hotspots layer",
    url: "https://firms.modaps.eosdis.nasa.gov/api/map_key",
    browserUses: false,
  },
  {
    name: "waqi_token",
    label: "WAQI token",
    provider: "World Air Quality Index",
    unlocks: "the pollutant breakdown on the air-quality page",
    url: "https://aqicn.org/data-platform/token",
    browserUses: false,
  },
  {
    name: "openrouter_api_key",
    label: "OpenRouter API key",
    provider: "OpenRouter",
    unlocks: "the assistant",
    url: "https://openrouter.ai/keys",
    browserUses: false,
  },
];

const STORAGE_KEY = "wildfireiq.keys.v1";

export function emptyKeys(): Keys {
  return {
    cesium_ion_token: "",
    firms_map_key: "",
    waqi_token: "",
    openrouter_api_key: "",
  };
}

/** Read the keys from local storage. Never throws; storage may be blocked. */
export function readKeys(): Keys {
  const out = emptyKeys();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return out;
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      for (const name of KEY_NAMES) {
        const v = (parsed as Record<string, unknown>)[name];
        if (typeof v === "string") out[name] = v.trim();
      }
    }
  } catch {
    // Private browsing, a cleared store, or a hand-edited value. Empty is
    // the honest fallback; the Settings panel shows what is missing.
  }
  return out;
}

/** Write the keys to local storage. Returns false if storage refused. */
export function writeKeys(keys: Keys): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(keys));
    return true;
  } catch {
    return false;
  }
}

export function anyKeySet(keys: Keys): boolean {
  return KEY_NAMES.some((n) => Boolean(keys[n]));
}

// ── talking to the backend ──────────────────────────────────────────────

export type KeyStatus = Record<KeyName, boolean>;

type StatusEnvelope = {
  data: { keys: Record<string, { configured: boolean }>; all_configured: boolean };
};

function toStatus(env: StatusEnvelope): KeyStatus {
  const s = emptyKeys() as unknown as Record<KeyName, boolean>;
  for (const name of KEY_NAMES) s[name] = Boolean(env.data.keys[name]?.configured);
  return s;
}

/** Which keys the backend currently holds. Values are never returned. */
export async function fetchKeyStatus(): Promise<KeyStatus> {
  const res = await fetch(`${API_BASE}/api/settings/keys`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`settings/keys failed: HTTP ${res.status}`);
  return toStatus((await res.json()) as StatusEnvelope);
}

/**
 * Push keys to the backend. Sends every key, including empty ones, so a
 * key cleared in the browser is cleared on the server too.
 */
export async function pushKeys(keys: Keys): Promise<KeyStatus> {
  const res = await fetch(`${API_BASE}/api/settings/keys`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(keys),
  });
  if (!res.ok) throw new Error(`settings/keys failed: HTTP ${res.status}`);
  return toStatus((await res.json()) as StatusEnvelope);
}
