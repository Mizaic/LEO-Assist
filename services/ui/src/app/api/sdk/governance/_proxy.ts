/**
 * Session-gated proxy for Core API host governance.
 *
 * Browser callers must be signed-in platform admins. The shared host
 * secret is never used here; this only writes the in-memory register.
 *
 * Atlas trace:
 *   DO: DO-6F6771E5
 *   DI: DI-14809BB8
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-6F6771E5")
 */
import { type NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";
import { fetchInitialSession } from "@/lib/serverSession";

const CORE_API_BASE = (
  process.env.INTERNAL_API_BASE ??
  process.env.CORE_API_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

export async function requirePlatformAdmin(): Promise<NextResponse | null> {
  const session = await fetchInitialSession();
  if (!session?.user?.email) {
    return NextResponse.json(
      { detail: "Sign in required to manage API hosts." },
      { status: 401 },
    );
  }
  if (!session.isPlatformAdmin) {
    return NextResponse.json(
      { detail: "Admin access required to manage API hosts." },
      { status: 403 },
    );
  }
  return null;
}

export async function proxyGovernance(
  request: NextRequest,
  path: string,
  body?: string,
): Promise<NextResponse> {
  const denied = await requirePlatformAdmin();
  if (denied) return denied;

  const cookie = request.headers.get("cookie") ?? "";
  const headers: Record<string, string> = {
    Accept: "application/json",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    Cookie: cookie,
  };

  let upstream: Response;
  try {
    upstream = await serverFetch(`${CORE_API_BASE}/sdk/governance/${path}`, {
      method: request.method,
      headers,
      body,
    });
  } catch (err) {
    return NextResponse.json(
      { detail: `Core API unreachable: ${String(err)}` },
      { status: 502 },
    );
  }

  const text = await upstream.text();
  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("content-type") ?? "application/json",
    },
  });
}
