import { PlaceholderCard } from "../_PlaceholderCard";

export function AboutView() {
  return (
    <PlaceholderCard
      phase="About"
      title="WildfireIQ Kamloops"
      blurb="An AI-powered wildfire risk, air quality, and community preparedness platform for the Thompson-Okanagan region. Built by Deeparsh Singh Dang at Thompson Rivers University with the support of the TRU Sustainability Research Grant for Students 2025-2026."
    >
      <div
        style={{
          marginTop: 24,
          fontFamily: "var(--font-data)",
          fontSize: 12,
          lineHeight: 1.6,
          color: "var(--color-text-low)",
          paddingTop: 24,
          borderTop: "1px solid var(--color-stroke)",
        }}
      >
        Data: BC Wildfire Service · Environment & Climate Change Canada · NASA FIRMS ·
        Open-Meteo · Natural Resources Canada CWFIS · BC Air Data Archive · WAQI ·
        ClimateData.ca · BC Emergency Management · OpenStreetMap · Copernicus Sentinel-2 ·
        Cesium ion · Cesium OSM Buildings.
      </div>
    </PlaceholderCard>
  );
}
