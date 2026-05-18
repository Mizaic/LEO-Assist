import { defineConfig } from "vite";
import { resolve } from "node:path";

// CDN bundle build: emits a single ES module at dist/v1/leo-widget.js.
// The custom element self-registers on import. Hosts include this with
// a single <script type="module"> tag.
//
// Atlas trace: DI-85C95E53 (distribution variants); DI-3C06AFD0 (the
// versioned /v1/ path supports CSO-managed manifest rollback).

export default defineConfig({
  build: {
    outDir: "dist/v1",
    emptyOutDir: true,
    sourcemap: true,
    target: "es2020",
    lib: {
      entry: resolve(__dirname, "src/index.ts"),
      formats: ["es"],
      fileName: () => "leo-widget.js",
    },
    rollupOptions: {
      output: {
        inlineDynamicImports: true,
      },
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
