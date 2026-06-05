/**
 * Auth session relay - server-side.
 *
 * Keeps /auth/session on the UI origin so browser CSP and session cookies never
 * depend on the core-api upstream host.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 */
import { NextRequest, NextResponse } from "next/server";
import { relayAuthEndpoint } from "@/lib/authUpstreamRelay";
import {
  E2E_SESSION_PAYLOAD,
  assertE2eModeNotInProduction,
  isE2eAuthMode,
} from "@/lib/e2eSession";

export async function GET(request: NextRequest) {
  assertE2eModeNotInProduction();
  if (isE2eAuthMode()) {
    return NextResponse.json(E2E_SESSION_PAYLOAD, {
      headers: { "Cache-Control": "no-store" },
    });
  }
  try {
    return await relayAuthEndpoint(request, "/auth/session");
  } catch (err) {
    console.error("[auth/session] Failed to reach core-api:", err);
    return NextResponse.json({ detail: "auth_service_unreachable" }, { status: 503 });
  }
}
