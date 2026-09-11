/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL: string;
  readonly VITE_ENABLE_TRU_CARBON?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare const CESIUM_BASE_URL: string;
