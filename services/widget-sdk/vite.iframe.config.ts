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
