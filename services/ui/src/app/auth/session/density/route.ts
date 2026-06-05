/**
 * Auth density preference relay - server-side.
 *
 * Keeps density preference writes on the UI origin and forwards them to the
 * authenticated core-api session endpoint.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 */
import { NextRequest, NextResponse } from "next/server";
import { relayAuthEndpoint } from "@/lib/authUpstreamRelay";

export async function PATCH(request: NextRequest) {
  try {
    return await relayAuthEndpoint(request, "/auth/session/density");
  } catch (err) {
    console.error("[auth/session/density] Failed to reach core-api:", err);
    return NextResponse.json({ detail: "auth_service_unreachable" }, { status: 503 });
  }
}
