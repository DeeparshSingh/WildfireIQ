/**
 * What the assistant did before it answered.
 *
 * A tool-using agent that shows only its conclusion is asking to be taken
 * on faith. This renders the work: which datasets it queried, whether each
 * one succeeded, how long it took, and what came back — collapsed by
 * default so it informs without shouting.
 */
import { useState } from "react";

import type { Source, ToolActivity } from "./types";

/** Human labels for the tool names the backend streams. */
const TOOL_LABELS: Record<string, string> = {
  get_wildfire_risk: "AI wildfire risk",
  get_active_fires: "Active fires",
  get_satellite_hotspots: "Satellite hotspots",
  check_evacuation_status: "Evacuation check",
  list_evacuation_orders: "Evacuation orders",
  get_air_quality: "Air quality now",
  get_air_quality_forecast: "PM2.5 forecast",
  get_health_guidance: "Health guidance",
  get_smoke_history: "Smoke history",
  get_smoke_plume_forecast: "Smoke plume forecast",
  get_weather: "Weather",
  get_fire_weather_index: "Fire Weather Index",
  get_season_context: "Season context",
  get_seasonal_history: "Season records",
  get_climate_trends: "Climate trends",
  get_historical_fires: "Fire archive",
  get_fire_danger_projection: "Fire-danger projection",
  get_firesmart_actions: "FireSmart actions",
  search_documentation: "Project documentation",
  get_model_performance: "Model metrics",
  get_data_freshness: "Pipeline health",
  resolve_place: "Place lookup",
  show_on_map: "Moved the map",
  set_map_layer: "Toggled a layer",
  open_page: "Opened a page",
};

const label = (name: string) => TOOL_LABELS[name] ?? name.replace(/_/g, " ");

export function ToolTrail({
  activity,
  notes,
  sources,
  running,
}: {
  activity: ToolActivity[];
  notes: string[];
  sources: Source[];
  running: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  if (!activity.length && !notes.length) return null;

  const failed = activity.filter((a) => a.ok === false).length;
  const pending = activity.filter((a) => a.ok === undefined).length;

  const summary =
    running && pending
      ? `Checking ${activity
          .filter((a) => a.ok === undefined)
          .map((a) => label(a.name).toLowerCase())
          .slice(0, 2)
          .join(", ")}…`
      : `${activity.length} ${activity.length === 1 ? "source" : "sources"} consulted${
          failed ? ` · ${failed} unavailable` : ""
        }`;

  return (
    <div
      style={{
        borderLeft: "2px solid var(--color-stroke)",
        paddingLeft: 10,
        margin: "2px 0 8px",
        fontSize: 11,
        fontFamily: "var(--font-data)",
      }}
    >
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        style={{
          background: "none",
          border: "none",
          padding: 0,
          cursor: "pointer",
          color: "var(--color-text-low)",
          fontFamily: "inherit",
          fontSize: "inherit",
          display: "flex",
          alignItems: "center",
          gap: 6,
          letterSpacing: "0.02em",
        }}
      >
        {running && pending > 0 && <span className="live-dot" aria-hidden />}
        <span>{summary}</span>
        <span aria-hidden style={{ opacity: 0.6 }}>
          {expanded ? "−" : "+"}
        </span>
      </button>

      {expanded && (
        <div style={{ marginTop: 8, display: "flex", flexDirection: "column", gap: 6 }}>
          {notes.map((note) => (
            <div key={note} style={{ color: "var(--color-text-low)", fontStyle: "italic" }}>
              {note}
            </div>
          ))}

          {activity.map((item) => (
            <div key={item.id} style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
              <span
                aria-hidden
                style={{
                  color:
                    item.ok === false
                      ? "var(--color-ember-600)"
                      : item.ok
                        ? "var(--color-cyan-glow)"
                        : "var(--color-text-low)",
                }}
              >
                {item.ok === false ? "×" : item.ok ? "✓" : "·"}
              </span>
              <span style={{ color: "var(--color-text-mid)" }}>{label(item.name)}</span>
              <span style={{ color: "var(--color-text-low)", flex: 1, minWidth: 0 }}>
                {item.error ?? item.summary ?? ""}
              </span>
              {item.durationMs !== undefined && (
                <span style={{ color: "var(--color-text-low)", opacity: 0.7 }}>
                  {item.cached ? "cached" : `${item.durationMs} ms`}
                </span>
              )}
            </div>
          ))}

          {sources.length > 0 && (
            <div style={{ marginTop: 4, color: "var(--color-text-low)", lineHeight: 1.5 }}>
              {sources.map((source) => (
                <div key={source.source}>
                  {source.source}
                  {source.as_of ? ` · as of ${source.as_of.slice(0, 16).replace("T", " ")}` : ""}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
