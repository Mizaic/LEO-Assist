import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
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
  experimental: {
    proxyTimeout: 300_000, // 5 minutes – extraction pipelines can take 60s+
  },
  // Proxying is handled at runtime by src/middleware.ts so the same
  // Docker image works in any environment without rebuilding.
};

export default nextConfig;
