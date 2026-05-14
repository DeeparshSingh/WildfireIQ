/**
 * TanStack Query hooks for each backend endpoint. Cesium layers consume
 * these hooks to keep their rendering in sync with the live data.
 */
import { useQuery } from "@tanstack/react-query";
import { apiGet, type Envelope } from "./client";

// ─── Domain types (mirrored from the backend Parquet schemas) ─────────

export type Fire = {
  fire_id: string;
  fire_name: string | null;
  status: string | null;
  stage_of_control: string | null;
  hectares: number | null;
  discovery_date_utc: string | null;
  latitude: number | null;
  longitude: number | null;
  geom_wkt: string | null;
  geom_kind: "polygon" | "point" | null;
  fetched_at_utc: string;
};

export type Hotspot = {
  latitude: number;
  longitude: number;
  acq_datetime_utc: string;
  brightness: number | null;
  frp: number | null;
  confidence: number | null;
  source: string;
  daynight: string | null;
  satellite: string | null;
  fetched_at_utc: string;
};

export type EvacZone = {
  event_id: string | null;
  event_name: string | null;
  status: string | null; // "Order" | "Alert" | "Rescind" | other
  issuing_agency: string | null;
  issued_utc: string | null;
  area_hectares: number | null;
  geom_wkt: string | null;
  fetched_at_utc: string;
};

export type FwiStation = {
  station_id: string;
  station_name: string;
  agency: string | null;
  latitude: number;
  longitude: number;
  observation_date_local: string | null;
  temp_c: number | null;
  rh_pct: number | null;
  wind_kmh: number | null;
  precip_mm: number | null;
  ffmc: number | null;
  dmc: number | null;
  dc: number | null;
  isi: number | null;
  bui: number | null;
  fwi: number | null;
  dsr: number | null;
  fetched_at_utc: string;
};

export type SmokeTimestep = {
  layer_name: string;
  valid_time_utc: string;
  fetch_url: string;
  fetched_at_utc: string;
};

export type RiskCell = {
  h3_cell: string;
  centroid_lat: number;
  centroid_lon: number;
  hist_fire_count: number;
  p_region: number;
  p_cell: number;
  risk_class: "Low" | "Moderate" | "High" | "Extreme";
};

export type RiskGrid = {
  observation_day: string;
  p_region: number;
  p_region_raw: number;
  fwi_today?: number;
  cffdrs_class?: "Low" | "Moderate" | "High" | "Very High" | "Extreme" | "Unknown";
  cells: RiskCell[];
};

// ─── Hooks ────────────────────────────────────────────────────────────

export function useFiresCurrent() {
  return useQuery({
    queryKey: ["fires", "current", "all"],
    // Always fetch all (incl. extinguished) — the filter store decides what
    // to render. Lets the LayerDetailModal "Include extinguished" toggle
    // work without re-fetching.
    queryFn: () => apiGet<Fire[]>("/api/fires/current?include_extinguished=true"),
    refetchInterval: 60_000,
    select: (env: Envelope<Fire[]>) => env.data,
  });
}

export function useFirmsHotspots(sinceHours = 72) {
  return useQuery({
    queryKey: ["fires", "hotspots", sinceHours],
    queryFn: () => apiGet<Hotspot[]>(`/api/fires/hotspots?since=${sinceHours}h`),
    refetchInterval: 5 * 60_000,
    select: (env: Envelope<Hotspot[]>) => env.data,
  });
}

export function useEvacActive() {
  return useQuery({
    queryKey: ["evac", "active"],
    queryFn: () => apiGet<EvacZone[]>("/api/evac/active"),
    refetchInterval: 60_000,
    select: (env: Envelope<EvacZone[]>) => env.data,
  });
}

export function useFwiToday() {
  return useQuery({
    queryKey: ["fwi", "today"],
    queryFn: () => apiGet<FwiStation[]>("/api/fwi/today"),
    refetchInterval: 10 * 60_000,
    select: (env: Envelope<FwiStation[]>) => env.data,
  });
}

export function useSmokeForecast() {
  return useQuery({
    queryKey: ["aq", "smoke-forecast"],
    queryFn: () => apiGet<SmokeTimestep[]>("/api/aq/smoke-forecast"),
    refetchInterval: 30 * 60_000,
    select: (env: Envelope<SmokeTimestep[]>) => env.data,
  });
}

export function useRiskGrid() {
  return useQuery({
    queryKey: ["risk", "grid"],
    queryFn: () => apiGet<RiskGrid>("/api/risk/grid"),
    refetchInterval: 30 * 60_000,
    select: (env: Envelope<RiskGrid>) => env.data,
  });
}

// ── Phase 4 · Air Quality dashboard ─────────────────────────────────

export type AqForecastPoint = {
  horizon_h: number;
  time_utc: string;
  q10: number;
  q50: number;
  q90: number;
  aqhi_q50: number;
};
export type AqObservation = { time_utc: string; pm2_5: number };
export type AqForecast = {
  issued_at_utc: string;
  observations: AqObservation[];
  forecasts: AqForecastPoint[];
  metrics: Record<string, Record<string, number>>;
};

export function useAqForecast() {
  return useQuery({
    queryKey: ["aq", "forecast"],
    queryFn: () => apiGet<AqForecast>("/api/aq/forecast"),
    refetchInterval: 10 * 60_000,
    select: (env: Envelope<AqForecast>) => env.data,
  });
}

export type AqCurrentStation = {
  station_id: string;
  station_name: string;
  latitude: number;
  longitude: number;
  aqhi: number | null;
  observation_datetime_utc: string;
};
export type AqPollutants = {
  station_name?: string;
  aqi?: number | null;
  pm25?: number | null;
  pm10?: number | null;
  o3?: number | null;
  no2?: number | null;
  so2?: number | null;
  co?: number | null;
  dominant_pollutant?: string | null;
  observation_time_utc?: string;
} | null;
export type AqCurrent = { stations: AqCurrentStation[]; pollutants: AqPollutants };

export function useAqCurrent() {
  return useQuery({
    queryKey: ["aq", "current"],
    queryFn: () => apiGet<AqCurrent>("/api/aq/current"),
    refetchInterval: 60_000,
    select: (env: Envelope<AqCurrent>) => env.data,
  });
}

export type AqCalendarDay = {
  day_utc: string;
  max_pm25: number;
  mean_pm25: number;
  max_aqhi: number;
};
export type AqCalendar = { days: AqCalendarDay[] };

export function useAqCalendar(days = 90) {
  return useQuery({
    queryKey: ["aq", "calendar", days],
    queryFn: () => apiGet<AqCalendar>(`/api/aq/calendar?days=${days}`),
    refetchInterval: 60 * 60_000,
    select: (env: Envelope<AqCalendar>) => env.data,
  });
}

export type HealthGuidanceBand = {
  aqhi_min: number;
  aqhi_max: number;
  label: string;
  general: string;
  at_risk: string;
  outdoor_workers: string;
};
export type HealthGuidance = {
  source: string;
  audiences: string[];
  bands: HealthGuidanceBand[];
  links: { title: string; url: string }[];
};

export function useHealthGuidance() {
  return useQuery({
    queryKey: ["aq", "health-guidance"],
    queryFn: () => apiGet<HealthGuidance>("/api/aq/health-guidance"),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<HealthGuidance>) => env.data,
  });
}
