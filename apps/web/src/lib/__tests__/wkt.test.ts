/**
 * Tests for the WKT parser that feeds the globe's fire and evacuation polygons.
 *
 * This module had no coverage while containing the trickiest code in the web
 * app: a hand-rolled regex loop over MULTIPOLYGON blocks. The September 2026
 * audit rewrote that loop from `while ((m = re.exec(s)))` to `matchAll`, and
 * these tests pin the behaviour that rewrite had to preserve — in particular
 * that a MULTIPOLYGON yields one ring per polygon rather than only the first.
 */
import { describe, expect, it } from "vitest";

import { parseWkt } from "../cesium-helpers/wkt";

describe("parseWkt", () => {
  it("returns null for empty input", () => {
    expect(parseWkt(null)).toBeNull();
    expect(parseWkt(undefined)).toBeNull();
    expect(parseWkt("")).toBeNull();
  });

  it("parses a POINT into one coordinate pair", () => {
    const p = parseWkt("POINT (-120.3273 50.6745)");
    expect(p).toEqual({ kind: "point", positions: [[-120.3273, 50.6745]] });
  });

  it("parses a POLYGON outer ring into a flat lon,lat array", () => {
    const p = parseWkt("POLYGON ((-120 50, -119 50, -119 51, -120 50))");
    expect(p?.kind).toBe("polygon");
    expect(p?.positions).toHaveLength(1);
    expect(p?.positions[0]).toEqual([-120, 50, -119, 50, -119, 51, -120, 50]);
  });

  it("keeps every polygon of a MULTIPOLYGON, not just the first", () => {
    const p = parseWkt(
      "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 0)), ((5 5, 6 5, 6 6, 5 5)), ((9 9, 10 9, 10 10, 9 9)))",
    );
    expect(p?.kind).toBe("multipolygon");
    expect(p?.positions).toHaveLength(3);
    expect(p?.positions[0]).toEqual([0, 0, 1, 0, 1, 1, 0, 0]);
    expect(p?.positions[2]).toEqual([9, 9, 10, 9, 10, 10, 9, 9]);
  });

  it("ignores interior holes and keeps the outer ring", () => {
    const p = parseWkt(
      "MULTIPOLYGON (((0 0, 10 0, 10 10, 0 0), (2 2, 3 2, 3 3, 2 2)), ((20 20, 21 20, 21 21, 20 20)))",
    );
    expect(p?.positions).toHaveLength(2);
    expect(p?.positions[0]).toEqual([0, 0, 10, 0, 10, 10, 0, 0]);
    expect(p?.positions[1]).toEqual([20, 20, 21, 20, 21, 21, 20, 20]);
  });

  it("is case-insensitive and tolerates the spacing real sources emit", () => {
    // PostGIS and DataBC vary in case, in space after the keyword, and in
    // space around the coordinate commas. None of them put space between the
    // grouping parens, and this parser does not accept that — deliberately,
    // since the regex keys on "((" to find each polygon block.
    const forms = [
      "multipolygon(((0 0,1 0,1 1,0 0)))",
      "MULTIPOLYGON (((0 0, 1 0, 1 1, 0 0)))",
      "  MultiPolygon   (((0 0 ,  1 0 ,  1 1 ,  0 0)))  ",
    ];
    const parsed = forms.map((f) => parseWkt(f));
    for (const p of parsed) {
      expect(p?.kind).toBe("multipolygon");
      expect(p?.positions[0]).toEqual([0, 0, 1, 0, 1, 1, 0, 0]);
    }
  });

  it("handles negative and fractional coordinates", () => {
    const p = parseWkt("POLYGON ((-120.5 50.25, -119.75 50.5, -119.9 51.125, -120.5 50.25))");
    expect(p?.positions[0]).toEqual([-120.5, 50.25, -119.75, 50.5, -119.9, 51.125, -120.5, 50.25]);
  });

  it("returns null for a geometry type it does not support", () => {
    expect(parseWkt("LINESTRING (0 0, 1 1)")).toBeNull();
    expect(parseWkt("GEOMETRYCOLLECTION EMPTY")).toBeNull();
  });

  it("returns null rather than a malformed ring for unparseable input", () => {
    expect(parseWkt("POINT (garbage)")).toBeNull();
    expect(parseWkt("MULTIPOLYGON ()")).toBeNull();
  });
});
