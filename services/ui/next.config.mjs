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

const API_BASE = process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") || "http://localhost:8000";

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  allowedDevOrigins: ["http://127.0.0.1:3000", "http://172.27.0.1:3000", "http://localhost:3000"],

  // Forward FastAPI routes to the backend.
  // Next.js route handlers (auth, agent, FHIR proxy) are NOT listed here — they keep their own handlers.
  async rewrites() {
    return [
      {
        source: "/api/patients/:path*",
        destination: `${API_BASE}/patients/:path*`,
      },
      {
        source: "/api/pipeline/:path*",
        destination: `${API_BASE}/pipeline/:path*`,
      },
      {
        source: "/api/operations/:path*",
        destination: `${API_BASE}/operations/:path*`,
      },
      {
        source: "/api/model-registry/:path*",
        destination: `${API_BASE}/model-registry/:path*`,
      },
      {
        source: "/api/training/:path*",
        destination: `${API_BASE}/training/:path*`,
      },
      {
        source: "/api/training-worker/:path*",
        destination: `${process.env.TRAINING_WORKER_URL || "http://localhost:8005"}/train/:path*`,
      },
    ];
  },
};

export default nextConfig;
