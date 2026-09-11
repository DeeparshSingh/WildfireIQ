/**
 * Owner control, from the browser.
 *
 * `GET /api/ownership` is public and answers even while the deployment is
 * paused, so this is safe to call on every page load: it is how the app knows
 * whose deployment it is and whether the owner has taken it down.
 *
 * Changing the state needs the admin token, which is the everyday route. The
 * stronger route is a command signed with the owner's key, which this file
 * can also post — the signature is what authorises it, so the token is not
 * needed and the command can be pasted in from anywhere.
 */
import { API_BASE } from "@/lib/api/client";

export type ServiceState = "running" | "readonly" | "paused";

export type Ownership = {
  owner: string;
  keyFingerprint: string;
  state: ServiceState;
  message: string;
  /** Which delivery route the standing command arrived by. */
  commandSource: string;
  problems: string[];
};

type Envelope = {
  data: {
    owner: string;
    key_fingerprint: string;
    state: ServiceState;
    message: string;
    command_source: string;
    problems: string[];
  };
};

function shape(env: Envelope): Ownership {
  const d = env.data;
  return {
    owner: d.owner,
    keyFingerprint: d.key_fingerprint,
    state: d.state,
    message: d.message,
    commandSource: d.command_source,
    problems: d.problems ?? [],
  };
}

export async function fetchOwnership(): Promise<Ownership> {
  const res = await fetch(`${API_BASE}/api/ownership`, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`ownership failed: HTTP ${res.status}`);
  return shape((await res.json()) as Envelope);
}

export class AdminTokenRejected extends Error {
  constructor() {
    super("The admin token did not match.");
    this.name = "AdminTokenRejected";
  }
}

/** Pause, restrict or resume using the admin token. */
export async function setServiceState(
  state: ServiceState,
  message: string,
  adminToken: string,
): Promise<ServiceState> {
  const res = await fetch(`${API_BASE}/api/ownership/state`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      "X-Admin-Token": adminToken,
    },
    body: JSON.stringify({ state, message }),
  });
  if (res.status === 401) throw new AdminTokenRejected();
  if (!res.ok) throw new Error(`ownership/state failed: HTTP ${res.status}`);
  return (await res.json()).data.state as ServiceState;
}

/** Apply a command signed with the owner's key. No admin token needed. */
export async function applySignedCommand(command: string): Promise<ServiceState> {
  const res = await fetch(`${API_BASE}/api/ownership/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify({ command }),
  });
  if (res.status === 403) {
    const body = await res.json().catch(() => ({}));
    throw new Error(String(body.detail || "That command was refused."));
  }
  if (!res.ok) throw new Error(`ownership/command failed: HTTP ${res.status}`);
  return (await res.json()).data.state as ServiceState;
}
