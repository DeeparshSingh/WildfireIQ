import { useEffect, useRef } from "react";
import {
  Cartesian3,
  Color,
  NearFarScalar,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Entity,
} from "cesium";

import { useFirmsHotspots, type Hotspot } from "@/lib/api/hooks";
import { requestRender } from "@/lib/cesium-helpers/render";
import { useGlobeStore } from "@/stores/globe";
import { useLayersStore } from "@/stores/layers";

const LOW = Color.fromCssColorString("hsl(28 100% 78%)");
const MID = Color.fromCssColorString("hsl(18 95% 54%)");
const HIGH = Color.fromCssColorString("hsl(8 88% 42%)");
const OUTLINE = Color.fromCssColorString("hsl(220 25% 4%)");

const POINT_SCALE = new NearFarScalar(1_000, 1.0, 4_000_000, 0.4);

function colorForFrp(frp: number | null | undefined): Color {
  const v = frp ?? 0;
  if (v < 5) return LOW;
  if (v <= 30) return MID;
  return HIGH;
}

function sizeForFrp(frp: number | null | undefined): number {
  const v = frp ?? 0;
  return Math.max(6, Math.min(20, 6 + v / 10));
}

function descriptionFor(h: Hotspot): string {
  return `<table style="font:12px ui-sans-serif,system-ui">
    <tr><td><b>Source</b></td><td>${h.source}</td></tr>
    <tr><td><b>Acquired</b></td><td>${h.acq_datetime_utc}</td></tr>
    <tr><td><b>FRP (MW)</b></td><td>${h.frp ?? "—"}</td></tr>
    <tr><td><b>Brightness</b></td><td>${h.brightness ?? "—"}</td></tr>
    <tr><td><b>Confidence</b></td><td>${h.confidence ?? "—"}</td></tr>
    <tr><td><b>Day/Night</b></td><td>${h.daynight ?? "—"}</td></tr>
    <tr><td><b>Satellite</b></td><td>${h.satellite ?? "—"}</td></tr>
  </table>`;
}

export function FIRMSHotspotsLayer() {
  const viewer = useGlobeStore((s) => s.viewer);
  const gate = useGlobeStore((s) => s.dataGateOpen);
  const visible = useLayersStore((s) => s.visible.hotspots);
  const { data } = useFirmsHotspots(24);

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

    for (const h of data) {
      const id = `${h.latitude}-${h.longitude}-${h.acq_datetime_utc}`;
      const ent = viewer.entities.add({
        position: Cartesian3.fromDegrees(h.longitude, h.latitude),
        point: {
          pixelSize: sizeForFrp(h.frp),
          color: colorForFrp(h.frp),
          outlineColor: OUTLINE,
          outlineWidth: 1,
          scaleByDistance: POINT_SCALE,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        description: descriptionFor(h),
      });
      idMapRef.current.set(ent.id, id);
      addedRef.current.push(ent);
    }

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction(
      (click: ScreenSpaceEventHandler.PositionedEvent) => {
        const picked = viewer.scene.pick(click.position);
        const ent = picked?.id as Entity | undefined;
        if (!ent || !ent.id) return;
        const id = idMapRef.current.get(ent.id);
        if (id) useLayersStore.getState().select({ kind: "hotspot", id });
      },
      ScreenSpaceEventType.LEFT_CLICK,
    );
    handlerRef.current = handler;

    requestRender(viewer);
    return cleanup;
  }, [viewer, gate, visible, data]);

  return null;
}
