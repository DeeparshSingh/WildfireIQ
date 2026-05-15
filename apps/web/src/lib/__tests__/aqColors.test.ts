/**
 * AQHI utilities — pure functions, no I/O. Locks the contract the
 * AqhiDial, StationsMap, and PollutantBars all rely on.
 */
import { describe, expect, it } from "vitest";

import { aqhiBand, aqhiColor, pm25ToAqhi } from "../../features/air-quality/aqColors";

describe("aqhiColor", () => {
  it("returns a CSS var for every integer 1..11", () => {
    for (let i = 1; i <= 11; i++) {
      const c = aqhiColor(i);
      expect(typeof c).toBe("string");
      expect(c.startsWith("var(")).toBe(true);
    }
  });
  it("maps the plus bucket for very-high values", () => {
    expect(aqhiColor(11)).toBe("var(--aq-plus)");
    expect(aqhiColor(99)).toBe("var(--aq-plus)");
  });
});

describe("aqhiBand", () => {
  it.each([
    [1, "Low"],
    [3, "Low"],
    [4, "Moderate"],
    [6, "Moderate"],
    [7, "High"],
    [10, "High"],
    [11, "Very High"],
  ])("AQHI %i → %s", (a, band) => {
    expect(aqhiBand(a)).toBe(band);
  });
});

describe("pm25ToAqhi", () => {
  it("returns 0 at PM2.5 = 0", () => {
    expect(pm25ToAqhi(0)).toBeCloseTo(0, 6);
  });
  it("monotonically increases with PM2.5", () => {
    const samples = [10, 25, 50, 100, 250].map(pm25ToAqhi);
    for (let i = 1; i < samples.length; i++) {
      expect(samples[i]).toBeGreaterThan(samples[i - 1]);
    }
  });
  it("matches Health Canada PM2.5 ≈ 70 → AQHI ≈ 3 within tolerance", () => {
    // Health Canada's PM2.5-only AQHI component at 70 µg/m³ is ≈ 3.3.
    expect(pm25ToAqhi(70)).toBeGreaterThan(2.5);
    expect(pm25ToAqhi(70)).toBeLessThan(4);
  });
});
