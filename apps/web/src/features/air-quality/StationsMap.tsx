/**
 * Compact AQHI station "minimap" — schematic SVG view of nearby monitoring
 * stations, sized by AQHI value, coloured by AQHI band. Kamloops centroid
 * pinned at the centre. Hover a marker → station name + AQHI.
 *
 * Why not MapLibre: this is a single 280×280 panel meant to show *which*
 * stations exist and *where* they sit relative to Kamloops; a full slippy
 * map for that purpose is overkill and adds 200 KB to the bundle. The
 * Phase-7 polish pass can swap in MapLibre if real basemap context becomes
 * needed.
 */
import type { AqCurrentStation } from "@/lib/api/hooks";
import { aqhiColor } from "./aqColors";

const SIZE = 300;
const CENTER = SIZE / 2;
const RADIUS = SIZE / 2 - 18; // ring radius in pixels
const KAMLOOPS_LAT = 50.6745;
const KAMLOOPS_LON = -120.3273;

/** Convert a lat/lon to (x, y) within the panel, using equirectangular projection
 *  scaled so the furthest station fits inside the ring. */
function project(lat: number, lon: number, maxKm: number) {
  // Approximate km per degree at this latitude.
  const dLat = (lat - KAMLOOPS_LAT) * 111;
  const dLon = (lon - KAMLOOPS_LON) * 111 * Math.cos((KAMLOOPS_LAT * Math.PI) / 180);
  const scale = RADIUS / Math.max(maxKm, 1);
  return { x: CENTER + dLon * scale, y: CENTER - dLat * scale };
}

function distanceKm(lat: number, lon: number) {
  const dLat = (lat - KAMLOOPS_LAT) * 111;
  const dLon = (lon - KAMLOOPS_LON) * 111 * Math.cos((KAMLOOPS_LAT * Math.PI) / 180);
  return Math.sqrt(dLat * dLat + dLon * dLon);
}

export function StationsMap({ stations }: { stations: AqCurrentStation[] }) {
  if (!stations.length) {
    return (
      <div
        style={{
          padding: 36,
          textAlign: "center",
          fontFamily: "var(--font-body)",
          fontSize: 13,
          color: "var(--color-text-low)",
        }}
      >
        No AQHI stations reporting.
      </div>
    );
  }

  // Cap to nearest 12 stations.
  const ranked = [...stations]
    .map((s) => ({ ...s, _km: distanceKm(s.latitude, s.longitude) }))
    .sort((a, b) => a._km - b._km)
    .slice(0, 12);

  const maxKm = Math.max(...ranked.map((s) => s._km), 50);

  // Concentric ring distances (km) — draw 3 rings inside the panel.
  const ringKms = [maxKm / 3, (2 * maxKm) / 3, maxKm];

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 10,
      }}
    >
      <svg
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="img"
        aria-label="AQHI stations around Kamloops"
      >
        {/* Concentric range rings */}
        {ringKms.map((_km, i) => (
          <circle
            key={i}
            cx={CENTER}
            cy={CENTER}
            r={(RADIUS * (i + 1)) / 3}
            fill="none"
            stroke="var(--color-stroke)"
            strokeOpacity={0.55}
            strokeDasharray="3 4"
          />
        ))}
        {/* Cardinal hairlines */}
        <line x1={CENTER} y1={4} x2={CENTER} y2={SIZE - 4} stroke="var(--color-stroke)" strokeOpacity={0.25} />
        <line x1={4} y1={CENTER} x2={SIZE - 4} y2={CENTER} stroke="var(--color-stroke)" strokeOpacity={0.25} />
        {/* Range labels */}
        {ringKms.map((km, i) => (
          <text
            key={`lbl-${i}`}
            x={CENTER + (RADIUS * (i + 1)) / 3 + 4}
            y={CENTER - 2}
            fontSize={8}
            fontFamily="var(--font-data)"
            fill="var(--color-text-low)"
            letterSpacing="0.18em"
          >
            {Math.round(km)} km
          </text>
        ))}

        {/* Kamloops centroid marker */}
        <circle
          cx={CENTER}
          cy={CENTER}
          r={4}
          fill="var(--color-text-hi)"
          stroke="var(--color-ember-500)"
          strokeWidth={1.5}
        />
        <text
          x={CENTER + 8}
          y={CENTER + 4}
          fontSize={10}
          fontFamily="var(--font-data)"
          fill="var(--color-text-mid)"
          letterSpacing="0.12em"
        >
          Kamloops
        </text>

        {/* Station markers */}
        {ranked.map((s) => {
          const { x, y } = project(s.latitude, s.longitude, maxKm);
          const r = s.aqhi != null ? Math.max(5, Math.min(14, 4 + s.aqhi)) : 5;
          const color = s.aqhi != null ? aqhiColor(s.aqhi) : "var(--color-text-low)";
          return (
            <g key={`${s.station_id}-${s.station_name}`}>
              <circle
                cx={x}
                cy={y}
                r={r}
                fill={color}
                opacity={0.85}
                stroke="var(--color-bg-0)"
                strokeWidth={1.5}
              >
                <title>
                  {s.station_name}
                  {s.aqhi != null ? ` · AQHI ${s.aqhi}` : ""}
                  {` · ${Math.round(s._km)} km`}
                </title>
              </circle>
            </g>
          );
        })}
      </svg>
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 9,
          letterSpacing: "0.18em",
          textTransform: "uppercase",
          color: "var(--color-text-low)",
        }}
      >
        Hover a dot · {ranked.length} of {stations.length} nearest stations · ECCC GeoMet AQHI
      </div>
    </div>
  );
}
