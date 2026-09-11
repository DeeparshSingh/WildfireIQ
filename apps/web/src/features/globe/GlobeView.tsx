/**
 * GlobeView — the home route. The actual <WildfireGlobe> mounts in AppShell
 * so it stays alive across route changes. This component only renders the
 * globe-specific UI overlays, which read the shared viewer reference from
 * the Zustand store.
 */
import { useGlobeStore } from "@/stores/globe";
import { useHasCesiumToken } from "@/stores/keys";
import { CameraPresetBar } from "./CameraPresets";
import { CoordinateReadout } from "./CoordinateReadout";
import { FeatureInfoPanel } from "./FeatureInfoPanel";
import { GlobeSetupNotice } from "./GlobeSetupNotice";
import { LayerDetailModal } from "./LayerDetailModal";
import { LayerToggleBar, useLayerKeyboardShortcuts } from "./LayerToggleBar";
import { LocationSearch } from "./LocationSearch";

export function GlobeView() {
  const viewer = useGlobeStore((s) => s.viewer);
  useLayerKeyboardShortcuts();
  const hasToken = useHasCesiumToken();

  if (!hasToken) {
    return <GlobeSetupNotice />;
  }

  return (
    <>
      <LocationSearch viewer={viewer} />
      <LayerToggleBar />
      <CameraPresetBar viewer={viewer} />
      <CoordinateReadout viewer={viewer} />
      <FeatureInfoPanel />
      <LayerDetailModal />
    </>
  );
}
