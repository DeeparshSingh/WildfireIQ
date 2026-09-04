/**
 * The assistant's wire contract, mirroring `wildfireiq_api/assistant/harness.py`.
 *
 * Every SSE frame the backend emits has a name and a JSON payload; these
 * types are the payloads. Keeping them exhaustive means an event the
 * frontend does not handle is a compile error rather than a silent drop.
 */

export type ChatRole = "user" | "assistant";

export type ToolActivity = {
  id: string;
  name: string;
  arguments?: string;
  ok?: boolean;
  cached?: boolean;
  durationMs?: number;
  summary?: string;
  error?: string | null;
};

export type Source = { source: string; as_of: string | null };

export type Usage = {
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  tool_calls: number;
  tools: string[];
  duration_ms: number;
};

export type ChatMessage = {
  id: string;
  role: ChatRole;
  /** Rendered answer text. Grows while streaming. */
  content: string;
  /** Tool activity and plan notes, in the order they happened. */
  activity: ToolActivity[];
  notes: string[];
  sources: Source[];
  suggestions: string[];
  safetyNotice?: string | null;
  usage?: Usage;
  error?: string | null;
  /** True while this message is still being produced. */
  streaming: boolean;
};

/** Instructions the backend sends for the UI to carry out. */
export type Effect =
  | { type: "fly_to"; lat: number; lon: number; height_m: number; label?: string }
  | { type: "set_layer"; layer: string; visible: boolean }
  | { type: "navigate"; path: string; label?: string };

/** What the browser tells the assistant about the user's current view. */
export type AssistantContext = {
  page?: string;
  lat?: number;
  lon?: number;
  place_label?: string;
  dwelling?: string;
  situation?: string[];
  visible_layers?: string[];
};

export type AssistantHealth = {
  enabled: boolean;
  configured: boolean;
  model: string;
  tools: number;
  max_steps: number;
  max_tool_calls: number;
};
