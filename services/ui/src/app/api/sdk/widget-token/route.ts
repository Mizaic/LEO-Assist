/**
 * POST /api/sdk/widget-token
 *
 * Server-side token exchange for the Consumer Validation panel.
 * Proxies to POST {CORE_API}/sdk/auth/exchange using the dev scenario-runner
 * host identity and shared secret. The secret never reaches the browser.
 *
 * Required env vars (see .env.example):
 *   SCENARIO_SDK_HOST_SECRET  -- must match SDK_HOST_SHARED_SECRET in the API
 *     (falls back to SDK_HOST_SHARED_SECRET when unset)
 *   SCENARIO_SDK_HOST_ENABLED -- must be "1" in the API so the host is seeded
 *   SCENARIO_SDK_HOST_ID      -- defaults to "leo-scenario-runner"
 *   SCENARIO_SDK_TENANT_ID    -- defaults to "dev-tenant"
 *
 * Body:  { assessment_id: string }
 * Reply: { widget_token: string, expires_at: number, ttl_seconds: number }
 *
 * Atlas trace:
 *   DO: DO-19BBE973
 *   DI: DI-B746E19E
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-19BBE973")
 */
import { type NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";
import { fetchInitialSession } from "@/lib/serverSession";

const CORE_API_BASE = (
  process.env.INTERNAL_API_BASE ??
  process.env.CORE_API_URL ??
  "http://localhost:8000"
).replace(/\/+$/, "");

export async function POST(request: NextRequest) {
  const session = await fetchInitialSession();
  if (!session?.user?.email) {
    return NextResponse.json(
      { detail: "Sign in required to mint a widget token" },
      { status: 401 },
    );
  }
  if (!session.isPlatformAdmin) {
    return NextResponse.json(
      { detail: "Admin access required to mint a widget token" },
      { status: 403 },
    );
  }

  const hostSecret =
    process.env.SCENARIO_SDK_HOST_SECRET ||
    process.env.SDK_HOST_SHARED_SECRET ||
    "";
  if (!hostSecret) {
    return NextResponse.json(
      {
        detail:
          "SCENARIO_SDK_HOST_SECRET (or SDK_HOST_SHARED_SECRET) is not configured on the UI server",
      },
      { status: 503 },
    );
  }

  let body: { assessment_id?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 });
  }

  const { assessment_id } = body;
  if (!assessment_id) {
    return NextResponse.json(
      { detail: "assessment_id is required" },
      { status: 400 },
    );
  }

  const hostId =
    process.env.SCENARIO_SDK_HOST_ID ?? "leo-scenario-runner";
  const tenantId =
    process.env.SCENARIO_SDK_TENANT_ID ?? "dev-tenant";

  // The exchange endpoint is server-to-server only (it rejects requests
  // that carry an Origin header). serverFetch does not add Origin, so this
  // call passes the server-to-server guard on the API side.
  let upstream: Response;
  try {
    upstream = await serverFetch(`${CORE_API_BASE}/sdk/auth/exchange`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Mizaic-Host-Secret": hostSecret,
      },
      body: JSON.stringify({
        host_id: hostId,
        host_user_id: "scenario-runner",
        tenant_id: tenantId,
        assessment_id,
        user_role: "clinical_reviewer",
      }),
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
