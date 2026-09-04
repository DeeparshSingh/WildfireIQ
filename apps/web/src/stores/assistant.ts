/**
 * Assistant conversation state.
 *
 * Lives in Zustand at app scope so the panel survives route changes — you
 * can ask about the risk grid, be flown to Merritt, navigate to the air
 * quality page, and still have the thread in front of you.
 *
 * The transcript is mirrored into sessionStorage so a reload during one
 * sitting does not lose it, and is gone when the tab closes. Nothing goes
 * to the server between requests: the backend is stateless and holds no
 * conversation of its own.
 */
import { create } from "zustand";

import type { ChatMessage, Source, ToolActivity, Usage } from "@/features/assistant/types";

const STORAGE_KEY = "wfiq.assistant.thread.v1";
const MAX_PERSISTED = 20;

function loadThread(): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ChatMessage[];
    // A message that was still streaming when the tab reloaded can never
    // finish, so it is dropped rather than left spinning forever.
    return parsed.filter((m) => !m.streaming);
  } catch {
    return [];
  }
}

function persist(messages: ChatMessage[]) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(messages.slice(-MAX_PERSISTED)));
  } catch {
    // Private browsing, quota, or a disabled storage API. The thread still
    // works for this page view; it just will not survive a reload.
  }
}

let counter = 0;
export function nextMessageId(prefix: string): string {
  counter += 1;
  return `${prefix}-${Date.now().toString(36)}-${counter}`;
}

type AssistantState = {
  open: boolean;
  messages: ChatMessage[];
  /** Set while a request is in flight, so the composer can be disabled. */
  busy: boolean;

  setOpen: (open: boolean) => void;
  toggle: () => void;

  appendUser: (content: string) => void;
  startAssistant: () => string;
  appendToken: (id: string, text: string) => void;
  addActivity: (id: string, activity: ToolActivity) => void;
  updateActivity: (id: string, activityId: string, patch: Partial<ToolActivity>) => void;
  absorbPlan: (id: string, note: string | null) => void;
  setSources: (id: string, sources: Source[]) => void;
  setSuggestions: (id: string, suggestions: string[]) => void;
  setSafetyNotice: (id: string, notice: string) => void;
  setUsage: (id: string, usage: Usage) => void;
  setError: (id: string, error: string) => void;
  finish: (id: string) => void;
  reset: () => void;
};

export const useAssistantStore = create<AssistantState>((set, get) => {
  /** Apply a patch to one message and keep sessionStorage in step. */
  const patchMessage = (id: string, patch: (m: ChatMessage) => ChatMessage) => {
    set((state) => {
      const messages = state.messages.map((m) => (m.id === id ? patch(m) : m));
      return { messages };
    });
  };

  return {
    open: false,
    messages: loadThread(),
    busy: false,

    setOpen: (open) => set({ open }),
    toggle: () => set((s) => ({ open: !s.open })),

    appendUser: (content) =>
      set((state) => {
        const messages = [
          ...state.messages,
          {
            id: nextMessageId("u"),
            role: "user" as const,
            content,
            activity: [],
            notes: [],
            sources: [],
            suggestions: [],
            streaming: false,
          },
        ];
        persist(messages);
        return { messages };
      }),

    startAssistant: () => {
      const id = nextMessageId("a");
      set((state) => ({
        busy: true,
        messages: [
          ...state.messages,
          {
            id,
            role: "assistant" as const,
            content: "",
            activity: [],
            notes: [],
            sources: [],
            suggestions: [],
            streaming: true,
          },
        ],
      }));
      return id;
    },

    appendToken: (id, text) => patchMessage(id, (m) => ({ ...m, content: m.content + text })),

    addActivity: (id, activity) =>
      patchMessage(id, (m) => ({ ...m, activity: [...m.activity, activity] })),

    updateActivity: (id, activityId, patch) =>
      patchMessage(id, (m) => ({
        ...m,
        activity: m.activity.map((a) => (a.id === activityId ? { ...a, ...patch } : a)),
      })),

    // A turn that ends in tool calls streamed a plan, not an answer. Move
    // what was streamed out of the bubble and into the activity trail, so
    // the final answer is not prefixed with "let me check that for you".
    absorbPlan: (id, note) =>
      patchMessage(id, (m) => {
        const text = (note ?? m.content).trim();
        return { ...m, content: "", notes: text ? [...m.notes, text] : m.notes };
      }),
    setSources: (id, sources) => patchMessage(id, (m) => ({ ...m, sources })),
    setSuggestions: (id, suggestions) => patchMessage(id, (m) => ({ ...m, suggestions })),
    setSafetyNotice: (id, safetyNotice) => patchMessage(id, (m) => ({ ...m, safetyNotice })),
    setUsage: (id, usage) => patchMessage(id, (m) => ({ ...m, usage })),
    setError: (id, error) => patchMessage(id, (m) => ({ ...m, error })),

    finish: (id) => {
      patchMessage(id, (m) => ({ ...m, streaming: false }));
      set({ busy: false });
      persist(get().messages);
    },

    reset: () => {
      persist([]);
      set({ messages: [], busy: false });
    },
  };
});
