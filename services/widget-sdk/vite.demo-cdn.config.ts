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

// Builds the CDN-hosted integrator demo card to dist/demo/.
// Deployed to $web/demo/ on the widget origin (see widget-release.yml).

const rootDir = resolve(__dirname, "cdn-demo");
const outDir = resolve(__dirname, "dist/demo");

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
