/**
 * The Settings panel: where the reader enters the four API keys.
 *
 * One dialog, four fields, one Save. Each field says what it unlocks and
 * links to where the key comes from, so a first-time reader can go from
 * "the hotspots layer is empty" to a working layer without leaving the app
 * or opening a file. The values are masked by default and shown on request.
 *
 * Keys live in this browser's local storage and are pushed to the backend,
 * which the panel states plainly, since a reader deciding whether to paste
 * a key deserves to know where it goes.
 */
import { useEffect, useId, useRef, useState } from "react";

import { KEY_DEFS, type KeyName, type Keys } from "@/lib/keys";
import { useKeysStore } from "@/stores/keys";

const mono: React.CSSProperties = {
  fontFamily: "var(--font-data)",
  fontSize: 10,
  letterSpacing: "0.18em",
  textTransform: "uppercase",
};

export function SettingsPanel() {
  const open = useKeysStore((s) => s.panelOpen);
  if (!open) return null;
  return <PanelBody />;
}

function PanelBody() {
  const keys = useKeysStore((s) => s.keys);
  const status = useKeysStore((s) => s.status);
  const offline = useKeysStore((s) => s.offline);
  const close = useKeysStore((s) => s.closePanel);
  const save = useKeysStore((s) => s.save);

  const [draft, setDraft] = useState<Keys>(keys);
  const [shown, setShown] = useState<Record<KeyName, boolean>>({
    cesium_ion_token: false,
    firms_map_key: false,
    waqi_token: false,
    openrouter_api_key: false,
  });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "ok" | "warn"; text: string } | null>(null);
  const titleId = useId();
  const firstInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    firstInput.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [close]);

  const dirty = KEY_DEFS.some((d) => draft[d.name] !== keys[d.name]);
  const cesiumWillChange = draft.cesium_ion_token !== keys.cesium_ion_token;

  const onSave = async () => {
    setBusy(true);
    setNote(null);
    const trimmed = Object.fromEntries(KEY_DEFS.map((d) => [d.name, draft[d.name].trim()])) as Keys;
    const result = await save(trimmed);
    setBusy(false);
    if (result.ok) {
      setNote({
        tone: "ok",
        text: result.reloading
          ? "Saved. Reloading so the globe picks up the new Cesium token…"
          : "Saved. Features that were waiting on a key will fill in within a minute.",
      });
      if (!result.reloading) window.setTimeout(close, 900);
    } else {
      setNote({ tone: "warn", text: result.message });
    }
  };

  return (
    <div
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget) close();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") close();
      }}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 60,
        display: "grid",
        placeItems: "center",
        padding: 24,
        background: "hsl(220 30% 3% / 0.72)",
        backdropFilter: "blur(6px)",
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="glass-strong"
        style={{
          width: "min(640px, 100%)",
          maxHeight: "min(88vh, 820px)",
          overflowY: "auto",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-stroke-strong)",
          boxShadow: "var(--shadow-elevated)",
          padding: 24,
          display: "grid",
          gap: 18,
        }}
      >
        <header style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
          <div style={{ flex: 1 }}>
            <div style={{ ...mono, color: "var(--color-cyan-glow)" }}>Settings</div>
            <h2
              id={titleId}
              style={{
                fontFamily: "var(--font-display)",
                fontSize: 22,
                fontWeight: 700,
                letterSpacing: "-0.02em",
                margin: "6px 0 0",
                color: "var(--color-text-hi)",
              }}
            >
              API keys
            </h2>
            <p
              style={{
                fontFamily: "var(--font-body)",
                fontSize: 13,
                lineHeight: 1.5,
                color: "var(--color-text-mid)",
                margin: "8px 0 0",
                maxWidth: "58ch",
              }}
            >
              Each key switches on one feature. The platform works without any of them. Keys are
              kept in this browser and sent to this app's own backend, which runs the scheduled data
              pulls and the assistant. They are never shown again once saved and never included in a
              share link.
            </p>
          </div>
          <button
            type="button"
            onClick={close}
            aria-label="Close settings"
            style={{
              border: "1px solid var(--color-stroke)",
              background: "transparent",
              color: "var(--color-text-mid)",
              width: 30,
              height: 30,
              borderRadius: "var(--radius-md)",
              cursor: "pointer",
              fontSize: 16,
              lineHeight: 1,
            }}
          >
            ×
          </button>
        </header>

        {offline && (
          <div
            style={{
              ...mono,
              color: "var(--color-ember-400)",
              padding: "8px 12px",
              border: "1px solid var(--color-ember-700)",
              borderRadius: "var(--radius-md)",
            }}
          >
            The API is not answering. Keys still save in this browser.
          </div>
        )}

        <div style={{ display: "grid", gap: 14 }}>
          {KEY_DEFS.map((def, i) => {
            const configured = status?.[def.name] ?? null;
            const localSet = Boolean(keys[def.name]);
            return (
              <div
                key={def.name}
                style={{
                  display: "grid",
                  gap: 8,
                  padding: "14px 16px",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-stroke)",
                  background: "var(--color-bg-1)",
                }}
              >
                <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
                  <label
                    htmlFor={`key-${def.name}`}
                    style={{
                      fontFamily: "var(--font-body)",
                      fontSize: 14,
                      fontWeight: 600,
                      color: "var(--color-text-hi)",
                      flex: 1,
                    }}
                  >
                    {def.label}
                  </label>
                  <StatusPill configured={configured} localSet={localSet} />
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-body)",
                    fontSize: 12.5,
                    color: "var(--color-text-mid)",
                    lineHeight: 1.45,
                  }}
                >
                  Unlocks {def.unlocks}.{" "}
                  <a
                    href={def.url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: "var(--color-cyan-glow)", textDecoration: "none" }}
                  >
                    Get one from {def.provider} ↗
                  </a>
                </div>
                <div style={{ display: "flex", gap: 8 }}>
                  <input
                    id={`key-${def.name}`}
                    ref={i === 0 ? firstInput : undefined}
                    type={shown[def.name] ? "text" : "password"}
                    autoComplete="off"
                    spellCheck={false}
                    value={draft[def.name]}
                    onChange={(e) => setDraft({ ...draft, [def.name]: e.target.value })}
                    placeholder={
                      localSet ? "Saved — paste to replace, clear to remove" : "Paste key"
                    }
                    style={{
                      flex: 1,
                      fontFamily: "var(--font-data)",
                      fontSize: 12.5,
                      padding: "9px 11px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--color-stroke)",
                      background: "var(--color-bg-0)",
                      color: "var(--color-text-hi)",
                      outline: "none",
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShown({ ...shown, [def.name]: !shown[def.name] })}
                    aria-pressed={shown[def.name]}
                    aria-label={shown[def.name] ? "Hide key" : "Show key"}
                    style={{
                      ...mono,
                      padding: "0 12px",
                      borderRadius: "var(--radius-sm)",
                      border: "1px solid var(--color-stroke)",
                      background: "transparent",
                      color: "var(--color-text-mid)",
                      cursor: "pointer",
                    }}
                  >
                    {shown[def.name] ? "Hide" : "Show"}
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {cesiumWillChange && (
          <p
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 12.5,
              color: "var(--color-text-mid)",
              margin: 0,
            }}
          >
            Changing the Cesium token reloads the page, so the globe starts with the new one.
          </p>
        )}

        {note && (
          <output
            style={{
              fontFamily: "var(--font-body)",
              fontSize: 13,
              color: note.tone === "ok" ? "var(--risk-low)" : "var(--color-ember-400)",
            }}
          >
            {note.text}
          </output>
        )}

        <footer style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <button
            type="button"
            onClick={close}
            style={{
              ...mono,
              padding: "9px 16px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--color-stroke)",
              background: "transparent",
              color: "var(--color-text-mid)",
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onSave}
            disabled={!dirty || busy}
            style={{
              ...mono,
              padding: "9px 18px",
              borderRadius: "var(--radius-pill)",
              border: "1px solid var(--color-ember-500)",
              background: dirty && !busy ? "var(--color-ember-500)" : "transparent",
              color: dirty && !busy ? "#0b0e14" : "var(--color-text-low)",
              cursor: dirty && !busy ? "pointer" : "default",
              fontWeight: 700,
            }}
          >
            {busy ? "Saving…" : "Save keys"}
          </button>
        </footer>
      </div>
    </div>
  );
}

function StatusPill({ configured, localSet }: { configured: boolean | null; localSet: boolean }) {
  // Server status wins when known; before the first fetch, fall back to the
  // browser's own copy so the panel is never blank on open.
  const on = configured ?? localSet;
  return (
    <span
      style={{
        ...mono,
        fontSize: 9,
        padding: "3px 8px",
        borderRadius: "var(--radius-pill)",
        background: on ? "hsl(140 55% 50% / 0.14)" : "var(--color-bg-3)",
        color: on ? "var(--risk-low)" : "var(--color-text-low)",
        whiteSpace: "nowrap",
      }}
    >
      {on ? "Configured" : "Not set"}
    </span>
  );
}
