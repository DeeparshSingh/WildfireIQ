import { useEffect, useRef } from "react";
import {
  Rectangle,
  SingleTileImageryProvider,
  type ImageryLayer,
} from "cesium";

import { useSmokeForecast } from "@/lib/api/hooks";
import { requestRender } from "@/lib/cesium-helpers/render";
import { useGlobeStore } from "@/stores/globe";
import { useLayersStore } from "@/stores/layers";
import { useSmokeStore } from "@/stores/smoke";

// Thompson-Okanagan region bbox (lon_min, lat_min, lon_max, lat_max)
const SMOKE_RECT = Rectangle.fromDegrees(-121.5, 50.0, -118.5, 51.5);

export function SmokeLayer() {
  const viewer = useGlobeStore((s) => s.viewer);
  const gate = useGlobeStore((s) => s.dataGateOpen);
  const visible = useLayersStore((s) => s.visible.smoke);
  const { data } = useSmokeForecast();
  const timestepIndex = useSmokeStore((s) => s.timestepIndex);

  const layerRef = useRef<ImageryLayer | null>(null);

  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const removeExisting = () => {
      if (layerRef.current && !viewer.isDestroyed()) {
        viewer.imageryLayers.remove(layerRef.current, true);
      }
      layerRef.current = null;
      requestRender(viewer);
    };

    if (!gate || !visible || !data || data.length === 0) {
      removeExisting();
      return removeExisting;
    }

    // Clamp to the available timesteps if the user has scrubbed past the end.
    const safeIndex = Math.min(Math.max(0, timestepIndex), data.length - 1);
    const chosen = data[safeIndex];
    let cancelled = false;

    (async () => {
      try {
        const provider = await SingleTileImageryProvider.fromUrl(chosen.fetch_url, {
          rectangle: SMOKE_RECT,
        });
        if (cancelled || viewer.isDestroyed()) return;
        removeExisting();
        const lyr = viewer.imageryLayers.addImageryProvider(provider);
        lyr.alpha = 0.55;
        lyr.dayAlpha = 0.55;
        lyr.nightAlpha = 0.55;
        layerRef.current = lyr;
        requestRender(viewer);
      } catch (err) {
        console.warn("[SmokeLayer] failed to load smoke imagery", err);
      }
    })();

    return () => {
      cancelled = true;
      removeExisting();
    };
  }, [viewer, gate, visible, data, timestepIndex]);

  return null;
}
