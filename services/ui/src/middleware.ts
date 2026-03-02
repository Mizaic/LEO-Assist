/**
 * Runtime proxy middleware.
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
};

interface PrefixRule {
  prefix: string;
  rewrite: (rest: string) => string;
}

const PREFIX_RULES: PrefixRule[] = [
  { prefix: "/api/proxy/", rewrite: (r) => `${coreApi()}/api/proxy/${r}` },
  { prefix: "/api/patients/", rewrite: (r) => `${coreApi()}/patients/${r}` },
  { prefix: "/api/pipeline/", rewrite: (r) => `${coreApi()}/pipeline/${r}` },
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

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  const exactDest = EXACT_ROUTES[pathname];
  if (exactDest) {
    return NextResponse.rewrite(new URL(exactDest() + search));
  }

  for (const rule of PREFIX_RULES) {
    if (pathname.startsWith(rule.prefix)) {
      const rest = pathname.slice(rule.prefix.length);
      return NextResponse.rewrite(new URL(rule.rewrite(rest) + search));
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    "/auth/login",
    "/auth/logout",
    "/auth/session",
    "/api/proxy/:path*",
    "/api/patients/:path*",
    "/api/pipeline/:path*",
    "/api/terminology/:path*",
    "/api/operations/:path*",
    "/api/model-registry/:path*",
    "/api/training/:path*",
    "/api/training-worker/:path*",
  ],
};
