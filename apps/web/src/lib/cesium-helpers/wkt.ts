/**
 * Minimal WKT parser — no dependency. Handles POINT, POLYGON, MULTIPOLYGON.
 *
 * Returned `positions` is always a flat array of rings:
 *   - "point":        [[lon, lat]]
 *   - "polygon":      [[lon, lat, lon, lat, ...]]   (one ring; outer only)
 *   - "multipolygon": [[lon, lat, ...], [lon, lat, ...], ...] (one entry per polygon outer ring)
 *
 * Inner holes are ignored — adequate for visualizing fires and evac zones.
 */

export type ParsedWkt =
  | { kind: "point"; positions: number[][] }
  | { kind: "polygon"; positions: number[][] }
  | { kind: "multipolygon"; positions: number[][] }
  | null;

function parseCoordList(s: string): number[] {
  // "lon lat, lon lat, ..." → [lon, lat, lon, lat, ...]
  const out: number[] = [];
  const pairs = s.split(",");
  for (const p of pairs) {
    const m = p.trim().match(/(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)/);
    if (!m) continue;
    out.push(parseFloat(m[1]), parseFloat(m[2]));
  }
  return out;
}

export function parseWkt(wkt: string | null | undefined): ParsedWkt {
  if (!wkt) return null;
  const w = wkt.trim();
  const upper = w.toUpperCase();

  if (upper.startsWith("POINT")) {
    const m = w.match(/POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)/i);
    if (!m) return null;
    return { kind: "point", positions: [[parseFloat(m[1]), parseFloat(m[2])]] };
  }

  if (upper.startsWith("MULTIPOLYGON")) {
    // Match each polygon: (((...))) — get every outer ring per polygon.
    // Strip leading "MULTIPOLYGON" then walk the parens.
    const body = w.replace(/^MULTIPOLYGON\s*/i, "");
    // Each polygon is wrapped like ((outer),(hole),...). We need outer rings only.
    const polys: number[][] = [];
    // Find each polygon block: starts with `((`, contains comma-separated rings.
    const polyRe = /\(\(([^()]+)\)(?:\s*,\s*\([^()]+\))*\s*\)/g;
    let m: RegExpExecArray | null;
    while ((m = polyRe.exec(body)) !== null) {
      polys.push(parseCoordList(m[1]));
    }
    if (polys.length === 0) return null;
    return { kind: "multipolygon", positions: polys };
  }

  if (upper.startsWith("POLYGON")) {
    // First ring is outer.
    const m = w.match(/POLYGON\s*\(\s*\(([^()]+)\)/i);
    if (!m) return null;
    return { kind: "polygon", positions: [parseCoordList(m[1])] };
  }

  return null;
}

/** Centroid of a flat [lon,lat,lon,lat,...] ring. Simple average — good enough for labels. */
export function ringCentroid(flat: number[]): [number, number] | null {
  if (flat.length < 2) return null;
  let sx = 0;
  let sy = 0;
  let n = 0;
  for (let i = 0; i + 1 < flat.length; i += 2) {
    sx += flat[i];
    sy += flat[i + 1];
    n++;
  }
  if (n === 0) return null;
  return [sx / n, sy / n];
}
