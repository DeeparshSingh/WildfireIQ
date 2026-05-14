/**
 * Phase 5 state layer — localStorage + IndexedDB, no network.
 *
 *   localStorage `wildfireiq.profile.v1`  : PrepProfile (lightweight)
 *   localStorage `wildfireiq.progress.v1` : ProgressV1 metadata (no photos)
 *   IndexedDB    `wildfireiq.progress.v1` / store `photos` : photo blobs
 *
 * Photos are split out of the main progress object so localStorage stays
 * tiny (a few hundred bytes) and the photo cache can be cleared
 * independently. Every read/write is wrapped — privacy modes that disable
 * storage degrade to in-memory only.
 */

export const SITUATION_OPTIONS = [
  { id: "house_yard", label: "I have a house with a yard" },
  { id: "renter", label: "I rent / live in an apartment" },
  { id: "pets", label: "I have pets or livestock" },
  { id: "sensitive", label: "I'm in a sensitive group" },
  { id: "outdoor_worker", label: "I work outdoors" },
  { id: "mobility", label: "I have mobility considerations" },
] as const;

export type SituationId = (typeof SITUATION_OPTIONS)[number]["id"];

export type Dwelling = "house" | "townhome" | "cabin" | "mobile";
export type Season = "any" | "spring" | "summer" | "fall";

export type PrepProfile = {
  version: "1";
  neighbourhood: string | null;
  neighbourhoodLat: number | null;
  neighbourhoodLon: number | null;
  dwelling: Dwelling;
  season: Season;
  situation: SituationId[];
  notify: { aqhiThreshold: number; evacAlerts: boolean };
  createdAt: string;
};

export type ProgressV1 = {
  version: "1";
  completedActions: { id: string; completedAt: string; hasPhoto: boolean }[];
  shared: boolean;
  smokeAware: boolean;
  streakDays: number;
  lastVisitDay: string; // YYYY-MM-DD
  lastEvacStatus: "clear" | "alert" | "order" | null;
  earnedAchievements: string[]; // ids that have already triggered confetti
};

const PROFILE_KEY = "wildfireiq.profile.v1";
const PROGRESS_KEY = "wildfireiq.progress.v1";

export function loadProfile(): PrepProfile | null {
  try {
    const raw = localStorage.getItem(PROFILE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as PrepProfile;
  } catch {
    return null;
  }
}

export function saveProfile(p: PrepProfile) {
  try {
    localStorage.setItem(PROFILE_KEY, JSON.stringify(p));
  } catch {
    /* incognito / quota — fall through */
  }
}

export function clearProfile() {
  try {
    localStorage.removeItem(PROFILE_KEY);
    localStorage.removeItem(PROGRESS_KEY);
  } catch {
    /* noop */
  }
}

const todayISO = () => new Date().toISOString().slice(0, 10);

export function loadProgress(): ProgressV1 {
  try {
    const raw = localStorage.getItem(PROGRESS_KEY);
    if (raw) return JSON.parse(raw) as ProgressV1;
  } catch {
    /* noop */
  }
  return {
    version: "1",
    completedActions: [],
    shared: false,
    smokeAware: false,
    streakDays: 0,
    lastVisitDay: "",
    lastEvacStatus: null,
    earnedAchievements: [],
  };
}

export function saveProgress(p: ProgressV1) {
  try {
    localStorage.setItem(PROGRESS_KEY, JSON.stringify(p));
  } catch {
    /* noop */
  }
}

/** Daily streak rollover: call once per session. */
export function rolloverStreak(p: ProgressV1): ProgressV1 {
  const today = todayISO();
  if (p.lastVisitDay === today) return p;
  const yesterday = new Date(Date.now() - 86_400_000).toISOString().slice(0, 10);
  const next = { ...p };
  next.lastVisitDay = today;
  next.streakDays =
    p.lastVisitDay === yesterday ? p.streakDays + 1 : 1;
  return next;
}

// ─── IndexedDB for photo blobs ─────────────────────────────────────────

const DB_NAME = "wildfireiq.progress.v1";
const STORE = "photos";

function _openDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, 1);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE)) db.createObjectStore(STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

export async function putPhoto(actionId: string, blob: Blob): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const db = await _openDB();
  await new Promise<void>((res, rej) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).put(blob, actionId);
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
  });
  db.close();
}

export async function getPhoto(actionId: string): Promise<Blob | null> {
  if (typeof indexedDB === "undefined") return null;
  const db = await _openDB();
  return new Promise<Blob | null>((res, rej) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).get(actionId);
    req.onsuccess = () => res((req.result as Blob) ?? null);
    req.onerror = () => rej(req.error);
    tx.oncomplete = () => db.close();
  });
}

export async function deletePhoto(actionId: string): Promise<void> {
  if (typeof indexedDB === "undefined") return;
  const db = await _openDB();
  await new Promise<void>((res, rej) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(actionId);
    tx.oncomplete = () => res();
    tx.onerror = () => rej(tx.error);
  });
  db.close();
}

// ─── Share URL: base64-encode profile + progress into the hash ─────────

export type SharedPayload = { p: PrepProfile; g: Omit<ProgressV1, "version"> };

export function encodeShare(profile: PrepProfile, progress: ProgressV1): string {
  const payload: SharedPayload = {
    p: profile,
    g: {
      completedActions: progress.completedActions.map((c) => ({
        ...c,
        hasPhoto: false, // photos never leave the device
      })),
      shared: true,
      smokeAware: progress.smokeAware,
      streakDays: progress.streakDays,
      lastVisitDay: progress.lastVisitDay,
      lastEvacStatus: null,
      earnedAchievements: progress.earnedAchievements,
    },
  };
  const json = JSON.stringify(payload);
  return btoa(unescape(encodeURIComponent(json)));
}

export function decodeShare(b64: string): SharedPayload | null {
  try {
    const json = decodeURIComponent(escape(atob(b64)));
    return JSON.parse(json) as SharedPayload;
  } catch {
    return null;
  }
}

// ─── Web Notifications helpers ────────────────────────────────────────

export async function requestNotificationPermission(): Promise<boolean> {
  if (typeof Notification === "undefined") return false;
  if (Notification.permission === "granted") return true;
  if (Notification.permission === "denied") return false;
  const res = await Notification.requestPermission();
  return res === "granted";
}

export function notify(title: string, body: string) {
  try {
    if (typeof Notification === "undefined") return;
    if (Notification.permission === "granted") {
      new Notification(title, { body });
    }
  } catch {
    /* noop */
  }
}
