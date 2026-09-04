/**
 * The control that opens the assistant, and the ⌘K binding behind it.
 *
 * It lives in the top bar rather than floating over the map. Every route
 * here already puts something in the bottom-right corner — the camera
 * presets on the globe, scrolling content everywhere else — so a floating
 * action button has nowhere to sit that does not cover something. The top
 * bar is present on every route and has room.
 *
 * Renders nothing when the backend reports the assistant is unconfigured,
 * rather than offering a button that can only produce an error.
 */
import { useEffect } from "react";

import { useAssistantStore } from "@/stores/assistant";

import { useAssistantHealth } from "./useAssistant";

export function AssistantTrigger() {
  const health = useAssistantHealth();
  const open = useAssistantStore((s) => s.open);
  const toggle = useAssistantStore((s) => s.toggle);

  const available = Boolean(health.data?.enabled && health.data?.configured);

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

  if (!available) return null;

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
