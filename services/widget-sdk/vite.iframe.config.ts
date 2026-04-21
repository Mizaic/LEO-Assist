import { defineConfig } from "vite";
import { resolve } from "node:path";

// Hardened iframe variant build. Emits a static index.html at
// dist/iframe/sbar/index.html that boots the same widget surface
// without a Shadow DOM (the iframe IS the trust boundary).
//
// Atlas trace: DI-85C95E53 acceptance criterion 1 (one source tree,
// two variants).

export default defineConfig({
  build: {
    outDir: "dist/iframe",
    emptyOutDir: true,
    sourcemap: true,
    target: "es2020",
    rollupOptions: {
      input: resolve(__dirname, "src/iframe-shell/index.html"),
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
