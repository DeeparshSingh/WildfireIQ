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
    what: "Every wildfire BC Wildfire Service currently reports anywhere in the province. Burned-area perimeters (when mapped) are drawn as translucent polygons; smaller / point-only fires are shown as flame icons.",
    pipeline:
      "We pull from DataBC's WFS endpoints for current fire perimeters and points every 15 minutes, drop status=\"Out\" by default (you can toggle them back on inside this modal), and serve the rest verbatim. No modelling — what you see is the same fire list BCWS publishes.",
    source: "BC Wildfire Service · DataBC",
    refresh: "ingest every 15 min · frontend re-fetch every 60 s",
  },
  hotspots: {
    what: "Thermal anomalies detected by NASA satellites in the last 72 hours. Dot size scales with Fire Radiative Power; colour ramps from pale yellow (low energy) to deep red (high energy).",
    pipeline:
      "We query NASA FIRMS's near-real-time CSV endpoint every 30 minutes for VIIRS-NOAA20, VIIRS-SNPP, and MODIS detections in the BC bbox. Confidence < 30 is filtered out as likely false positive. A hotspot is not the same as a confirmed fire — it's worth investigating, not a confirmed ignition.",
    source: "NASA FIRMS · VIIRS / MODIS NRT",
    refresh: "ingest every 30 min · frontend re-fetch every 5 min",
    caveat:
      "Thermal anomalies can include gas flares, hot rooftops, and processing facilities — not just fires.",
  },
  evac: {
    what: "Active Evacuation Orders, Alerts, and Rescinds issued by BC Emergency Management. Orders fill red with a solid outline; Alerts fill amber with a dashed outline; Rescinds fade to sage.",
    pipeline:
      "Every 5 minutes during fire season (hourly off-season), we pull the BC Emergency Map's public FeatureServer, filter to features that intersect the BC bbox, and serve them verbatim. Point-in-polygon checks via Shapely power the Phase 5 \"am I in an evac zone?\" lookup.",
    source: "BC Emergency Management Climate Readiness",
    refresh: "ingest every 5 min · frontend re-fetch every 60 s",
  },
  fwi: {
    what: "Stations across BC reporting today's Canadian Fire Weather Index codes (FFMC, DMC, DC, ISI, BUI, FWI, DSR). Circle colour reflects the FWI value using standard CFFDRS thresholds.",
    pipeline:
      "We hit Natural Resources Canada's CWFIS GeoServer daily at 18:00 UTC for the live station table. CWFIS has been HTTP-502'd for some time — when it's down, this layer is empty, but Phase 3 also computes FWI ourselves from Open-Meteo weather, so the AI Risk Grid still works.",
    source: "Natural Resources Canada · CWFIS",
    refresh: "ingest daily 18 UTC · frontend re-fetch every 10 min",
  },
  smoke: {
    what: "ECCC's official wildfire smoke forecast — surface-level PM2.5 concentration as a translucent overlay on the globe.",
    pipeline:
      "Every 6 hours we read the MSC GeoMet WMS GetCapabilities document, find the latest RAQDPS-FW Wildfire Smoke run, and catalogue the available timesteps. The frontend renders the first timestep as a single tile imagery layer over the bbox at 55% alpha. Phase 4 will add a time scrubber to step through the 48-hour forecast hour-by-hour.",
    source: "ECCC · RAQDPS-FW via MSC GeoMet WMS",
    refresh: "ingest every 6 h · frontend re-fetch every 30 min",
  },
  risk: {
    what: "An AI-predicted regional fire-day probability for the Thompson-Okanagan, multiplied by each hex cell's historical fire density. Hexes shaded Low / Moderate / High / Extreme. The cell detail panel also shows the canonical CFFDRS Fire Danger class for comparison.",
    pipeline:
      "A LightGBM classifier trained on 8,394 days of Open-Meteo ERA5 weather + Van Wagner FWI codes (1999-2021), validated on 2022 and tested held-out on 2023. Test PR-AUC 0.66 beats the FWI-threshold baseline (0.52) by ~15 points. The single regional probability is multiplied by each H3 r=5 cell's sqrt-normalised historical fire count from 15,996 BC incidents. Bucket thresholds are calibrated to our model — the CFFDRS class shown alongside is the deterministic standard BCWS uses.",
    source: "LightGBM · trained on BCWS 1999-2021 + ERA5 weather",
    refresh: "daily inference · frontend re-fetch every 30 min",
    caveat:
      "Per-cell variation comes from historical density, not today's local weather (we use only one weather station). Informational only — not a substitute for BC Wildfire Service or BC Emergency Management.",
  },
};
