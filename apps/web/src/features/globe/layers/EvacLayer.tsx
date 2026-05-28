import { useEffect, useRef } from "react";
import {
  Cartesian3,
  Color,
  ColorMaterialProperty,
  PolylineDashMaterialProperty,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Entity,
} from "cesium";

import { isPastEvac, useEvacActive, type EvacZone } from "@/lib/api/hooks";
import { parseWkt } from "@/lib/cesium-helpers/wkt";
import { requestRender } from "@/lib/cesium-helpers/render";
import { useFiltersStore } from "@/stores/filters";
import { useGlobeStore } from "@/stores/globe";
import { useLayersStore } from "@/stores/layers";

type Style = {
  fill: Color;
  outline: Color;
  outlineWidth: number;
  dashed: boolean;
};

const RISK_EXTREME = "hsl(0 88% 52%)";
const RISK_HIGH = "hsl(22 100% 56%)";
const RISK_LOW = "hsl(140 55% 50%)";

function styleFor(status: string | null): Style {
  const s = (status ?? "").toLowerCase();
  if (s.includes("order")) {
    return {
      fill: Color.fromCssColorString(RISK_EXTREME).withAlpha(0.32),
      outline: Color.fromCssColorString(RISK_EXTREME),
      outlineWidth: 2.5,
      dashed: false,
    };
  }
  if (s.includes("alert")) {
    return {
      fill: Color.fromCssColorString(RISK_HIGH).withAlpha(0.22),
      outline: Color.fromCssColorString(RISK_HIGH),
      outlineWidth: 2,
      dashed: true,
    };
  }
  return {
    fill: Color.fromCssColorString(RISK_LOW).withAlpha(0.12),
    outline: Color.fromCssColorString(RISK_LOW),
    outlineWidth: 1.5,
    dashed: false,
  };
}

function descriptionFor(z: EvacZone): string {
  return `<table style="font:12px ui-sans-serif,system-ui">
    <tr><td><b>Name</b></td><td>${z.event_name ?? "—"}</td></tr>
    <tr><td><b>Status</b></td><td>${z.status ?? "—"}</td></tr>
    <tr><td><b>Agency</b></td><td>${z.issuing_agency ?? "—"}</td></tr>
    <tr><td><b>Issued</b></td><td>${z.issued_utc ?? "—"}</td></tr>
    <tr><td><b>Area (ha)</b></td><td>${z.area_hectares?.toLocaleString() ?? "—"}</td></tr>
  </table>`;
}

export function EvacLayer() {
  const viewer = useGlobeStore((s) => s.viewer);
  const gate = useGlobeStore((s) => s.dataGateOpen);
  const visible = useLayersStore((s) => s.visible.evac);
  const hidePast = useFiltersStore((s) => s.evac.hidePast);
  const { data } = useEvacActive();

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

    for (const z of data) {
      // Hide rescinded / no-longer-active zones from the map when the
      // "hide past" control is on (mirrors the modal list filter).
      if (hidePast && isPastEvac(z)) continue;
      const parsed = parseWkt(z.geom_wkt);
      if (!parsed || parsed.kind === "point") continue;
      const rings = parsed.positions;
      const st = styleFor(z.status);
      const zoneId = z.event_id ?? z.event_name ?? z.fetched_at_utc;

      for (const ring of rings) {
        if (ring.length < 6) continue;
        const fillEnt = viewer.entities.add({
          polygon: {
            hierarchy: Cartesian3.fromDegreesArray(ring) as never,
            material: new ColorMaterialProperty(st.fill),
            outline: false,
          },
          description: descriptionFor(z),
        });
        idMapRef.current.set(fillEnt.id, zoneId);
        addedRef.current.push(fillEnt);

        const closed = ring.slice();
        if (closed[0] !== closed[closed.length - 2] || closed[1] !== closed[closed.length - 1]) {
          closed.push(closed[0], closed[1]);
        }
        const outlineEnt = viewer.entities.add({
          polyline: {
            positions: Cartesian3.fromDegreesArray(closed),
            width: st.outlineWidth,
            material: st.dashed
              ? new PolylineDashMaterialProperty({ color: st.outline })
              : new ColorMaterialProperty(st.outline),
            clampToGround: true,
          },
          description: descriptionFor(z),
        });
        idMapRef.current.set(outlineEnt.id, zoneId);
        addedRef.current.push(outlineEnt);
      }
    }

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click: ScreenSpaceEventHandler.PositionedEvent) => {
      const picked = viewer.scene.pick(click.position);
      const ent = picked?.id as Entity | undefined;
      if (!ent || !ent.id) return;
      const id = idMapRef.current.get(ent.id);
      if (id) useLayersStore.getState().select({ kind: "evac", id });
    }, ScreenSpaceEventType.LEFT_CLICK);
    handlerRef.current = handler;
    requestRender(viewer);

    return cleanup;
  }, [viewer, gate, visible, data, hidePast]);

  return null;
}
