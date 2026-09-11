/**
 * The Settings panel: where API keys are entered.
 *
 * Two sections, because there are two kinds of key. "Your keys" stay in this
 * browser: the Cesium Ion token the globe needs, and an OpenRouter key of the
 * visitor's own that travels with each question and is never stored on the
 * server. "Server keys" are the owner's, one set for the whole deployment;
 * they are saved to the backend and, when the deployment has an admin token,
 * only with it. Each field says what it unlocks and links to where the key
 * comes from. Values are masked by default and shown on request.
 */
import { useEffect, useId, useRef, useState } from "react";

import {
  BROWSER_KEY_NAMES,
  KEY_DEFS,
  type KeyName,
  type Keys,
  SERVER_KEY_NAMES,
  type ServerKeyName,
  type ServerStatus,
} from "@/lib/keys";
import { useKeysStore } from "@/stores/keys";

const mono: React.CSSProperties = {
  fontFamily: "var(--font-data)",
  fontSize: 10,
  letterSpacing: "0.18em",
  textTransform: "uppercase",
};
const button = (active: boolean): React.CSSProperties => ({
  ...mono,
  padding: "9px 18px",
  borderRadius: "var(--radius-pill)",
  border: "1px solid var(--color-ember-500)",
  background: active ? "var(--color-ember-500)" : "transparent",
  color: active ? "#0b0e14" : "var(--color-text-low)",
  cursor: active ? "pointer" : "default",
  fontWeight: 700,
});
const inputStyle: React.CSSProperties = {
  flex: 1,
  width: "100%",
  fontFamily: "var(--font-data)",
  fontSize: 12.5,
  padding: "9px 11px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--color-stroke)",
  background: "var(--color-bg-0)",
  color: "var(--color-text-hi)",
  outline: "none",
};
const smallButton: React.CSSProperties = {
  ...mono,
  padding: "0 12px",
  borderRadius: "var(--radius-sm)",
  border: "1px solid var(--color-stroke)",
  background: "transparent",
  color: "var(--color-text-mid)",
  cursor: "pointer",
};

type Note = { tone: "ok" | "warn"; text: string } | null;

export function SettingsPanel() {
  const open = useKeysStore((s) => s.panelOpen);
  if (!open) return null;
  return <PanelBody />;
}

function PanelBody() {
  const close = useKeysStore((s) => s.closePanel);
  const status = useKeysStore((s) => s.status);
  const offline = useKeysStore((s) => s.offline);
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
          width: "min(680px, 100%)",
          maxHeight: "min(90vh, 900px)",
          overflowY: "auto",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-stroke-strong)",
          boxShadow: "var(--shadow-elevated)",
          padding: 24,
          display: "grid",
          gap: 22,
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

        <BrowserSection firstInput={firstInput} />
        <ServerSection status={status} offline={offline} />
      </div>
    </div>
  );
}

// ── the visitor's keys ───────────────────────────────────────────────────

function BrowserSection({
  firstInput,
}: {
  firstInput: React.RefObject<HTMLInputElement>;
}) {
  const keys = useKeysStore((s) => s.keys);
  const save = useKeysStore((s) => s.saveBrowserKeys);
  const [draft, setDraft] = useState<Keys>(keys);
  const [note, setNote] = useState<Note>(null);
  const dirty = BROWSER_KEY_NAMES.some((n) => draft[n] !== keys[n]);
  const cesiumWillChange = draft.cesium_ion_token !== keys.cesium_ion_token;

  const onSave = () => {
    const result = save({
      cesium_ion_token: draft.cesium_ion_token.trim(),
      openrouter_api_key: draft.openrouter_api_key.trim(),
    });
    setNote(
      result.ok
        ? {
            tone: "ok",
            text: result.reloading
              ? "Saved. Reloading so the globe picks up the new Cesium token…"
              : "Saved in this browser.",
          }
        : { tone: "warn", text: result.message },
    );
  };

  return (
    <Section
      kicker="Your keys"
      title="Stay in this browser"
      intro="Used by this browser only. Your OpenRouter key travels with each question you ask and is never stored on the server."
    >
      {BROWSER_KEY_NAMES.map((name, i) => (
        <KeyField
          key={name}
          name={name}
          value={draft[name]}
          onChange={(v) => setDraft({ ...draft, [name]: v })}
          set={Boolean(keys[name])}
          inputRef={i === 0 ? firstInput : undefined}
        />
      ))}
      {cesiumWillChange && (
        <Hint>
          Changing the Cesium token reloads the page, so the globe starts with the new one.
        </Hint>
      )}
      <Footer note={note}>
        <button type="button" onClick={onSave} disabled={!dirty} style={button(dirty)}>
          Save my keys
        </button>
      </Footer>
    </Section>
  );
}

// ── the owner's keys ─────────────────────────────────────────────────────

const blankServerDraft = (): Record<ServerKeyName, string> => ({
  firms_map_key: "",
  waqi_token: "",
  openrouter_api_key: "",
});
const blankClear = (): Record<ServerKeyName, boolean> => ({
  firms_map_key: false,
  waqi_token: false,
  openrouter_api_key: false,
});

function ServerSection({ status, offline }: { status: ServerStatus | null; offline: boolean }) {
  const save = useKeysStore((s) => s.saveServerKeys);
  const [draft, setDraft] = useState(blankServerDraft);
  const [clear, setClear] = useState(blankClear);
  const [adminToken, setAdminToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<Note>(null);

  const changes: Partial<Record<ServerKeyName, string>> = {};
  for (const name of SERVER_KEY_NAMES) {
    if (clear[name]) changes[name] = "";
    else if (draft[name].trim()) changes[name] = draft[name].trim();
  }
  const dirty = Object.keys(changes).length > 0;
  const needsToken = Boolean(status?.writeProtected);
  const canSave = dirty && !busy && (!needsToken || adminToken.trim().length > 0);

  const onSave = async () => {
    setBusy(true);
    setNote(null);
    const result = await save(changes, adminToken.trim());
    setBusy(false);
    if (result.ok) {
      setDraft(blankServerDraft());
      setClear(blankClear());
      setNote({
        tone: "ok",
        text: "Saved on the server. A layer waiting on a new key fills in within a minute.",
      });
    } else {
      setNote({ tone: "warn", text: result.message });
    }
  };

  return (
    <Section
      kicker="Server keys · owner only"
      title="One set for this deployment"
      intro="These run the scheduled data pulls and act as the assistant's default key. They are saved on the server and never shown again; this browser does not keep a copy."
    >
      {offline && <Hint tone="warn">The API is not answering, so server status is unknown.</Hint>}
      {status && !status.writeProtected && (
        <Hint tone="warn">
          This server has no admin token, so anyone who can reach it can change these. Set
          ADMIN_TOKEN in the server's .env before exposing it to others.
        </Hint>
      )}
      {SERVER_KEY_NAMES.map((name) => (
        <KeyField
          key={name}
          name={name}
          value={draft[name]}
          onChange={(v) => setDraft({ ...draft, [name]: v })}
          set={status?.keys[name] ?? null}
          serverSide
          clearing={clear[name]}
          onToggleClear={() => setClear({ ...clear, [name]: !clear[name] })}
        />
      ))}
      {needsToken && (
        <label style={{ display: "grid", gap: 6 }}>
          <span style={{ ...mono, color: "var(--color-text-mid)" }}>Admin token</span>
          <input
            type="password"
            autoComplete="off"
            value={adminToken}
            onChange={(e) => setAdminToken(e.target.value)}
            placeholder="Required to change server keys"
            style={inputStyle}
          />
        </label>
      )}
      <Footer note={note}>
        <button type="button" onClick={onSave} disabled={!canSave} style={button(canSave)}>
          {busy ? "Saving…" : "Save server keys"}
        </button>
      </Footer>
    </Section>
  );
}

// ── pieces ───────────────────────────────────────────────────────────────

function Section({
  kicker,
  title,
  intro,
  children,
}: {
  kicker: string;
  title: string;
  intro: string;
  children: React.ReactNode;
}) {
  return (
    <section
      style={{
        display: "grid",
        gap: 12,
        padding: "16px 18px",
        borderRadius: "var(--radius-md)",
        border: "1px solid var(--color-stroke)",
        background: "var(--color-bg-1)",
      }}
    >
      <div>
        <div style={{ ...mono, color: "var(--color-ember-400)" }}>{kicker}</div>
        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 16,
            fontWeight: 700,
            color: "var(--color-text-hi)",
            marginTop: 4,
          }}
        >
          {title}
        </div>
        <p
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 12.5,
            lineHeight: 1.5,
            color: "var(--color-text-mid)",
            margin: "6px 0 0",
          }}
        >
          {intro}
        </p>
      </div>
      {children}
    </section>
  );
}

function KeyField({
  name,
  value,
  onChange,
  set,
  inputRef,
  serverSide = false,
  clearing = false,
  onToggleClear,
}: {
  name: KeyName;
  value: string;
  onChange: (v: string) => void;
  /** Whether a value is currently stored; null while unknown. */
  set: boolean | null;
  inputRef?: React.RefObject<HTMLInputElement>;
  serverSide?: boolean;
  clearing?: boolean;
  onToggleClear?: () => void;
}) {
  const def = KEY_DEFS[name];
  const [shown, setShown] = useState(false);
  const id = `key-${serverSide ? "server-" : ""}${name}`;
  return (
    <div style={{ display: "grid", gap: 7 }}>
      <div style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
        <label
          htmlFor={id}
          style={{
            fontFamily: "var(--font-body)",
            fontSize: 13.5,
            fontWeight: 600,
            color: "var(--color-text-hi)",
            flex: 1,
          }}
        >
          {def.label}
        </label>
        <StatusPill set={set} />
      </div>
      <div
        style={{
          fontFamily: "var(--font-body)",
          fontSize: 12,
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
          id={id}
          ref={inputRef}
          type={shown ? "text" : "password"}
          autoComplete="off"
          spellCheck={false}
          value={value}
          disabled={clearing}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            clearing ? "Will be cleared on save" : set ? "Set — paste to replace" : "Paste key"
          }
          style={{ ...inputStyle, opacity: clearing ? 0.5 : 1 }}
        />
        <button
          type="button"
          onClick={() => setShown((v) => !v)}
          aria-pressed={shown}
          // The OpenRouter key has a field in both sections; the label says which.
          aria-label={`${shown ? "Hide" : "Show"} ${def.label}${serverSide ? " on the server" : ""}`}
          style={smallButton}
        >
          {shown ? "Hide" : "Show"}
        </button>
        {serverSide && set && onToggleClear && (
          <button type="button" onClick={onToggleClear} aria-pressed={clearing} style={smallButton}>
            {clearing ? "Keep" : "Clear"}
          </button>
        )}
      </div>
    </div>
  );
}

function StatusPill({ set }: { set: boolean | null }) {
  const on = set === true;
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
      {set === null ? "Unknown" : on ? "Set" : "Not set"}
    </span>
  );
}

function Hint({ children, tone = "info" }: { children: React.ReactNode; tone?: "info" | "warn" }) {
  return (
    <p
      style={{
        fontFamily: "var(--font-body)",
        fontSize: 12,
        lineHeight: 1.45,
        color: tone === "warn" ? "var(--color-ember-400)" : "var(--color-text-mid)",
        margin: 0,
      }}
    >
      {children}
    </p>
  );
}

function Footer({ note, children }: { note: Note; children: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 12,
        justifyContent: "flex-end",
        flexWrap: "wrap",
      }}
    >
      {note && (
        <output
          style={{
            flex: 1,
            minWidth: 200,
            fontFamily: "var(--font-body)",
            fontSize: 12.5,
            color: note.tone === "ok" ? "var(--risk-low)" : "var(--color-ember-400)",
          }}
        >
          {note.text}
        </output>
      )}
      {children}
    </div>
  );
}
