import type { Viewer as CesiumViewer } from "cesium";

import { cinematicFlyTo } from "@/lib/cesium-helpers/cinematicFlyTo";

export type CameraPreset = {
  id: string;
  label: string;
  subtitle: string;
  lon: number;
  lat: number;
  /** Camera altitude in metres. */
  height: number;
  /** Camera tilt in degrees. -90 = straight down. */
  pitch: number;
  /** Camera bearing in degrees. */
  heading: number;
};

export const PRESETS: CameraPreset[] = [
  {
    id: "canada",
    label: "Globe",
    subtitle: "Canada in view",
    lon: -104.1181,
    lat: 46.2553,
    height: 22_200_000,
    pitch: -90,
    heading: 0,
  },
  {
    id: "region",
    label: "Region",
    subtitle: "Thompson-Okanagan",
    lon: -120.0,
    lat: 50.5,
    height: 320_000,
    pitch: -90,
    heading: 0,
  },
  {
    id: "kamloops",
    label: "Kamloops",
    subtitle: "City core",
    lon: -120.3273,
    lat: 50.6745,
    height: 25_000,
    pitch: -90,
    heading: 0,
  },
  {
    id: "tru",
    label: "TRU Campus",
    subtitle: "Thompson Rivers Univ.",
    lon: -120.3651,
    lat: 50.6712,
    height: 2_400,
    pitch: -90,
    heading: 0,
  },
];

export function flyToPreset(viewer: CesiumViewer, preset: CameraPreset) {
  cinematicFlyTo(viewer, {
    lon: preset.lon,
    lat: preset.lat,
    height: preset.height,
    pitch: preset.pitch,
    heading: preset.heading,
  });
}

export function CameraPresetBar({ viewer }: { viewer: CesiumViewer | null }) {
  if (!viewer) return null;
  return (
    <div
      style={{
        position: "absolute",
        bottom: 56, // leaves room above the bottom-left CoordinateReadout
        right: 16,
        display: "flex",
        flexDirection: "column",
        gap: 8,
        pointerEvents: "auto",
        zIndex: 20,
      }}
    >
      <div
        style={{
          fontFamily: "var(--font-data)",
          fontSize: 9,
          letterSpacing: "0.28em",
          textTransform: "uppercase",
          color: "var(--color-text-low)",
          padding: "2px 6px",
          textAlign: "right",
        }}
      >
        Camera presets
      </div>
      {PRESETS.map((p) => (
        <button
          key={p.id}
          type="button"
          onClick={() => flyToPreset(viewer, p)}
          className="glass"
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "flex-end",
            padding: "10px 14px",
            borderRadius: "var(--radius-md)",
            cursor: "pointer",
            color: "var(--color-text-hi)",
            transition:
              "background var(--dur-fast) var(--ease-out-expo), transform var(--dur-fast) var(--ease-out-expo), box-shadow var(--dur-fast) var(--ease-out-expo)",
            minWidth: 200,
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = "var(--glass-bg-strong)";
            e.currentTarget.style.transform = "translateX(-2px)";
            e.currentTarget.style.boxShadow = "var(--glow-ember-soft)";
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = "";
            e.currentTarget.style.transform = "";
            e.currentTarget.style.boxShadow = "";
          }}
        >
          <span
            style={{
              fontFamily: "var(--font-display)",
              fontSize: 14,
              fontWeight: 600,
              letterSpacing: "-0.01em",
              color: "var(--color-text-hi)",
            }}
          >
            {p.label}
          </span>
          <span
            style={{
              fontFamily: "var(--font-data)",
              fontSize: 9,
              letterSpacing: "0.24em",
              textTransform: "uppercase",
              color: "var(--color-text-low)",
              marginTop: 2,
            }}
          >
            {p.subtitle}
          </span>
        </button>
      ))}
    </div>
  );
}
