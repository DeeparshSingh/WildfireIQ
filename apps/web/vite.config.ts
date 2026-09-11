import path from "node:path";
import { fileURLToPath } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import cesium from "vite-plugin-cesium";
import { defineConfig } from "vitest/config";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // .env lives at the monorepo root, not in apps/web.
  envDir: path.resolve(__dirname, "..", ".."),
  plugins: [react(), tailwindcss(), cesium()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    host: true,
  },
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 4096,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    // jsdom only provides localStorage for a page with a real origin. Without
    // this the global is undefined and any test that touches storage fails
    // with "cannot read properties of undefined", which is easy to misread.
    environmentOptions: { jsdom: { url: "http://localhost/" } },
    setupFiles: ["./src/test-setup.ts"],
    globals: true,
  },
});
