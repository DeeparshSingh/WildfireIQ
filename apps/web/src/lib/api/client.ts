/**
 * Minimal HTTP client for the FastAPI backend. The base URL comes from
 * VITE_API_BASE_URL (defaults to http://localhost:8000 in dev).
 */
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type Meta = {
  cached_at: string;
  source: string;
  attribution: string;
  phase: string;
  note?: string | null;
};

export type Envelope<T> = { data: T; meta: Meta };

export async function apiGet<T>(path: string): Promise<Envelope<T>> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { Accept: "application/json" },
  });
  if (!res.ok) {
    throw new Error(`API ${path} failed: HTTP ${res.status}`);
  }
  return (await res.json()) as Envelope<T>;
}
