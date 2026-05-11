import type { Viewer as CesiumViewer } from "cesium";

/**
 * Cesium runs in `requestRenderMode = true` after the intro lands. In that mode
 * the scene only paints when explicitly asked. Entity collection changes
 * mostly trigger this automatically, but some operations (toggle off, imagery
 * layer remove, billboard update) need a manual nudge.
 *
 * Every layer should call this after a batch of add/remove operations.
 */
export function requestRender(viewer: CesiumViewer | null): void {
  if (!viewer || viewer.isDestroyed()) return;
  viewer.scene.requestRender();
}
