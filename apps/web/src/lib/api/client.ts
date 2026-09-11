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

/**
 * Thrown when the owner has paused or restricted the deployment.
 *
 * Worth its own type: a 503 here is not a fault, it is a decision, and it
 * carries the owner's own wording for why. Telling a reader "something went
 * wrong" when the answer is "the owner took it down for an hour" is the kind
 * of error message that wastes everybody's time.
 */
export class ServicePausedError extends Error {
  readonly state: string;
  constructor(message: string, state: string) {
    super(message);
    this.name = "ServicePausedError";
    this.state = state;
  }
}

async function pausedFrom(res: Response): Promise<ServicePausedError | null> {
  if (res.status !== 503) return null;
  try {
    const body = await res.clone().json();
    if (body && typeof body.state === "string" && body.state !== "running") {
      return new ServicePausedError(
        String(body.detail || "This deployment is paused."),
        body.state,
      );
    }
  } catch {
    // A 503 from something other than the owner control middleware, e.g. a
    // reverse proxy with no body. Falls through to the generic error.
  }
  return null;
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
    const paused = await pausedFrom(res);
    if (paused) throw paused;
    throw new ApiResponseError(path, res.status);
  }
  return (await res.json()) as Envelope<T>;
}
