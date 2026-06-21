import { useEffect, useRef } from "react";
import {
  Cartesian3,
  Color,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Entity,
} from "cesium";
import { cellToBoundary } from "h3-js";

import { type RiskCell, useRiskGrid } from "@/lib/api/hooks";
import { requestRender } from "@/lib/cesium-helpers/render";
import { useFiltersStore } from "@/stores/filters";
import { useGlobeStore } from "@/stores/globe";
import { useLayersStore } from "@/stores/layers";

// Match the design-tokens risk palette.
const RISK_COLOR: Record<RiskCell["risk_class"], Color> = {
  Low: Color.fromCssColorString("hsl(140 55% 50%)").withAlpha(0.32),
  Moderate: Color.fromCssColorString("hsl(45 95% 58%)").withAlpha(0.4),
  High: Color.fromCssColorString("hsl(22 100% 56%)").withAlpha(0.48),
  Extreme: Color.fromCssColorString("hsl(0 88% 52%)").withAlpha(0.6),
};
const RISK_STROKE: Record<RiskCell["risk_class"], Color> = {
  Low: Color.fromCssColorString("hsl(140 55% 50%)"),
  Moderate: Color.fromCssColorString("hsl(45 95% 58%)"),
  High: Color.fromCssColorString("hsl(22 100% 56%)"),
  Extreme: Color.fromCssColorString("hsl(0 88% 52%)"),
};

function descriptionFor(c: RiskCell): string {
  return `<table style="font:12px ui-sans-serif,system-ui">
    <tr><td><b>Cell</b></td><td><code>${c.h3_cell}</code></td></tr>
    <tr><td><b>Risk class</b></td><td>${c.risk_class}</td></tr>
    <tr><td><b>P(cell)</b></td><td>${(c.p_cell * 100).toFixed(1)}%</td></tr>
    <tr><td><b>P(region today)</b></td><td>${(c.p_region * 100).toFixed(1)}%</td></tr>
    <tr><td><b>Historical fires</b></td><td>${c.hist_fire_count}</td></tr>
    <tr><td><b>Centroid</b></td><td>${c.centroid_lat.toFixed(3)}, ${c.centroid_lon.toFixed(3)}</td></tr>
  </table>`;
}

export function RiskGridLayer() {
  const viewer = useGlobeStore((s) => s.viewer);
  const gate = useGlobeStore((s) => s.dataGateOpen);
  const visible = useLayersStore((s) => s.visible.risk);
  const hiddenRegions = useFiltersStore((s) => s.risk.hiddenRegions);
  const { data } = useRiskGrid();

  const addedRef = useRef<Entity[]>([]);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);
  const idMapRef = useRef<Map<string, string>>(new Map());

  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;

    const cleanup = () => {
      for (const e of addedRef.current) {
        if (!viewer.isDestroyed()) viewer.entities.remove(e);
      }
      addedRef.current = [];
      idMapRef.current.clear();
      handlerRef.current?.destroy();
      handlerRef.current = null;
      requestRender(viewer);
    };

    if (!gate || !visible || !data) {
      cleanup();
      return cleanup;
    }

    const hidden = new Set(hiddenRegions);
    for (const cell of data.cells) {
      if (hidden.has(cell.region)) continue;
      // h3-js returns boundary as [[lat, lon], ...]
      const boundary = cellToBoundary(cell.h3_cell);
      const flat: number[] = [];
      for (const [lat, lon] of boundary) {
        flat.push(lon, lat);
      }
      const hex = viewer.entities.add({
        polygon: {
          hierarchy: Cartesian3.fromDegreesArray(flat) as never,
          material: RISK_COLOR[cell.risk_class],
          outline: false,
        },
        description: descriptionFor(cell),
      });
      idMapRef.current.set(hex.id, cell.h3_cell);
      addedRef.current.push(hex);

      // Outline as a separate clamped polyline.
      const closed = [...flat];
      if (closed[0] !== closed[closed.length - 2] || closed[1] !== closed[closed.length - 1]) {
        closed.push(closed[0], closed[1]);
      }
      const stroke = viewer.entities.add({
        polyline: {
          positions: Cartesian3.fromDegreesArray(closed),
          width: 1.5,
          material: RISK_STROKE[cell.risk_class],
          clampToGround: true,
        },
        description: descriptionFor(cell),
      });
      idMapRef.current.set(stroke.id, cell.h3_cell);
      addedRef.current.push(stroke);
    }

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(
      (click: ScreenSpaceEventHandler.PositionedEvent) => {
        const picked = viewer.scene.pick(click.position);
        const ent = picked?.id as Entity | undefined;
        if (!ent || !ent.id) return;
        const cellId = idMapRef.current.get(ent.id);
        if (cellId) useLayersStore.getState().select({ kind: "risk", id: cellId });
      },
      ScreenSpaceEventType.LEFT_CLICK,
    );
    handlerRef.current = handler;
    requestRender(viewer);

    return cleanup;
  }, [viewer, gate, visible, data, hiddenRegions]);

  return null;
}
