/**
 * The banner a route shows when one of its data sources did not load.
 *
 * Before this existed, a failed fetch produced no message at all: the cards
 * still rendered, the numbers were replaced by em-dashes, and the reader was
 * left to work out whether the air really was that clean or the backend was
 * simply down. For a tool people might consult during a smoke event, silence
 * is the wrong failure mode — say what is missing and offer to try again.
 *
 * Deliberately a banner rather than a replacement for the page. The routes
 * already degrade to em-dashes and empty charts, and a partial page with an
 * honest note on top is more useful than an error screen that hides the
 * sections which did load.
 */
import { type QueryClient, onlineManager, useQueryClient } from "@tanstack/react-query";

import { ApiUnreachableError } from "@/lib/api/client";

/** The slice of a TanStack query this component needs. */
export type NoticeQuery = {
  isError: boolean;
  error: unknown;
  isFetching: boolean;
  fetchStatus: "fetching" | "paused" | "idle";
  refetch: () => unknown;
};

/**
 * Queries worth telling the reader about.
 *
 * Two different failures, and the second is the one that nearly slipped
 * through. A query that errors is obvious. A query that TanStack *pauses* is
 * not: when its online manager decides the network is unavailable it suspends
 * retries, and the query sits in `pending` — never `isError` — for as long as
 * that lasts. Keying only on `isError` would have shown nothing at all in the
 * case that matters most, a reader on a dropped or captive-portal connection
 * during a smoke event.
 */
function troubled(queries: NoticeQuery[]): NoticeQuery[] {
  return queries.filter((q) => q.isError || q.fetchStatus === "paused");
}

function isUnreachable(queries: NoticeQuery[]): boolean {
  return queries.some((q) => q.error instanceof ApiUnreachableError);
}

function isPaused(queries: NoticeQuery[]): boolean {
  return queries.some((q) => q.fetchStatus === "paused");
}

/**
 * What the Retry button does.
 *
 * `refetch()` is not enough, and the reason took measuring to find. Every
 * query this app pauses has a `refetchInterval` — the live ones: AQHI, fires,
 * evacuations, the risk grid. Once such a query is paused, neither `refetch()`
 * nor `refetchQueries()` revives it; it sits in `pending`/`paused` while the
 * two interval-free queries beside it recover, which is exactly the half-dead
 * page this notice exists to explain. `resetQueries` drops that paused state
 * and starts the fetch again from scratch, which does work.
 *
 * Scoped by predicate to the queries actually in trouble, so a retry does not
 * throw away good data that is already on screen.
 */
function retryAll(client: QueryClient): void {
  // Harmless when already online, and the thing that matters when genuinely
  // offline and the browser has not yet noticed the connection returning.
  onlineManager.setOnline(true);
  void client.resetQueries({
    predicate: (q) => q.state.fetchStatus === "paused" || q.state.status === "error",
  });
}

export function DataNotice({
  queries,
  what,
}: {
  queries: NoticeQuery[];
  /** What this route is missing, e.g. "air-quality data". */
  what: string;
}) {
  const client = useQueryClient();
  const failed = troubled(queries);
  if (failed.length === 0) return null;

  const retrying = failed.some((q) => q.isFetching);
  const paused = isPaused(failed);
  const unreachable = isUnreachable(failed);

  const headline = paused
    ? "Waiting for a connection"
    : unreachable
      ? "Cannot reach the WildfireIQ API"
      : `Could not load ${what}`;
  const detail = paused
    ? "Your browser reports no network, so retries are on hold. This page will fill in by itself once the connection returns."
    : unreachable
      ? "The backend is not responding. If you are running this locally, start it with ./start.sh — the page will fill in once it answers."
      : `${failed.length} of this page's data sources returned an error. Anything already shown is from the last successful load.`;

  return (
    <output
      className="glass"
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 14,
        padding: "12px 16px",
        marginBottom: 20,
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-ember-500)",
        borderLeftWidth: 3,
      }}
    >
      <span aria-hidden="true" style={{ color: "var(--color-ember-500)", fontSize: 15 }}>
        ⚠
      </span>
      <div style={{ flex: 1, minWidth: 220, display: "grid", gap: 3 }}>
        <div
          style={{
            fontFamily: "var(--font-data)",
            fontSize: 11,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--color-text-hi)",
          }}
        >
          {headline}
        </div>
        <div
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 12.5,
            lineHeight: 1.45,
            color: "var(--color-text-mid)",
          }}
        >
          {detail}
        </div>
      </div>
      <button
        type="button"
        onClick={() => retryAll(client)}
        disabled={retrying}
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 11,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          padding: "7px 14px",
          borderRadius: "var(--radius-pill)",
          border: "1px solid var(--color-ember-500)",
          background: "transparent",
          color: retrying ? "var(--color-text-low)" : "var(--color-text-hi)",
          cursor: retrying ? "default" : "pointer",
        }}
      >
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </output>
  );
}

/**
 * The globe's variant. The layer panel is a narrow floating column, so this
 * is a single line that matches its width rather than a full-width banner.
 */
export function GlobeDataNotice({ queries }: { queries: NoticeQuery[] }) {
  const client = useQueryClient();
  const failed = troubled(queries);
  if (failed.length === 0) return null;

  const retrying = failed.some((q) => q.isFetching);
  const unreachable = isUnreachable(failed) || isPaused(failed);

  return (
    <output
      className="glass"
      style={{
        display: "grid",
        gap: 6,
        width: 232,
        padding: "10px 12px",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-ember-500)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 10,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--color-text-hi)",
        }}
      >
        {unreachable ? "⚠ API unreachable" : `⚠ ${failed.length} of 6 layers failed`}
      </div>
      <div
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 11.5,
          lineHeight: 1.4,
          color: "var(--color-text-mid)",
        }}
      >
        {unreachable
          ? "The globe is drawing, but its data layers are empty."
          : "Those layers are empty, not clear."}
      </div>
      <button
        type="button"
        onClick={() => retryAll(client)}
        disabled={retrying}
        style={{
          justifySelf: "start",
          fontFamily: "var(--font-data)",
          fontSize: 10,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          padding: "5px 11px",
          borderRadius: "var(--radius-pill)",
          border: "1px solid var(--color-ember-500)",
          background: "transparent",
          color: retrying ? "var(--color-text-low)" : "var(--color-text-hi)",
          cursor: retrying ? "default" : "pointer",
        }}
      >
        {retrying ? "Retrying…" : "Retry"}
      </button>
    </output>
  );
}
