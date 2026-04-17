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
// Monorepo root. We point Turbopack here so npm-workspace-hoisted packages
// (next, @leo/design-system, etc.) resolve cleanly from either workspace.
// Without this, Turbopack fails with "we couldn't find next/package.json"
// because npm workspaces hoist to the repo root, not services/ui.
const monorepoRoot = path.resolve(__dirname, "../..");
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

// DI-LEO-AI-140: the NEXT_PUBLIC_ROLE_FIRST rollout flag was removed
// in Phase 6. The role-first shell is the only shipped experience, so
// there is no switch to read here. Any lingering value in the
// environment is ignored by the shell.

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  transpilePackages: ["@leo/design-system"],
  allowedDevOrigins: ["http://127.0.0.1:3000", "http://172.27.0.1:3000", "http://localhost:3000"],
  // Keep tracing root aligned with turbopack.root (Next warns if they differ).
  outputFileTracingRoot: monorepoRoot,
  turbopack: {
    // Pin root to the monorepo root so workspace packages (@leo/design-system)
    // and hoisted dependencies (next, react) resolve cleanly.
    root: monorepoRoot,
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
      { source: "/care/pathways", destination: "/care/encounters", permanent: true },
      { source: "/pathways", destination: "/care/encounters", permanent: true },
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
      // -- Consolidated admin section redirects (permanent 301) --
      // Operations -> Console
      { source: "/admin/operations", destination: "/admin/console", permanent: true },
      // Knowledge
      { source: "/admin/gold-dataset", destination: "/admin/knowledge?tab=training-data", permanent: true },
      { source: "/admin/surface-forms", destination: "/admin/knowledge?tab=surface-forms", permanent: true },
      { source: "/admin/context-rules", destination: "/admin/knowledge?tab=context-rules", permanent: true },
      { source: "/admin/prompts", destination: "/admin/knowledge?tab=ai-instructions", permanent: true },
      { source: "/admin/prompts/:path*", destination: "/admin/knowledge?tab=ai-instructions", permanent: false },
      { source: "/admin/guidance", destination: "/admin/knowledge?tab=clinical-guidelines", permanent: true },
      // Clinical -> Knowledge (Phase 2 IA merge, DI-LEO-AI-135 / R-LEO-AI-093)
      // /admin/clinical has been folded into /admin/knowledge. Every legacy
      // URL is a permanent redirect so bookmarks self-heal on first click.
      { source: "/admin/clinical", destination: "/admin/knowledge", permanent: true },
      { source: "/admin/pathways", destination: "/admin/knowledge?tab=pathways", permanent: true },
      { source: "/admin/domains", destination: "/admin/knowledge?tab=domains", permanent: true },
      { source: "/admin/terminology", destination: "/admin/knowledge?tab=terminology", permanent: true },
      // Platform
      { source: "/admin/billing", destination: "/admin/platform?tab=billing", permanent: true },
      { source: "/admin/models", destination: "/admin/platform?tab=model-config", permanent: true },
      { source: "/admin/data-quality", destination: "/admin/platform?tab=data-quality", permanent: true },
    ];
  },
  // Proxying is handled at runtime by src/middleware.ts so the same
  // Docker image works in any environment without rebuilding.
};

export default nextConfig;
