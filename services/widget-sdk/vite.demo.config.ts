import { defineConfig } from "vite";
import { resolve } from "node:path";

// Local demo server. Serves both variants from a single Vite dev
// server so Playwright VTs can mount them in real browser pages.
//
// Atlas trace: VTs for DI-85C95E53.
//
// Vite root is the package root so /src/... and /demo/... both
// resolve. The host pages live under /demo/host-pages and the
// iframe shell under /demo/iframe-shell.

export default defineConfig({
  root: resolve(__dirname),
  publicDir: false,
  server: {
    port: 5173,
    strictPort: true,
    open: false,
    cors: { origin: "*" },
    headers: {
      "Access-Control-Allow-Origin": "*",
    },
  },
  resolve: {
    alias: {
      "@": resolve(__dirname, "src"),
    },
  },
});
