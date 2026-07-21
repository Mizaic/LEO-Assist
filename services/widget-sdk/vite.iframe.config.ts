/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-5C88CA8F
 *   DI: DI-A1206416
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-5C88CA8F")
 */
import { defineConfig } from "vite";
import { resolve } from "node:path";

// Hardened iframe variant build. Emits index.html at dist/iframe/index.html.

const rootDir = resolve(__dirname, "src/iframe-shell");
const outDir = resolve(__dirname, "dist/iframe");

export default defineConfig({
  root: rootDir,
  base: "./",
  build: {
    outDir,
    emptyOutDir: true,
    sourcemap: true,
    target: "es2020",
    rollupOptions: {
      input: resolve(rootDir, "index.html"),
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
