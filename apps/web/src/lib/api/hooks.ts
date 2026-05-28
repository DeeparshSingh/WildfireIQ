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

/** A zone is "past" once it's been rescinded — no longer an active threat. */
export function isPastEvac(z: EvacZone): boolean {
  return (z.status ?? "").toLowerCase().includes("rescind");
}

/** Sort newest → oldest by issued date; nulls sink to the bottom. */
export function sortEvacByDateDesc(zones: EvacZone[]): EvacZone[] {
  return [...zones].sort((a, b) => {
    const ta = a.issued_utc ? Date.parse(a.issued_utc) : -Infinity;
    const tb = b.issued_utc ? Date.parse(b.issued_utc) : -Infinity;
    return tb - ta;
  });
}

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
  /** PM2.5 µg/m³ at Kamloops at this forecast hour (joined from Open-Meteo CAMS). */
  pm25_at_kamloops?: number | null;
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

// ─── FireSmart (Phase 5) ──────────────────────────────────────────────

export type FireSmartGroupId =
  | "immediate"
  | "intermediate_a"
  | "intermediate_b"
  | "extended"
  | "plan_gobag";

export type FireSmartGroup = {
  id: FireSmartGroupId;
  label: string;
  distance: string;
};

export type FireSmartAction = {
  id: string;
  zone: FireSmartGroupId;
  title: string;
  why: string;
  category: "structural" | "vegetation" | "preparedness" | "awareness";
  estimated_minutes: number | null;
  cost: "free" | "low" | "medium" | "high";
  season_priority: Record<string, number>;
  applies: { dwelling?: string[]; situation?: string[] };
  points: number;
};

export type FireSmartChecklist = {
  groups: FireSmartGroup[];
  actions: FireSmartAction[];
  max_points: number;
  version: string;
};

export function useFireSmartChecklist(
  dwelling: string,
  season: string,
  situation: string[],
) {
  const sitParam = situation.join(",");
  return useQuery({
    queryKey: ["firesmart", "checklist", dwelling, season, sitParam],
    queryFn: () =>
      apiGet<FireSmartChecklist>(
        `/api/firesmart/checklist?dwelling=${encodeURIComponent(
          dwelling,
        )}&season=${encodeURIComponent(season)}&situation=${encodeURIComponent(sitParam)}`,
      ),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<FireSmartChecklist>) => env.data,
  });
}

export type FireSmartAchievement = {
  id: string;
  label: string;
  blurb: string;
  emoji: string;
  rule: string;
};

export function useFireSmartAchievements() {
  return useQuery({
    queryKey: ["firesmart", "achievements"],
    queryFn: () =>
      apiGet<{ achievements: FireSmartAchievement[] }>(
        "/api/firesmart/achievements",
      ),
    staleTime: 24 * 60 * 60_000,
    select: (env) => env.data.achievements,
  });
}

export type NeighbourhoodFeature = {
  type: "Feature";
  properties: {
    name: string;
    centroid_lat: number;
    centroid_lon: number;
  };
  geometry: { type: "Polygon"; coordinates: number[][][] };
};

export function useNeighbourhoods() {
  return useQuery({
    queryKey: ["firesmart", "neighbourhoods"],
    queryFn: () =>
      apiGet<{ type: "FeatureCollection"; features: NeighbourhoodFeature[] }>(
        "/api/firesmart/neighbourhoods",
      ),
    staleTime: 24 * 60 * 60_000,
    select: (env) => env.data.features,
  });
}

export type SeasonContext = {
  days_since_5mm_rain: number | null;
  peak_month: number;
  peak_day: number;
  peak_basis: string;
};

// ─── Climate Trend (Phase 6) ──────────────────────────────────────────

export type SeasonalRow = {
  year: number;
  area_burned_ha: number | null;
  fire_count: number | null;
  largest_fire_ha: number | null;
  season_start_doy: number | null;
  season_end_doy: number | null;
  season_length_days: number | null;
  mean_jul_temp_c: number | null;
  julaug_precip_mm: number | null;
  mean_julaug_vpd_kpa: number | null;
  max_julaug_fwi: number | null;
  days_fwi_ge_19: number | null;
};

export function useSeasonalMetrics() {
  return useQuery({
    queryKey: ["climate", "seasonal"],
    queryFn: () => apiGet<SeasonalRow[]>("/api/climate/seasonal"),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<SeasonalRow[]>) => env.data,
  });
}

export type TrendMetric = {
  slope_per_year: number;
  intercept: number;
  slope_ci_lo: number;
  slope_ci_hi: number;
  n_years: number;
  delta_over_span: number;
};

export type Trends = {
  year_min: number;
  year_max: number;
  metrics: Record<string, TrendMetric>;
};

export function useClimateTrends() {
  return useQuery({
    queryKey: ["climate", "trends"],
    queryFn: () => apiGet<Trends>("/api/climate/trends"),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<Trends>) => env.data,
  });
}

export type RibbonRow = {
  year: number;
  start_doy: number;
  end_doy: number;
  length_days: number;
  area_burned_ha: number;
};

export function useClimateRibbon() {
  return useQuery({
    queryKey: ["climate", "ribbon"],
    queryFn: () => apiGet<RibbonRow[]>("/api/climate/ribbon"),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<RibbonRow[]>) => env.data,
  });
}

export type ProjectionRow = {
  year: number;
  ssp: string;
  variable: string;
  value: number;
  q10: number;
  q50: number;
  q90: number;
};

export type ProjectionsAll = {
  variable: string;
  scenarios: { observed: ProjectionRow[]; ssp126: ProjectionRow[]; ssp245: ProjectionRow[]; ssp585: ProjectionRow[] };
};

export function useProjectionsAll(variable: string) {
  return useQuery({
    queryKey: ["climate", "projections-all", variable],
    queryFn: () =>
      apiGet<ProjectionsAll>(
        `/api/climate/projections-all?var=${encodeURIComponent(variable)}`,
      ),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<ProjectionsAll>) => env.data,
  });
}

export type FwiProjection = {
  method: string;
  fit: { slope_days_per_C: number; intercept: number; n: number };
  scenarios: Record<string, { decade: number; july_temp_c: number; days_fwi_ge_19: number; observed: boolean }[]>;
};

export function useFwiProjection() {
  return useQuery({
    queryKey: ["climate", "fwi-projection"],
    queryFn: () => apiGet<FwiProjection>("/api/climate/fwi-projection"),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<FwiProjection>) => env.data,
  });
}

export type TruCarbon = { available: boolean; rows: Record<string, number | string>[] };

export function useTruCarbon() {
  return useQuery({
    queryKey: ["climate", "tru-carbon"],
    queryFn: () => apiGet<TruCarbon>("/api/climate/tru-carbon"),
    staleTime: 24 * 60 * 60_000,
    select: (env: Envelope<TruCarbon>) => env.data,
  });
}

export function useSeasonContext() {
  return useQuery({
    queryKey: ["firesmart", "season-context"],
    queryFn: () =>
      apiGet<SeasonContext>("/api/firesmart/season-context"),
    refetchInterval: 60 * 60_000,
    select: (env: Envelope<SeasonContext>) => env.data,
  });
}

// ─── Evac check (point-in-polygon) ────────────────────────────────────

export type EvacCheckResult = {
  status: "clear" | "alert" | "order";
  matches: Array<{
    event_name?: string | null;
    status?: string | null;
    issuing_agency?: string | null;
    issued_utc?: string | null;
  }>;
  queried: { lat: number; lon: number };
};

export function useEvacCheck(lat: number | null, lon: number | null) {
  const enabled = lat !== null && lon !== null;
  return useQuery({
    queryKey: ["evac", "check", lat, lon],
    enabled,
    queryFn: () =>
      apiGet<EvacCheckResult>(
        `/api/evac/check?lat=${lat}&lon=${lon}`,
      ),
    refetchInterval: 60_000,
    select: (env: Envelope<EvacCheckResult>) => env.data,
  });
}
