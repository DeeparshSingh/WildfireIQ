/**
 * The control that opens the assistant, and the ⌘K binding behind it.
 *
 * It lives in the top bar rather than floating over the map. Every route
 * here already puts something in the bottom-right corner — the camera
 * presets on the globe, scrolling content everywhere else — so a floating
 * action button has nowhere to sit that does not cover something. The top
 * bar is present on every route and has room.
 *
 * When the backend reports the assistant has no key, the button stays but
 * opens the Settings panel instead — the one action that can fix it.
 */
import { useEffect } from "react";

import { useAssistantStore } from "@/stores/assistant";
import { useKeysStore, useVisitorOpenRouterKey } from "@/stores/keys";

import { useAssistantHealth } from "./useAssistant";

export function AssistantTrigger() {
  const health = useAssistantHealth();
  const open = useAssistantStore((s) => s.open);
  const toggle = useAssistantStore((s) => s.toggle);
  const openSettings = useKeysStore((s) => s.openPanel);
  const visitorKey = useVisitorOpenRouterKey();

  // Usable with the server's default key or with one the visitor brought.
  const available = Boolean(health.data?.enabled && (health.data?.configured || visitorKey));

  useEffect(() => {
    if (!available) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [available, toggle]);

  if (!available) {
    // Switched off in config: nothing to offer. No key yet: offer the panel.
    if (health.data && !health.data.enabled) return null;
    if (!health.data) return null;
    return (
      <button
        type="button"
        onClick={openSettings}
        aria-label="The assistant needs an OpenRouter key. Open settings"
        style={{
          display: "flex",
          alignItems: "center",
          gap: 8,
          height: 26,
          padding: "0 10px",
          borderRadius: "var(--radius-pill)",
          border: "1px dashed var(--color-stroke-strong)",
          background: "transparent",
          color: "var(--color-text-low)",
          fontFamily: "var(--font-data)",
          fontSize: 11,
          letterSpacing: "0.04em",
          cursor: "pointer",
        }}
      >
        Ask
        <span aria-hidden style={{ color: "var(--color-ember-400)" }}>
          · needs key
        </span>
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label="Open the WildfireIQ assistant"
      aria-expanded={open}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        height: 26,
        padding: "0 10px",
        borderRadius: "var(--radius-pill)",
        border: `1px solid ${open ? "var(--color-ember-700)" : "var(--color-stroke)"}`,
        background: open ? "hsl(18 95% 54% / 0.14)" : "transparent",
        color: open ? "var(--color-ember-200)" : "var(--color-text-mid)",
        fontFamily: "var(--font-data)",
        fontSize: 11,
        letterSpacing: "0.04em",
        cursor: "pointer",
        transition: "background 180ms, border-color 180ms, color 180ms",
      }}
    >
      <span
        aria-hidden
        style={{
          width: 6,
          height: 6,
          borderRadius: "50%",
          background: "var(--color-ember-500)",
          boxShadow: "var(--glow-ember)",
        }}
      />
      Ask
      <span aria-hidden style={{ color: "var(--color-text-low)" }}>
        ⌘K
      </span>
    </button>
  );
}
