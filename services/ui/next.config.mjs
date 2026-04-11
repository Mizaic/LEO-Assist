// aca-image: ui build/deploy verification (comment only; no runtime effect).

import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
// Match Next's getProjectDir() realpath behaviour so rootPath and projectPath
// stay the same physical folder on Windows (8.3 vs long paths, junctions).
let appRoot;
try {
  appRoot = fs.realpathSync(__dirname);
} catch {
  appRoot = path.resolve(__dirname);
}
const secretsDir = path.resolve(__dirname, "../../secrets");

function loadEnvFile(filePath) {
  try {
    if (!fs.existsSync(filePath)) return;
    const content = fs.readFileSync(filePath, "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) continue;
      const eq = trimmed.indexOf("=");
      if (eq < 1) continue;
      const key = trimmed.slice(0, eq).trim();
      let val = trimmed.slice(eq + 1).replace(/\s*#.*$/, "").trim();
      if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
      if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1);
      // override=false: don't overwrite env vars already set (ACA runtime / shell)
      if (!(key in process.env)) process.env[key] = val;
    }
  } catch (_) {}
}

// Load order (later files do NOT override earlier ones -- override=false):
// 1. Non-secret config (safe to commit)
// 2. KV-generated secrets file (git-ignored, run sync-secrets-local.ps1 to populate)
// 3. Legacy combined secrets file (kept for backwards compat; delete once migrated)
loadEnvFile(path.join(secretsDir, ".env.config"));
loadEnvFile(path.join(secretsDir, ".env.secrets"));
loadEnvFile(path.join(secretsDir, ".env"));

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  allowedDevOrigins: ["http://127.0.0.1:3000", "http://172.27.0.1:3000", "http://localhost:3000"],
  // Keep tracing root aligned with turbopack.root (Next warns if they differ).
  outputFileTracingRoot: appRoot,
  turbopack: {
    // Pin root to this app directory to avoid lockfile-based inference.
    root: appRoot,
  },
  experimental: {
    proxyTimeout: 300_000, // 5 minutes – extraction pipelines can take 60s+
  },
  // Legacy un-prefixed routes -> care/admin shell (see AppShell CARE_NAV / ADMIN_NAV).
  async redirects() {
    return [
      { source: "/dashboard", destination: "/care/dashboard", permanent: true },
      { source: "/audit", destination: "/care/audit", permanent: true },
      { source: "/patients", destination: "/care/patients", permanent: true },
      { source: "/patients/:path*", destination: "/care/patients/:path*", permanent: true },
      { source: "/pathways", destination: "/care/pathways", permanent: true },
      { source: "/safety-netting", destination: "/care/safety-netting", permanent: true },
      { source: "/reports", destination: "/care/reports", permanent: true },
      { source: "/reports/:path*", destination: "/care/reports/:path*", permanent: true },
      { source: "/measures", destination: "/care/measures", permanent: true },
      { source: "/measures/:path*", destination: "/care/measures/:path*", permanent: true },
      { source: "/benchmarks", destination: "/care/benchmarks", permanent: true },
      { source: "/benchmarks/:path*", destination: "/care/benchmarks/:path*", permanent: true },
      { source: "/cohorts", destination: "/care/cohorts", permanent: true },
      { source: "/operations", destination: "/admin/operations", permanent: true },
      { source: "/games", destination: "/care/wellbeing", permanent: true },
      { source: "/gold-dataset", destination: "/admin/gold-dataset", permanent: true },
      { source: "/portal", destination: "/care/portal", permanent: true },
    ];
  },
  // Proxying is handled at runtime by src/middleware.ts so the same
  // Docker image works in any environment without rebuilding.
};

export default nextConfig;
