/**
 * Minimal HTTP client for the FastAPI backend. The base URL comes from
 * VITE_API_BASE_URL (defaults to http://localhost:8000 in dev).
 */
const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

/** Exported for the assistant, which streams SSE rather than using apiGet. */
export const API_BASE = BASE;

type Meta = {
  cached_at: string;
  source: string;
  attribution: string;
  note?: string | null;
};

export type Envelope<T> = { data: T; meta: Meta };

/** Thrown when the backend is unreachable, as opposed to answering with an error. */
export class ApiUnreachableError extends Error {
  readonly path: string;
  constructor(path: string, cause: unknown) {
    super(`Cannot reach the API at ${BASE}`, { cause });
    this.name = "ApiUnreachableError";
    this.path = path;
  }
}

/** Thrown when the backend answered, but not with a success status. */
export class ApiResponseError extends Error {
  readonly path: string;
  readonly status: number;
  constructor(path: string, status: number) {
    super(`API ${path} failed: HTTP ${status}`);
    this.name = "ApiResponseError";
    this.path = path;
    this.status = status;
  }
}

export async function apiGet<T>(path: string): Promise<Envelope<T>> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { Accept: "application/json" },
    });
  } catch (cause) {
    // fetch only rejects when the request never completed — the server is
    // down, DNS failed, or CORS blocked it. Worth distinguishing from a 500,
    // because the two need different things from the reader.
    throw new ApiUnreachableError(path, cause);
  }
  if (!res.ok) {
    throw new ApiResponseError(path, res.status);
  }
  return (await res.json()) as Envelope<T>;
}
