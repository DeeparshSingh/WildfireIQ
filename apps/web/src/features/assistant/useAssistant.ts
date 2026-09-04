import { useQuery } from "@tanstack/react-query";
import { Math as CesiumMath } from "cesium";
/**
 * The browser half of the agent loop.
 *
 * `ask()` posts the transcript plus the user's current view, then drives
 * the conversation store from the event stream. Effects — fly the camera,
 * toggle a layer, change route — are applied here as they arrive, so the
 * map starts moving while the answer is still being written.
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { loadProfile } from "@/features/preparedness/state";
import { API_BASE } from "@/lib/api/client";
import { cinematicFlyTo } from "@/lib/cesium-helpers/cinematicFlyTo";
import { useAssistantStore } from "@/stores/assistant";
import { useGlobeStore } from "@/stores/globe";
import { type LayerId, useLayersStore } from "@/stores/layers";

import { readSse } from "./sse";
import type { AssistantContext, AssistantHealth, Effect, Source, Usage } from "./types";

const PAGE_NAMES: Record<string, string> = {
  "/": "globe",
  "/air-quality": "air quality",
  "/preparedness": "preparedness",
  "/preparedness/shared": "shared progress",
  "/climate": "climate trends",
  "/about": "about",
};

const LAYER_IDS: ReadonlySet<string> = new Set([
  "fires",
  "hotspots",
  "evac",
  "smoke",
  "fwi",
  "risk",
]);

/** Is the assistant configured on this deployment? Cached for the session. */
export function useAssistantHealth() {
  return useQuery({
    queryKey: ["assistant", "health"],
    queryFn: async () => {
      // The health endpoint is not enveloped — it answers even when the
      // assistant is off, which is the whole point of it.
      const res = await fetch(`${API_BASE}/api/assistant/health`);
      if (!res.ok) throw new Error(`assistant health: HTTP ${res.status}`);
      return (await res.json()) as AssistantHealth;
    },
    staleTime: 10 * 60_000,
    retry: 1,
  });
}

export function useStarterPrompts() {
  return useQuery({
    queryKey: ["assistant", "tools"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/assistant/tools`);
      if (!res.ok) throw new Error(`assistant tools: HTTP ${res.status}`);
      return (await res.json()) as { count: number; starter_prompts: string[] };
    },
    staleTime: 24 * 60 * 60_000,
    retry: 0,
  });
}

/** Where the camera is pointing, so "here" means something. */
function cameraPosition(): { lat: number; lon: number } | null {
  const viewer = useGlobeStore.getState().viewer;
  if (!viewer) return null;
  try {
    const carto = viewer.camera.positionCartographic;
    return {
      lat: Number(CesiumMath.toDegrees(carto.latitude).toFixed(4)),
      lon: Number(CesiumMath.toDegrees(carto.longitude).toFixed(4)),
    };
  } catch {
    return null;
  }
}

export function useAssistant() {
  const store = useAssistantStore();
  const navigate = useNavigate();
  const location = useLocation();
  const abortRef = useRef<AbortController | null>(null);

  // Abandon an in-flight answer if the panel unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  const buildContext = useCallback((): AssistantContext => {
    const context: AssistantContext = {
      page: PAGE_NAMES[location.pathname] ?? location.pathname,
    };

    const camera = cameraPosition();
    if (camera) {
      context.lat = camera.lat;
      context.lon = camera.lon;
    }

    const visible = useLayersStore.getState().visible;
    const on = Object.entries(visible)
      .filter(([, isOn]) => isOn)
      .map(([id]) => id);
    if (on.length) context.visible_layers = on;

    // The FireSmart profile lives in localStorage and never leaves the
    // browser except here, where it makes preparedness answers specific.
    const profile = loadProfile();
    if (profile) {
      context.dwelling = profile.dwelling;
      if (profile.situation.length) context.situation = profile.situation;
      if (profile.neighbourhood && profile.neighbourhoodLat && profile.neighbourhoodLon) {
        context.place_label = `${profile.neighbourhood}, Kamloops`;
        context.lat = profile.neighbourhoodLat;
        context.lon = profile.neighbourhoodLon;
      }
    }

    return context;
  }, [location.pathname]);

  const applyEffect = useCallback(
    (effect: Effect) => {
      switch (effect.type) {
        case "fly_to": {
          const viewer = useGlobeStore.getState().viewer;
          if (!viewer) return;
          cinematicFlyTo(viewer, {
            lat: effect.lat,
            lon: effect.lon,
            height: Math.max(effect.height_m, 2_000),
          });
          break;
        }
        case "set_layer": {
          if (!LAYER_IDS.has(effect.layer)) return;
          useLayersStore.getState().set(effect.layer as LayerId, effect.visible);
          break;
        }
        case "navigate": {
          // Only in-app paths, never an arbitrary URL from the stream.
          if (effect.path.startsWith("/")) navigate(effect.path);
          break;
        }
      }
    },
    [navigate],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const ask = useCallback(
    async (question: string) => {
      const text = question.trim();
      if (!text || useAssistantStore.getState().busy) return;

      // Zustand actions are stable, so reading them once here keeps `ask`
      // out of the dependency churn of the message list.
      const actions = useAssistantStore.getState();
      actions.appendUser(text);

      // Send the transcript as it stands *after* appending the question.
      // Failed turns are dropped: replaying an error back at the model
      // teaches it nothing and costs tokens.
      const transcript = useAssistantStore
        .getState()
        .messages.filter((m) => !m.error)
        .map((m) => ({ role: m.role, content: m.content }))
        .filter((m) => m.content.trim().length > 0);

      const id = actions.startAssistant();

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        const response = await fetch(`${API_BASE}/api/assistant/chat`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
          body: JSON.stringify({ messages: transcript, context: buildContext() }),
          signal: controller.signal,
        });

        if (!response.ok || !response.body) {
          const detail = await response
            .json()
            .then((b) => b?.detail as string | undefined)
            .catch(() => undefined);
          actions.setError(id, detail ?? `The assistant is unavailable (HTTP ${response.status}).`);
          actions.finish(id);
          return;
        }

        for await (const frame of readSse(response.body, controller.signal)) {
          const data = frame.data as Record<string, unknown>;
          switch (frame.event) {
            case "token":
              actions.appendToken(id, String(data.text ?? ""));
              break;
            case "step_end":
              actions.absorbPlan(id, (data.note as string | null) ?? null);
              break;
            case "tool_call":
              actions.addActivity(id, {
                id: String(data.id),
                name: String(data.name),
                arguments: data.arguments as string | undefined,
              });
              break;
            case "tool_result":
              actions.updateActivity(id, String(data.id), {
                ok: Boolean(data.ok),
                cached: Boolean(data.cached),
                durationMs: Number(data.duration_ms ?? 0),
                summary: data.summary as string | undefined,
                error: (data.error as string | null) ?? null,
              });
              break;
            case "effect":
              applyEffect(data as unknown as Effect);
              break;
            case "safety":
              actions.setSafetyNotice(id, String(data.message));
              break;
            case "sources":
              actions.setSources(id, (data.sources as Source[]) ?? []);
              break;
            case "suggestions":
              actions.setSuggestions(id, (data.items as string[]) ?? []);
              break;
            case "usage":
              actions.setUsage(id, data as unknown as Usage);
              break;
            case "error":
              actions.setError(id, String(data.message));
              break;
            case "done":
              break;
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          actions.setError(id, "Lost the connection to the assistant.");
        }
      } finally {
        actions.finish(id);
        abortRef.current = null;
      }
    },
    [applyEffect, buildContext],
  );

  return useMemo(
    () => ({
      messages: store.messages,
      busy: store.busy,
      open: store.open,
      setOpen: store.setOpen,
      toggle: store.toggle,
      reset: store.reset,
      ask,
      stop,
    }),
    [store.messages, store.busy, store.open, store.setOpen, store.toggle, store.reset, ask, stop],
  );
}
