/**
 * Runtime proxy (formerly middleware.ts, renamed to proxy.ts for Next.js 16).
 *
 * Replaces the build-time rewrites that were previously in next.config.mjs.
 * Reads backend URLs from runtime env vars so the same Docker image works
 * in any environment without rebuilding.
 *
 * Env vars (all have localhost defaults for local dev):
 *   INTERNAL_API_BASE      - core-api           (default http://localhost:8000)
 *   TERMINOLOGY_API_URL    - terminology-api     (default http://localhost:8001)
 *   TRAINING_WORKER_URL    - training-worker     (default http://localhost:8005)
 *   PIPELINE_WORKER_URL    - pipeline-worker     (default http://localhost:8006)
 *
 * ROUTING NOTE — NextResponse.rewrite() with an absolute external URL
 * short-circuits Next.js routing entirely; App Router Route Handlers are
 * never consulted for paths that hit an external-rewrite middleware rule.
 * Therefore all test-run paths (which belong on the pipeline worker, not
 * the core API) must be declared explicitly here, BEFORE the generic
 * /api/pipeline/ rule, so the first-match wins logic routes them correctly.
 */
import { NextRequest, NextResponse } from "next/server";

function coreApi(): string {
  return (process.env.INTERNAL_API_BASE || "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
}

function termApi(): string {
  return (process.env.TERMINOLOGY_API_URL || "http://localhost:8001").replace(
    /\/+$/,
    "",
  );
}

function trainWorker(): string {
  return (process.env.TRAINING_WORKER_URL || "http://localhost:8005").replace(
    /\/+$/,
    "",
  );
}

function pipelineWorker(): string {
  return (process.env.PIPELINE_WORKER_URL || "http://localhost:8006").replace(
    /\/+$/,
    "",
  );
}

const EXACT_ROUTES: Record<string, () => string> = {
  "/auth/login": () => `${coreApi()}/auth/login`,
  "/auth/logout": () => `${coreApi()}/auth/logout`,
  "/auth/session": () => `${coreApi()}/auth/session`,
  "/api/patients": () => `${coreApi()}/patients`,
  "/api/prompts": () => `${coreApi()}/prompts`,
};

interface PrefixRule {
  prefix: string;
  rewrite: (rest: string) => string;
}

const PREFIX_RULES: PrefixRule[] = [
  { prefix: "/api/admin/", rewrite: (r) => `${coreApi()}/admin/${r}` },
  { prefix: "/api/mail/", rewrite: (r) => `${coreApi()}/mail/${r}` },
  { prefix: "/api/proxy/", rewrite: (r) => `${coreApi()}/api/proxy/${r}` },
  { prefix: "/api/patients/", rewrite: (r) => `${coreApi()}/patients/${r}` },
  // ── Pipeline Worker routes (must come BEFORE the generic /api/pipeline/ rule) ──
  // All interactive dry-run endpoints run on the pipeline worker, not the Core API,
  // so that LLM/NLP work does not compete with live API request serving.
  { prefix: "/api/pipeline/test-run", rewrite: (r) => `${pipelineWorker()}/test-run${r}` },
  // ── Core API — all other pipeline endpoints (production runs, stats, etc.) ──
  { prefix: "/api/pipeline/", rewrite: (r) => `${coreApi()}/pipeline/${r}` },
  { prefix: "/api/review/", rewrite: (r) => `${coreApi()}/review/${r}` },
  { prefix: "/api/exports/", rewrite: (r) => `${coreApi()}/exports/${r}` },
  { prefix: "/api/games/", rewrite: (r) => `${coreApi()}/games/${r}` },
  {
    prefix: "/api/terminology/",
    rewrite: (r) => `${termApi()}/terminology/${r}`,
  },
  {
    prefix: "/api/operations/",
    rewrite: (r) => `${coreApi()}/operations/${r}`,
  },
  {
    prefix: "/api/model-registry/inference/",
    rewrite: (r) => `${coreApi()}/model-registry/inference/${r}`,
  },
  {
    prefix: "/api/model-registry/",
    rewrite: (r) => `${coreApi()}/model-registry/${r}`,
  },
  {
    prefix: "/api/devices/",
    rewrite: (r) => `${coreApi()}/devices/${r}`,
  },
  { prefix: "/api/devices", rewrite: () => `${coreApi()}/devices` },
  { prefix: "/api/presets/", rewrite: (r) => `${coreApi()}/presets/${r}` },
  { prefix: "/api/presets", rewrite: () => `${coreApi()}/presets` },
  { prefix: "/api/prompts/", rewrite: (r) => `${coreApi()}/prompts/${r}` },
  { prefix: "/api/training/", rewrite: (r) => `${coreApi()}/training/${r}` },
  {
    prefix: "/api/training-worker/",
    rewrite: (r) => `${trainWorker()}/train/${r}`,
  },
  { prefix: "/api/analytics/", rewrite: (r) => `${coreApi()}/analytics/${r}` },
  { prefix: "/api/pricing/", rewrite: (r) => `${coreApi()}/pricing/${r}` },
  { prefix: "/api/pricing", rewrite: () => `${coreApi()}/pricing` },
  { prefix: "/api/model-configs/", rewrite: (r) => `${coreApi()}/model-configs/${r}` },
  { prefix: "/api/model-configs", rewrite: () => `${coreApi()}/model-configs` },
  { prefix: "/api/service-configs/", rewrite: (r) => `${coreApi()}/service-configs/${r}` },
  { prefix: "/api/service-configs", rewrite: () => `${coreApi()}/service-configs` },
  { prefix: "/api/nice/", rewrite: (r) => `${coreApi()}/nice/${r}` },
  { prefix: "/api/guidance/", rewrite: (r) => `${coreApi()}/guidance/${r}` },
];

function proxyRewrite(request: NextRequest, dest: string): NextResponse {
  // Forward X-Requested-With so the Core API CSRF check passes.
  const headers = new Headers(request.headers);
  headers.set("X-Requested-With", "XMLHttpRequest");
  return NextResponse.rewrite(new URL(dest), { request: { headers } });
}

function termApiRewrite(request: NextRequest, dest: string): NextResponse {
  // Forward X-Requested-With and inject the shared service secret so that
  // write endpoints protected by verify_service_token accept the request.
  const headers = new Headers(request.headers);
  headers.set("X-Requested-With", "XMLHttpRequest");
  const secret = process.env.SERVICE_AUTH_SECRET;
  if (secret) headers.set("Authorization", `Bearer ${secret}`);
  return NextResponse.rewrite(new URL(dest), { request: { headers } });
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  const exactDest = EXACT_ROUTES[pathname];
  if (exactDest) {
    return proxyRewrite(request, exactDest() + search);
  }

  for (const rule of PREFIX_RULES) {
    if (pathname.startsWith(rule.prefix)) {
      const rest = pathname.slice(rule.prefix.length);
      const rewriteFn = rule.prefix === "/api/terminology/"
        ? termApiRewrite
        : proxyRewrite;
      return rewriteFn(request, rule.rewrite(rest) + search);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/api/admin/:path*",
    "/api/mail/:path*",
    "/auth/login",
    "/auth/logout",
    "/auth/session",
    "/api/proxy/:path*",
    "/api/patients/:path*",
    "/api/pipeline/:path*",
    "/api/review/:path*",
    "/api/exports/:path*",
    "/api/games/:path*",
    "/api/terminology/:path*",
    "/api/operations/:path*",
    "/api/model-registry/:path*",
    "/api/devices",
    "/api/devices/:path*",
    "/api/presets",
    "/api/presets/:path*",
    "/api/prompts",
    "/api/prompts/:path*",
    "/api/training/:path*",
    "/api/training-worker/:path*",
    "/api/analytics/:path*",
    "/api/pricing",
    "/api/pricing/:path*",
    "/api/model-configs",
    "/api/model-configs/:path*",
    "/api/service-configs",
    "/api/service-configs/:path*",
    "/api/nice/:path*",
    "/api/guidance/:path*",
  ],
};
