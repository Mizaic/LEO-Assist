/**
 * Runtime proxy (formerly middleware.ts, renamed to proxy.ts for Next.js 16).
 *
 * Replaces the build-time rewrites that were previously in next.config.mjs.
 * Reads backend URLs from runtime env vars so the same Docker image works
 * in any environment without rebuilding.
 *
 * Env vars (all have localhost defaults for local dev):
 *   INTERNAL_API_BASE    - core-api  (default http://localhost:8000)
 *   TERMINOLOGY_API_URL  - terminology-api (default http://localhost:8001)
 *   TRAINING_WORKER_URL  - training-worker (default http://localhost:8005)
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

const EXACT_ROUTES: Record<string, () => string> = {
  "/auth/login": () => `${coreApi()}/auth/login`,
  "/auth/logout": () => `${coreApi()}/auth/logout`,
  "/auth/session": () => `${coreApi()}/auth/session`,
  "/api/patients": () => `${coreApi()}/patients`,
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
    prefix: "/api/model-registry/",
    rewrite: (r) => `${coreApi()}/model-registry/${r}`,
  },
  { prefix: "/api/training/", rewrite: (r) => `${coreApi()}/training/${r}` },
  {
    prefix: "/api/training-worker/",
    rewrite: (r) => `${trainWorker()}/train/${r}`,
  },
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
    "/api/training/:path*",
    "/api/training-worker/:path*",
  ],
};
