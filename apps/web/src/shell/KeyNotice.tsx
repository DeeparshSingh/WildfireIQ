/**
 * A quiet, one-line notice that a feature is waiting on an API key.
 *
 * Sits exactly where the feature would be — under the hotspots toggle, in
 * the pollutant card, on the assistant button — and does one thing: names
 * the key and opens the Settings panel. It disappears on its own once the
 * backend reports the key is in place, so no one has to dismiss it.
 */
import { KEY_DEFS, type KeyName } from "@/lib/keys";
import { useKeyMissing, useKeysStore } from "@/stores/keys";

export function KeyNotice({
  keyName,
  what,
  compact = false,
}: {
  keyName: KeyName;
  /** What is missing, in the reader's words, e.g. "Satellite hotspots". */
  what: string;
  compact?: boolean;
}) {
  const missing = useKeyMissing(keyName);
  const openPanel = useKeysStore((s) => s.openPanel);
  if (!missing) return null;

  const def = KEY_DEFS.find((d) => d.name === keyName);
  const provider = def?.provider ?? "an API";

  return (
    <div
      className="glass"
      role="note"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: compact ? "7px 11px" : "10px 14px",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-stroke)",
        borderLeft: "2px solid var(--color-ember-500)",
        maxWidth: compact ? 240 : undefined,
      }}
    >
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontFamily: "var(--font-data)",
            fontSize: compact ? 9.5 : 10,
            letterSpacing: "0.16em",
            textTransform: "uppercase",
            color: "var(--color-text-hi)",
          }}
        >
          {what} needs a {provider} key
        </div>
        {!compact && (
          <div
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 12,
              color: "var(--color-text-mid)",
              marginTop: 3,
              lineHeight: 1.4,
            }}
          >
            Everything else keeps working. Add the key to switch this on.
          </div>
        )}
      </div>
      <button
        type="button"
        onClick={openPanel}
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 9.5,
          letterSpacing: "0.16em",
          textTransform: "uppercase",
          padding: "5px 10px",
          borderRadius: "var(--radius-pill)",
          border: "1px solid var(--color-ember-500)",
          background: "transparent",
          color: "var(--color-text-hi)",
          cursor: "pointer",
          whiteSpace: "nowrap",
        }}
      >
        Enter key
      </button>
    </div>
  );
}
