import { AnimatePresence, motion } from "motion/react";
/**
 * The assistant panel: transcript, composer, and the work it showed.
 *
 * Docked to the right on desktop and full-width on narrow screens. It is
 * mounted once in `AppShell`, so the conversation follows the user across
 * every route — which matters, because the assistant can navigate them.
 */
import { useEffect, useRef, useState } from "react";

import { Markdown } from "./Markdown";
import { ToolTrail } from "./ToolTrail";
import type { ChatMessage } from "./types";
import { useAssistant, useStarterPrompts } from "./useAssistant";

const PANEL_WIDTH = 400;

function Composer({
  busy,
  onSend,
  onStop,
}: {
  busy: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Grow with the content up to a few lines, then scroll. `value` is the
  // trigger rather than something the body reads, which is exactly the case
  // the exhaustive-deps rule cannot tell apart from a redundant dependency.
  // biome-ignore lint/correctness/useExhaustiveDependencies: value is the trigger, not a read
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [value]);

  const submit = () => {
    const text = value.trim();
    if (!text || busy) return;
    setValue("");
    onSend(text);
  };

  return (
    <div
      style={{
        borderTop: "1px solid var(--color-stroke)",
        padding: 12,
        display: "flex",
        gap: 8,
        alignItems: "flex-end",
        background: "var(--color-bg-1)",
      }}
    >
      <textarea
        ref={textareaRef}
        value={value}
        rows={1}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
        placeholder="Ask about risk, smoke, evacuations, or your home…"
        aria-label="Ask the WildfireIQ assistant"
        style={{
          flex: 1,
          resize: "none",
          background: "var(--color-bg-2)",
          border: "1px solid var(--color-stroke)",
          borderRadius: "var(--radius-md)",
          color: "var(--color-text-hi)",
          fontFamily: "var(--font-body)",
          fontSize: 13,
          lineHeight: 1.5,
          padding: "8px 10px",
          outline: "none",
        }}
      />
      <button
        type="button"
        onClick={busy ? onStop : submit}
        disabled={!busy && !value.trim()}
        aria-label={busy ? "Stop" : "Send"}
        style={{
          height: 34,
          minWidth: 34,
          padding: "0 12px",
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--color-stroke)",
          background: busy ? "var(--color-bg-3)" : "var(--color-ember-600)",
          color: busy ? "var(--color-text-mid)" : "var(--color-text-hi)",
          cursor: !busy && !value.trim() ? "default" : "pointer",
          opacity: !busy && !value.trim() ? 0.4 : 1,
          fontFamily: "var(--font-data)",
          fontSize: 12,
          transition: "opacity 160ms, background 160ms",
        }}
      >
        {busy ? "Stop" : "Ask"}
      </button>
    </div>
  );
}

function Bubble({
  message,
  onSuggestion,
}: { message: ChatMessage; onSuggestion: (s: string) => void }) {
  if (message.role === "user") {
    return (
      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <div
          style={{
            maxWidth: "85%",
            background: "var(--color-bg-3)",
            border: "1px solid var(--color-stroke)",
            borderRadius: "var(--radius-lg)",
            padding: "8px 12px",
            fontSize: 13,
            lineHeight: 1.5,
            color: "var(--color-text-hi)",
          }}
        >
          {message.content}
        </div>
      </div>
    );
  }

  const waiting = message.streaming && !message.content && !message.activity.length;

  return (
    <div style={{ fontSize: 13, color: "var(--color-text-mid)" }}>
      {message.safetyNotice && (
        <div
          role="alert"
          style={{
            background: "hsl(4 85% 36% / 0.16)",
            border: "1px solid var(--color-ember-700)",
            borderRadius: "var(--radius-md)",
            padding: "8px 10px",
            marginBottom: 10,
            color: "var(--color-ember-100)",
            fontSize: 12,
            lineHeight: 1.5,
          }}
        >
          {message.safetyNotice}
        </div>
      )}

      <ToolTrail
        activity={message.activity}
        notes={message.notes}
        sources={message.sources}
        running={message.streaming}
      />

      {waiting && (
        <div
          style={{ color: "var(--color-text-low)", fontSize: 12, fontFamily: "var(--font-data)" }}
        >
          <span className="live-dot" aria-hidden style={{ marginRight: 6 }} />
          Thinking…
        </div>
      )}

      {message.content && <Markdown text={message.content} />}

      {message.error && (
        <div
          style={{
            marginTop: 8,
            color: "var(--color-ember-300)",
            fontSize: 12,
            lineHeight: 1.5,
          }}
        >
          {message.error}
        </div>
      )}

      {!message.streaming && message.suggestions.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
          {message.suggestions.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => onSuggestion(suggestion)}
              style={{
                background: "transparent",
                border: "1px solid var(--color-stroke)",
                borderRadius: "var(--radius-pill)",
                padding: "4px 10px",
                color: "var(--color-text-low)",
                fontSize: 11,
                fontFamily: "var(--font-body)",
                cursor: "pointer",
              }}
            >
              {suggestion}
            </button>
          ))}
        </div>
      )}

      {!message.streaming && message.usage && (
        <div
          style={{
            marginTop: 8,
            fontSize: 10,
            fontFamily: "var(--font-data)",
            color: "var(--color-text-low)",
            opacity: 0.6,
          }}
        >
          {message.usage.tool_calls > 0 && `${message.usage.tool_calls} tool calls · `}
          {(message.usage.duration_ms / 1000).toFixed(1)} s
        </div>
      )}
    </div>
  );
}

export function AssistantPanel() {
  const { messages, busy, open, setOpen, ask, stop, reset } = useAssistant();
  const starters = useStarterPrompts();
  const scrollRef = useRef<HTMLDivElement>(null);

  // Follow the stream, but only when the user has not scrolled up to read
  // something earlier in the thread.
  // biome-ignore lint/correctness/useExhaustiveDependencies: messages is the trigger, not a read
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [messages]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, setOpen]);

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          key="assistant"
          aria-label="WildfireIQ assistant"
          initial={{ x: PANEL_WIDTH, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: PANEL_WIDTH, opacity: 0 }}
          transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            bottom: 0,
            width: `min(${PANEL_WIDTH}px, 100vw)`,
            display: "flex",
            flexDirection: "column",
            background: "var(--color-bg-1)",
            borderLeft: "1px solid var(--color-stroke)",
            boxShadow: "var(--shadow-elevated)",
            pointerEvents: "auto",
            zIndex: 30,
          }}
        >
          <header
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "12px 14px",
              borderBottom: "1px solid var(--color-stroke)",
            }}
          >
            <span
              aria-hidden
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "var(--color-ember-500)",
                boxShadow: "var(--glow-ember)",
              }}
            />
            <div style={{ flex: 1 }}>
              <div
                style={{
                  fontFamily: "var(--font-display)",
                  fontSize: 13,
                  fontWeight: 600,
                  color: "var(--color-text-hi)",
                  letterSpacing: "-0.01em",
                }}
              >
                Assistant
              </div>
              <div
                style={{
                  fontFamily: "var(--font-data)",
                  fontSize: 10,
                  color: "var(--color-text-low)",
                  letterSpacing: "0.04em",
                }}
              >
                {starters.data ? `${starters.data.count} live data tools` : "grounded in live data"}
              </div>
            </div>
            {messages.length > 0 && (
              <button
                type="button"
                onClick={reset}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--color-text-low)",
                  fontSize: 11,
                  fontFamily: "var(--font-data)",
                  cursor: "pointer",
                }}
              >
                Clear
              </button>
            )}
            <button
              type="button"
              onClick={() => setOpen(false)}
              aria-label="Close assistant"
              style={{
                background: "none",
                border: "none",
                color: "var(--color-text-mid)",
                fontSize: 16,
                lineHeight: 1,
                cursor: "pointer",
                padding: 4,
              }}
            >
              ×
            </button>
          </header>

          <div
            ref={scrollRef}
            style={{
              flex: 1,
              overflowY: "auto",
              padding: 14,
              display: "flex",
              flexDirection: "column",
              gap: 18,
            }}
          >
            {messages.length === 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <p
                  style={{
                    margin: 0,
                    fontSize: 13,
                    lineHeight: 1.6,
                    color: "var(--color-text-mid)",
                  }}
                >
                  I answer from this platform's live data — the risk model, the BC Wildfire Service
                  feed, evacuation orders, air quality, and the project's own documentation. I can
                  move the map for you too.
                </p>
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {(starters.data?.starter_prompts ?? []).map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => ask(prompt)}
                      style={{
                        textAlign: "left",
                        background: "var(--color-bg-2)",
                        border: "1px solid var(--color-stroke)",
                        borderRadius: "var(--radius-md)",
                        padding: "8px 10px",
                        color: "var(--color-text-mid)",
                        fontSize: 12,
                        fontFamily: "var(--font-body)",
                        cursor: "pointer",
                      }}
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
                <p
                  style={{
                    margin: 0,
                    fontSize: 10,
                    fontFamily: "var(--font-data)",
                    color: "var(--color-text-low)",
                    lineHeight: 1.5,
                  }}
                >
                  Informational only. In an emergency call 911 and follow emergencyinfobc.gov.bc.ca.
                </p>
              </div>
            )}

            {messages.map((message) => (
              <Bubble key={message.id} message={message} onSuggestion={ask} />
            ))}
          </div>

          <Composer busy={busy} onSend={ask} onStop={stop} />
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
