import { useEffect, useRef } from "react";
import {
  Cartesian3,
  NearFarScalar,
  ScreenSpaceEventHandler,
  ScreenSpaceEventType,
  type Entity,
} from "cesium";

const BILLBOARD_SCALE = new NearFarScalar(1_000, 1.0, 3_000_000, 0.55);

import { useFwiToday, type FwiStation } from "@/lib/api/hooks";
import { requestRender } from "@/lib/cesium-helpers/render";
import { useGlobeStore } from "@/stores/globe";
import { useLayersStore } from "@/stores/layers";

function colorForFwi(fwi: number | null): string {
  const v = fwi ?? 0;
  if (v < 5) return "#3FB66E"; // risk-low
  if (v < 12) return "#F5C04A"; // risk-moderate
  if (v < 19) return "#FF8A1F"; // risk-high
  return "#EE2A1D"; // risk-extreme
}

function svgFor(fwi: number | null): string {
  const fill = colorForFwi(fwi);
  const label = fwi == null ? "—" : Math.round(fwi).toString();
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
    <circle cx="16" cy="14" r="11" fill="${fill}" stroke="#0a0d14" stroke-width="1.5"/>
    <text x="16" y="18" text-anchor="middle"
      font-family="ui-monospace,SFMono-Regular,Menlo,monospace"
      font-size="11" font-weight="700" fill="#0a0d14"
      style="font-variant-numeric:tabular-nums">${label}</text>
  </svg>`;
  return "data:image/svg+xml;utf8," + encodeURIComponent(svg);
}

function descriptionFor(s: FwiStation): string {
  const row = (k: string, v: number | string | null | undefined) =>
    `<tr><td><b>${k}</b></td><td>${v ?? "—"}</td></tr>`;
  return `<table style="font:12px ui-sans-serif,system-ui;font-variant-numeric:tabular-nums">
    ${row("Station", s.station_name)}
    ${row("Agency", s.agency)}
    ${row("Date", s.observation_date_local)}
    ${row("FFMC", s.ffmc)}
    ${row("DMC", s.dmc)}
    ${row("DC", s.dc)}
    ${row("ISI", s.isi)}
    ${row("BUI", s.bui)}
    ${row("FWI", s.fwi)}
    ${row("DSR", s.dsr)}
  </table>`;
}

export function FWIStationsLayer() {
  const viewer = useGlobeStore((s) => s.viewer);
  const gate = useGlobeStore((s) => s.dataGateOpen);
  const visible = useLayersStore((s) => s.visible.fwi);
  const { data } = useFwiToday();

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

    for (const s of data) {
      const ent = viewer.entities.add({
        position: Cartesian3.fromDegrees(s.longitude, s.latitude),
        billboard: {
          image: svgFor(s.fwi),
          width: 36,
          height: 36,
          scaleByDistance: BILLBOARD_SCALE,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        description: descriptionFor(s),
      });
      idMapRef.current.set(ent.id, s.station_id);
      addedRef.current.push(ent);
    }

    const handler = new ScreenSpaceEventHandler(viewer.scene.canvas);
    handler.setInputAction((click: ScreenSpaceEventHandler.PositionedEvent) => {
      const picked = viewer.scene.pick(click.position);
      const ent = picked?.id as Entity | undefined;
      if (!ent || !ent.id) return;
      const id = idMapRef.current.get(ent.id);
      if (id) useLayersStore.getState().select({ kind: "fwi", id });
    }, ScreenSpaceEventType.LEFT_CLICK);
    handlerRef.current = handler;
    requestRender(viewer);

    return cleanup;
  }, [viewer, gate, visible, data]);

  return null;
}
