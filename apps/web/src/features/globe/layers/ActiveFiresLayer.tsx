import { useEffect, useRef } from "react";
import {
  Cartesian3,
  Color,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Entity,
} from "cesium";

import { useFiresCurrent, type Fire } from "@/lib/api/hooks";
import { parseWkt, ringCentroid } from "@/lib/cesium-helpers/wkt";
import { useGlobeStore } from "@/stores/globe";
import { useLayersStore } from "@/stores/layers";

const EMBER_500 = "hsl(18 95% 54%)";
const EMBER_700 = "hsl(8 88% 42%)";

// 32x32 flame SVG, ember-500 fill, used as a billboard icon.
const FIRE_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <defs><radialGradient id="g" cx="50%" cy="65%" r="55%">
    <stop offset="0%" stop-color="#FFD18A"/>
    <stop offset="60%" stop-color="#FF5C1A"/>
    <stop offset="100%" stop-color="#B22A0A"/>
  </radialGradient></defs>
  <path fill="url(#g)" stroke="#7a1b06" stroke-width="1"
    d="M16 2 C18 8 24 10 22 18 C28 16 26 26 16 30 C6 26 4 16 10 18 C8 10 14 8 16 2 Z"/>
</svg>`;
const FIRE_ICON_URL =
  "data:image/svg+xml;utf8," + encodeURIComponent(FIRE_SVG);

function descriptionFor(f: Fire): string {
  return `<table style="font:12px ui-sans-serif,system-ui">
    <tr><td><b>Name</b></td><td>${f.fire_name ?? "—"}</td></tr>
    <tr><td><b>Status</b></td><td>${f.status ?? "—"}</td></tr>
    <tr><td><b>Stage</b></td><td>${f.stage_of_control ?? "—"}</td></tr>
    <tr><td><b>Hectares</b></td><td>${f.hectares?.toLocaleString() ?? "—"}</td></tr>
    <tr><td><b>Discovered</b></td><td>${f.discovery_date_utc ?? "—"}</td></tr>
  </table>`;
}

export function ActiveFiresLayer() {
  const viewer = useGlobeStore((s) => s.viewer);
  const visible = useLayersStore((s) => s.visible.fires);
  const { data } = useFiresCurrent();

  const addedRef = useRef<Entity[]>([]);
  const handlerRef = useRef<ScreenSpaceEventHandler | null>(null);
  const idMapRef = useRef<Map<string, string>>(new Map()); // entity.id -> fire_id

  useEffect(() => {
    if (!viewer || viewer.isDestroyed()) return;
    if (!visible || !data) {
      // cleanup only
      for (const e of addedRef.current) viewer.entities.remove(e);
      addedRef.current = [];
      idMapRef.current.clear();
      handlerRef.current?.destroy();
      handlerRef.current = null;
      return;
    }

    const fillColor = Color.fromCssColorString(EMBER_500).withAlpha(0.35);
    const outlineColor = Color.fromCssColorString(EMBER_700);

    for (const f of data) {
      const parsed = parseWkt(f.geom_wkt);
      const isPoly =
        f.geom_kind === "polygon" &&
        parsed &&
        (parsed.kind === "polygon" || parsed.kind === "multipolygon");

      if (isPoly && parsed) {
        const rings =
          parsed.kind === "polygon" ? parsed.positions : parsed.positions;
        for (const ring of rings) {
          if (ring.length < 6) continue;
          const polyEnt = viewer.entities.add({
            polygon: {
              hierarchy: Cartesian3.fromDegreesArray(ring) as never,
              material: fillColor,
              outline: false,
            },
            polyline: undefined,
            description: descriptionFor(f),
          });
          idMapRef.current.set(polyEnt.id, f.fire_id);
          addedRef.current.push(polyEnt);

          // outline as a separate polyline so we can style independently
          const closed = ring.slice();
          if (closed[0] !== closed[closed.length - 2] || closed[1] !== closed[closed.length - 1]) {
            closed.push(closed[0], closed[1]);
          }
          const outlineEnt = viewer.entities.add({
            polyline: {
              positions: Cartesian3.fromDegreesArray(closed),
              width: 2,
              material: outlineColor,
              clampToGround: true,
            },
            description: descriptionFor(f),
          });
          idMapRef.current.set(outlineEnt.id, f.fire_id);
          addedRef.current.push(outlineEnt);

          // centroid billboard
          const c = ringCentroid(ring);
          if (c) {
            const bb = viewer.entities.add({
              position: Cartesian3.fromDegrees(c[0], c[1]),
              billboard: { image: FIRE_ICON_URL, width: 28, height: 28 },
              description: descriptionFor(f),
            });
            idMapRef.current.set(bb.id, f.fire_id);
            addedRef.current.push(bb);
          }
        }
      } else if (
        f.latitude != null &&
        f.longitude != null
      ) {
        const bb = viewer.entities.add({
          position: Cartesian3.fromDegrees(f.longitude, f.latitude),
          billboard: { image: FIRE_ICON_URL, width: 28, height: 28 },
          description: descriptionFor(f),
        });
        idMapRef.current.set(bb.id, f.fire_id);
        addedRef.current.push(bb);
      }
    }

    // click handler
    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click: ScreenSpaceEventHandler.PositionedEvent) => {
      const picked = viewer.scene.pick(click.position);
      const ent = picked?.id as Entity | undefined;
      if (!ent || !ent.id) return;
      const fireId = idMapRef.current.get(ent.id);
      if (fireId) {
        useLayersStore.getState().select({ kind: "fire", id: fireId });
      }
    }, ScreenSpaceEventType.LEFT_CLICK);
    handlerRef.current = handler;

    return () => {
      for (const e of addedRef.current) {
        if (!viewer.isDestroyed()) viewer.entities.remove(e);
      }
      addedRef.current = [];
      idMapRef.current.clear();
      handler.destroy();
      if (handlerRef.current === handler) handlerRef.current = null;
    };
  }, [viewer, visible, data]);

  return null;
}
