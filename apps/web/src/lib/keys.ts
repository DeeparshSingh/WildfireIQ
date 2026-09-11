/**
 * API keys, and the line between a visitor's keys and the owner's.
 *
 * Visitor keys live in this browser and nowhere else. The Cesium Ion token is
 * only ever used by the browser. A visitor's own OpenRouter key is sent along
 * with each chat request as a header and used for that request alone; the
 * server never keeps it. Anyone can bring their own keys without trusting the
 * deployment with them.
 *
 * Server keys are the owner's, one set per deployment: NASA FIRMS and WAQI
 * drive scheduled jobs that run with no browser attached, and an OpenRouter
 * key there is the default for visitors who do not bring their own. They are
 * saved through the panel's server section, guarded by the owner's admin
 * token when the deployment has one, and this browser never stores them.
 *
 * Nothing here imports Cesium or React. `getCesiumIonToken` in
 * cesium-helpers/init reads through this module, and that file must stay
 * free of the Cesium import so the token check does not pull the whole
 * globe into every route.
 */
import { API_BASE } from "@/lib/api/client";

export const BROWSER_KEY_NAMES = ["cesium_ion_token", "openrouter_api_key"] as const;
export const SERVER_KEY_NAMES = ["firms_map_key", "waqi_token", "openrouter_api_key"] as const;

export type BrowserKeyName = (typeof BROWSER_KEY_NAMES)[number];
export type ServerKeyName = (typeof SERVER_KEY_NAMES)[number];
export type KeyName = BrowserKeyName | ServerKeyName;

/** The visitor's keys, kept in local storage. */
export type Keys = Record<BrowserKeyName, string>;
/** A partial update to the owner's server keys. Empty string clears. */
export type ServerKeys = Partial<Record<ServerKeyName, string>>;

export type KeyDef = {
  label: string;
  provider: string;
  /** What the key switches on, in the reader's words. */
  unlocks: string;
  /** Where to obtain one. */
  url: string;
};

export const KEY_DEFS: Record<KeyName, KeyDef> = {
  cesium_ion_token: {
    label: "Cesium Ion access token",
    provider: "Cesium Ion",
    unlocks: "the 3D globe: world terrain and aerial imagery",
    url: "https://ion.cesium.com/tokens",
  },
  openrouter_api_key: {
    label: "OpenRouter API key",
    provider: "OpenRouter",
    unlocks: "the assistant",
    url: "https://openrouter.ai/keys",
  },
  firms_map_key: {
    label: "NASA FIRMS map key",
    provider: "NASA FIRMS",
    unlocks: "the satellite hotspots layer",
    url: "https://firms.modaps.eosdis.nasa.gov/api/map_key",
  },
  waqi_token: {
    label: "WAQI token",
    provider: "World Air Quality Index",
    unlocks: "the pollutant breakdown on the air-quality page",
    url: "https://aqicn.org/data-platform/token",
  },
};

const STORAGE_KEY = "wildfireiq.keys.v1";

export function emptyKeys(): Keys {
  return { cesium_ion_token: "", openrouter_api_key: "" };
}

/** Read the visitor's keys from local storage. Never throws; storage may be blocked. */
export function readKeys(): Keys {
  const out = emptyKeys();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return out;
    const parsed: unknown = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      for (const name of BROWSER_KEY_NAMES) {
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

/** Write the visitor's keys to local storage. Returns false if storage refused. */
export function writeKeys(keys: Keys): boolean {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(keys));
    return true;
  } catch {
    return false;
  }
}

// ── the owner's server keys ─────────────────────────────────────────────

export type ServerStatus = {
  /** Whether each server key is set. Values are never returned. */
  keys: Record<ServerKeyName, boolean>;
  /** Whether the deployment requires the admin token to change them. */
  writeProtected: boolean;
};

type StatusEnvelope = {
  data: { keys: Record<string, { configured: boolean }>; write_protected: boolean };
};

function toStatus(env: StatusEnvelope): ServerStatus {
  const keys = { firms_map_key: false, waqi_token: false, openrouter_api_key: false };
  for (const name of SERVER_KEY_NAMES) keys[name] = Boolean(env.data.keys[name]?.configured);
  return { keys, writeProtected: Boolean(env.data.write_protected) };
}

export async function fetchServerStatus(): Promise<ServerStatus> {
  const res = await fetch(`${API_BASE}/api/settings/keys`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) throw new Error(`settings/keys failed: HTTP ${res.status}`);
  return toStatus((await res.json()) as StatusEnvelope);
}

/** The deployment has an admin token and the one supplied did not match. */
export class AdminTokenRejected extends Error {
  constructor() {
    super("The admin token did not match.");
    this.name = "AdminTokenRejected";
  }
}

/** Save the owner's server keys. Sends only the keys given. */
export async function pushServerKeys(keys: ServerKeys, adminToken: string): Promise<ServerStatus> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  if (adminToken) headers["X-Admin-Token"] = adminToken;
  const res = await fetch(`${API_BASE}/api/settings/keys`, {
    method: "PUT",
    headers,
    body: JSON.stringify(keys),
  });
  if (res.status === 401) throw new AdminTokenRejected();
  if (!res.ok) throw new Error(`settings/keys failed: HTTP ${res.status}`);
  return toStatus((await res.json()) as StatusEnvelope);
}
