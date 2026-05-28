/**
 * Per-layer explanation copy. Lives next to the LayerToggleBar so info icons
 * and the LayerDetailModal banner both pull from this single source.
 *
 * Kept concise (~1-2 short paragraphs). For deep detail, the user reads
 * logic.md or the model card. The platform's footer always reminds: "this
 * is informational, not a substitute for BC Wildfire Service or BC
 * Emergency Management guidance."
 */
import type { LayerId } from "@/stores/layers";

export type LayerInfo = {
  what: string;
  pipeline: string;
  source: string;
  refresh: string;
  caveat?: string;
};

export const LAYER_INFO: Record<LayerId, LayerInfo> = {
  fires: {
    what: "Where wildfires are burning in BC right now. Each fire is shown two ways: if the fire is big enough to have its burned area mapped, you'll see a shaded outline of that area; smaller fires appear as a single flame marker. This is the same list of fires the BC Wildfire Service publishes — we don't add or guess anything.",
    pipeline:
      "We ask the BC government's open data service for the current fire list every 15 minutes. By default we hide fires marked \"Out\" so the map shows what's still active — you can switch them back on with the filters in this panel. Click any fire to see its name, size (in hectares), and how contained it is.",
    source: "BC Wildfire Service (official government data)",
    refresh: "Updated every 15 minutes; the map re-checks every minute",
  },
  hotspots: {
    what: "Spots on the ground that satellites measured as unusually hot in the last 3 days. Think of these as \"heat alarms,\" not confirmed fires — a hotspot means a satellite saw heat there and it's worth a look. Bigger, redder dots gave off more heat; small pale dots are weaker signals.",
    pipeline:
      "NASA satellites pass over BC a few times a day and record heat. We download those readings every 30 minutes and drop the least reliable ones (low-confidence detections). A single fire can light up two or three neighbouring dots at once — that's normal, it just means the hot area is bigger than one satellite pixel.",
    source: "NASA FIRMS satellites (VIIRS and MODIS)",
    refresh: "Updated every 30 minutes; the map re-checks every 5 minutes",
    caveat:
      "Not every hotspot is a wildfire. Industrial flares, hot rooftops, and processing plants can also trip the heat sensor. Treat a hotspot as \"investigate,\" not \"confirmed fire.\"",
  },
  evac: {
    what: "Areas where people have been told to leave or get ready to leave because of a nearby hazard. Three levels: an Evacuation ORDER (leave now) is filled red; an ALERT (be ready to leave) is amber with a dashed edge; a RESCIND (it's safe again) fades to green. Tap the \"Hide past\" control to remove rescinded zones from the list and the map.",
    pipeline:
      "We pull the official BC Emergency Management map every few minutes and draw the zones exactly as issued. The Preparedness Hub uses these same shapes to answer \"is my address inside an evacuation zone?\"",
    source: "BC Emergency Management Climate Readiness (official)",
    refresh: "Updated every 5 minutes; the map re-checks every minute",
  },
  fwi: {
    what: "How dangerous the weather is for fire spread, measured at weather stations across BC. This is the Fire Weather Index (FWI) — a single number that combines temperature, humidity, wind, and recent rain into a fire-danger score. Low numbers (green) mean fire is unlikely to spread fast; high numbers (red) mean conditions are primed for a fast, intense fire. It describes the *weather*, not whether a fire actually exists.",
    pipeline:
      "Canada's official fire-weather service was unreachable for much of this build, so we calculate the same index ourselves. Every 30 minutes we take the last 30 days of weather for ~18 BC towns and run the exact equations Canada uses (the Van Wagner method) to produce each station's score. If the official service comes back online, its numbers take priority.",
    source: "Calculated with Canada's official FWI equations from Open-Meteo weather",
    refresh: "Updated every 30 minutes; the map re-checks every 10 minutes",
  },
  smoke: {
    what: "Canada's official forecast for wildfire smoke — specifically tiny airborne particles called PM2.5 that are the part of smoke most harmful to breathe. The shaded overlay shows where smoke is predicted hour by hour. Use the time slider in this panel to step through the next ~3 days; each step shows the predicted particle level (in µg/m³ — micrograms per cubic metre) for Kamloops.",
    pipeline:
      "Every 6 hours we read Canada's smoke-forecast model and break its forecast window into roughly 73 hourly snapshots. For each hour we also attach the predicted Kamloops particle level so you see a real number — important because the overlay looks empty when the air is clean, which is good news, not a glitch.",
    source: "Environment and Climate Change Canada (RAQDPS-FW smoke model)",
    refresh: "Updated every 6 hours; the map re-checks every 30 minutes",
  },
  risk: {
    what: "Our AI's best estimate of wildfire risk across the region today, drawn as coloured hexagons (Low / Moderate / High / Extreme). It blends two things: how fire-prone today's weather is, and how often each specific area has burned in the past. Open a hexagon to also see the official government Fire Danger rating side-by-side, so you can compare our estimate to the standard one.",
    pipeline:
      "We trained a machine-learning model on 23 years of BC weather and fire records (1999-2021), then tested it on years it had never seen (2022 and 2023). On that unseen data it correctly ranked fire days clearly better than the traditional weather-threshold method. Today's region-wide risk is then scaled up or down for each hexagon based on that area's documented fire history.",
    source: "In-house AI model trained on 23 years of BC Wildfire Service + weather data",
    refresh: "Recalculated daily on the latest weather; the map re-checks every 30 minutes",
    caveat:
      "The difference between hexagons comes from each area's fire history, not from separate local weather (we use one regional weather signal). This is a planning aid, not an official warning — always follow the BC Wildfire Service and BC Emergency Management.",
  },
};
