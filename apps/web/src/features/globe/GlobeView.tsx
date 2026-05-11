/**
 * GlobeView — the home route. The actual <WildfireGlobe> mounts in AppShell
 * so it stays alive across route changes. This component only renders the
 * globe-specific UI overlays, which read the shared viewer reference from
 * the Zustand store.
 */
import { hasCesiumIonToken } from "@/lib/cesium-helpers/init";
import { useGlobeStore } from "@/stores/globe";
import { CameraPresetBar } from "./CameraPresets";
import { CoordinateReadout } from "./CoordinateReadout";
import { FeatureInfoPanel } from "./FeatureInfoPanel";
import { GlobeSetupNotice } from "./GlobeSetupNotice";
import { LayerToggleBar, useLayerKeyboardShortcuts } from "./LayerToggleBar";
import { LocationSearch } from "./LocationSearch";

export function GlobeView() {
  const viewer = useGlobeStore((s) => s.viewer);
  useLayerKeyboardShortcuts();

  if (!hasCesiumIonToken()) {
    return <GlobeSetupNotice />;
  }

  return (
    <>
      <LocationSearch viewer={viewer} />
      <LayerToggleBar />
      <CameraPresetBar viewer={viewer} />
      <CoordinateReadout viewer={viewer} />
      <FeatureInfoPanel />
    </>
  );
}
