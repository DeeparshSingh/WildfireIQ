/**
 * A quiet, one-line notice that a feature is waiting on one of the owner's
 * server keys.
 *
 * Sits exactly where the feature would be — under the hotspots toggle, in
 * the pollutant card — names the key and opens the Settings panel, where the
 * server section explains that these are the owner's to set. It disappears
 * on its own once the backend reports the key is in place.
 */
import { KEY_DEFS, type ServerKeyName } from "@/lib/keys";
import { useKeyMissing, useKeysStore } from "@/stores/keys";

export function KeyNotice({
  keyName,
  what,
  compact = false,
}: {
  keyName: ServerKeyName;
  /** What is missing, in the reader's words, e.g. "Satellite hotspots". */
  what: string;
  compact?: boolean;
}) {
  const missing = useKeyMissing(keyName);
  const openPanel = useKeysStore((s) => s.openPanel);
  if (!missing) return null;

  const provider = KEY_DEFS[keyName].provider;

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
          {what} needs a {provider} key on this server
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
            Everything else keeps working. The server owner can add the key in Settings.
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
        Settings
      </button>
    </div>
  );
}
