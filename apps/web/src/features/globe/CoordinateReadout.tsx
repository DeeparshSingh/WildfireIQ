import { useEffect, useState } from "react";
import { Math as CesiumMath } from "cesium";
import type { Viewer as CesiumViewer } from "cesium";

type Readout = {
  lat: number;
  lon: number;
  heightKm: number;
};

function formatLat(lat: number) {
  const hemi = lat >= 0 ? "N" : "S";
  return `${Math.abs(lat).toFixed(4)}°${hemi}`;
}
function formatLon(lon: number) {
  const hemi = lon >= 0 ? "E" : "W";
  return `${Math.abs(lon).toFixed(4)}°${hemi}`;
}
function formatHeight(km: number) {
  if (km < 1) return `${(km * 1000).toFixed(0)} m`;
  if (km < 100) return `${km.toFixed(2)} km`;
  if (km < 10_000) return `${km.toFixed(0)} km`;
  return `${(km / 1000).toFixed(1)} Mm`;
}

export function CoordinateReadout({ viewer }: { viewer: CesiumViewer | null }) {
  const [r, setR] = useState<Readout | null>(null);

  useEffect(() => {
    if (!viewer) return;
    const update = () => {
      const c = viewer.camera.positionCartographic;
      setR({
        lat: CesiumMath.toDegrees(c.latitude),
        lon: CesiumMath.toDegrees(c.longitude),
        heightKm: c.height / 1000,
      });
    };
    update();
    const remove = viewer.camera.changed.addEventListener(update);
    viewer.camera.percentageChanged = 0.001; // fire on small camera moves
    return () => remove();
  }, [viewer]);

  if (!r) return null;

  return (
    <div
      style={{
        position: "absolute",
        left: 24,
        bottom: 24,
        fontFamily: "var(--font-data)",
        fontSize: 10,
        letterSpacing: "0.24em",
        textTransform: "uppercase",
        color: "var(--color-text-low)",
        pointerEvents: "none",
        display: "flex",
        gap: 18,
        alignItems: "center",
      }}
    >
      <span className="live-dot" aria-hidden />
      <span>
        <span style={{ color: "var(--color-text-low)" }}>Lat </span>
        <span className="tabular" style={{ color: "var(--color-text-hi)" }}>
          {formatLat(r.lat)}
        </span>
      </span>
      <span>
        <span style={{ color: "var(--color-text-low)" }}>Lon </span>
        <span className="tabular" style={{ color: "var(--color-text-hi)" }}>
          {formatLon(r.lon)}
        </span>
      </span>
      <span>
        <span style={{ color: "var(--color-text-low)" }}>Alt </span>
        <span className="tabular" style={{ color: "var(--color-text-hi)" }}>
          {formatHeight(r.heightKm)}
        </span>
      </span>
      <span style={{ color: "var(--color-stroke-strong)" }}>·</span>
      <span>Cesium World Terrain · Bing Aerial w/ Labels</span>
    </div>
  );
}
