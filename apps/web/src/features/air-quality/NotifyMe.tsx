/**
 * Web Notification subscription for AQHI threshold alerts.
 * Subscription state lives entirely in localStorage — no backend, no PII.
 *
 * Behaviour:
 *   • User picks a threshold (4–10) and toggles "Notify me" on
 *   • A polling effect checks the current AQHI every 60 s while the tab is
 *     visible. If AQHI ≥ threshold and ≥ 60 minutes have passed since the
 *     last notification, fire a Web Notification
 *   • Notifications only fire while a tab is open — acceptable for a
 *     research demo. No service worker, no FCM, no cost.
 */
import { useCallback, useEffect, useMemo, useState } from "react";

const STORAGE_KEY = "wildfireiq.aqhi-notify.v1";

type Settings = {
  enabled: boolean;
  threshold: number;
  lastNotifiedAt: string | null;
};

function read(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { ...defaults(), ...JSON.parse(raw) };
  } catch {
    /* ignore */
  }
  return defaults();
}
function defaults(): Settings {
  return { enabled: false, threshold: 7, lastNotifiedAt: null };
}
function write(s: Settings) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export function NotifyMe({ currentAqhi }: { currentAqhi: number | null }) {
  const [settings, setSettings] = useState<Settings>(() => read());
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(
    () => (typeof Notification !== "undefined" ? Notification.permission : "unsupported"),
  );

  const apply = useCallback((patch: Partial<Settings>) => {
    setSettings((curr) => {
      const next = { ...curr, ...patch };
      write(next);
      return next;
    });
  }, []);

  const requestPermission = useCallback(async () => {
    if (typeof Notification === "undefined") return;
    const result = await Notification.requestPermission();
    setPermission(result);
  }, []);

  // Fire the notification if conditions are met.
  useEffect(() => {
    if (!settings.enabled) return;
    if (permission !== "granted") return;
    if (currentAqhi == null) return;
    if (currentAqhi < settings.threshold) return;
    const last = settings.lastNotifiedAt ? new Date(settings.lastNotifiedAt).getTime() : 0;
    if (Date.now() - last < 60 * 60_000) return;
    try {
      new Notification("WildfireIQ · AQHI alert", {
        body: `Kamloops AQHI is ${currentAqhi}. Your threshold is ${settings.threshold}.`,
        tag: "wildfireiq-aqhi",
      });
      apply({ lastNotifiedAt: new Date().toISOString() });
    } catch {
      /* notifications can throw inside cross-origin iframes; non-fatal */
    }
  }, [settings, permission, currentAqhi, apply]);

  const status = useMemo(() => {
    if (permission === "unsupported") return "Browser does not support notifications";
    if (permission === "denied") return "Notifications blocked. Enable them in browser settings.";
    if (permission === "default") return "Browser permission required";
    return settings.enabled ? "Active" : "Off";
  }, [permission, settings.enabled]);

  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        alignItems: "center",
        gap: 14,
        padding: "12px 16px",
        borderRadius: "var(--radius-md)",
        background: "var(--color-bg-1)",
        border: "1px solid var(--color-stroke)",
      }}
    >
      <div style={{ flex: 1, minWidth: 200 }}>
        <div
          style={{
            fontFamily: "var(--font-display)",
            fontSize: 14,
            color: "var(--color-text-hi)",
            fontWeight: 600,
          }}
        >
          Notify me when AQHI ≥{" "}
          <span className="tabular" style={{ color: "var(--color-ember-500)" }}>
            {settings.threshold}
          </span>
        </div>
        <div
          style={{
            marginTop: 2,
            fontFamily: "var(--font-data)",
            fontSize: 10,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
            color: "var(--color-text-low)",
          }}
        >
          {status}
        </div>
      </div>

      <input
        type="range"
        min={4}
        max={10}
        value={settings.threshold}
        onChange={(e) => apply({ threshold: Number(e.target.value) })}
        aria-label="AQHI threshold"
        style={{
          width: 140,
          accentColor: "var(--color-ember-500)",
        }}
      />

      {permission === "default" && (
        <button
          type="button"
          onClick={requestPermission}
          style={{
            padding: "6px 14px",
            background: "var(--color-ember-500)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            cursor: "pointer",
            fontFamily: "var(--font-data)",
            fontSize: 11,
            letterSpacing: "0.18em",
            textTransform: "uppercase",
          }}
        >
          Allow
        </button>
      )}

      <button
        type="button"
        onClick={() => apply({ enabled: !settings.enabled })}
        disabled={permission !== "granted"}
        aria-pressed={settings.enabled}
        style={{
          padding: "6px 14px",
          background: settings.enabled ? "var(--color-ember-500)" : "transparent",
          color: settings.enabled ? "white" : "var(--color-text-mid)",
          border: `1px solid ${
            settings.enabled ? "var(--color-ember-500)" : "var(--color-stroke)"
          }`,
          borderRadius: "var(--radius-md)",
          cursor: permission === "granted" ? "pointer" : "not-allowed",
          opacity: permission === "granted" ? 1 : 0.5,
          fontFamily: "var(--font-data)",
          fontSize: 11,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
        }}
      >
        {settings.enabled ? "Notify on" : "Notify off"}
      </button>
    </div>
  );
}
