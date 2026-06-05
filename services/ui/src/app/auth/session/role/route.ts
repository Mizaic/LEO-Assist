/**
 * Auth role-selection relay - server-side.
 *
 * PATCH /auth/session/role must remain same-origin in the browser while the UI
 * server forwards the selected role to core-api.
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

export async function PATCH(request: NextRequest) {
  assertE2eModeNotInProduction();
  if (isE2eAuthMode()) {
    return NextResponse.json(
      { ...E2E_SESSION_PAYLOAD, selected_role: "platform_admin" },
      { headers: { "Cache-Control": "no-store" } },
    );
  }
  try {
    return await relayAuthEndpoint(request, "/auth/session/role");
  } catch (err) {
    console.error("[auth/session/role] Failed to reach core-api:", err);
    return NextResponse.json({ detail: "auth_service_unreachable" }, { status: 503 });
  }
}
