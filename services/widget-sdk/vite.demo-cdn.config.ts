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
