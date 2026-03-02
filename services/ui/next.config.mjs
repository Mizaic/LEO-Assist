import path from "path";
import fs from "fs";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const secretsEnv = path.resolve(__dirname, "../../secrets/.env");

// Load secrets/.env so AZURE_REDIS_CONNECTION_STRING etc. are available when running npm run dev standalone
try {
  if (fs.existsSync(secretsEnv)) {
    const content = fs.readFileSync(secretsEnv, "utf-8");
    for (const line of content.split("\n")) {
      const trimmed = line.trim();
      if (trimmed && !trimmed.startsWith("#")) {
        const eq = trimmed.indexOf("=");
        if (eq > 0) {
          const key = trimmed.slice(0, eq).trim();
          let val = trimmed.slice(eq + 1).replace(/\s*#.*$/, "").trim(); // preserve "=" in values
          if (val.startsWith('"') && val.endsWith('"')) val = val.slice(1, -1);
          if (val.startsWith("'") && val.endsWith("'")) val = val.slice(1, -1);
          if (!(key in process.env)) process.env[key] = val;
        }
      }
    }
  }
} catch (_) {}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  allowedDevOrigins: ["http://127.0.0.1:3000", "http://172.27.0.1:3000", "http://localhost:3000"],
  // Proxying is handled at runtime by src/middleware.ts so the same
  // Docker image works in any environment without rebuilding.
};

export default nextConfig;
