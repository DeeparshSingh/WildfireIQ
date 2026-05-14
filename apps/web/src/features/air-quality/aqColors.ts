/**
 * Health Canada AQHI palette (locked, mirrors design-tokens). Index = AQHI.
 * AQHI 1–3 = Low, 4–6 = Moderate, 7–10 = High, 11+ = Very High.
 */

export function aqhiColor(aqhi: number): string {
  if (aqhi <= 1) return "var(--aq-1)";
  if (aqhi <= 2) return "var(--aq-2)";
  if (aqhi <= 3) return "var(--aq-3)";
  if (aqhi <= 4) return "var(--aq-4)";
  if (aqhi <= 5) return "var(--aq-5)";
  if (aqhi <= 6) return "var(--aq-6)";
  if (aqhi <= 7) return "var(--aq-7)";
  if (aqhi <= 8) return "var(--aq-8)";
  if (aqhi <= 9) return "var(--aq-9)";
  if (aqhi <= 10) return "var(--aq-10)";
  return "var(--aq-plus)";
}

export function aqhiBand(aqhi: number): "Low" | "Moderate" | "High" | "Very High" {
  if (aqhi <= 3) return "Low";
  if (aqhi <= 6) return "Moderate";
  if (aqhi <= 10) return "High";
  return "Very High";
}

/**
 * PM2.5 (µg/m³) → approximate AQHI via Health Canada formula component.
 * Real AQHI also uses NO2 + O3; this is the PM2.5-only approximation, which
 * is the dominant signal in wildfire smoke contexts.
 */
export function pm25ToAqhi(pm25: number): number {
  return (1000 / 10.4) * (Math.exp(0.000487 * pm25) - 1);
}
