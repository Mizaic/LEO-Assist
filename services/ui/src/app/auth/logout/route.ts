/**
 * Auth logout relay - server-side.
 *
 * Keeps logout on the UI origin while forwarding the session-clearing request
 * to core-api.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 */
import { NextRequest, NextResponse } from "next/server";
import { relayAuthEndpoint } from "@/lib/authUpstreamRelay";

export async function POST(request: NextRequest) {
  try {
    return await relayAuthEndpoint(request, "/auth/logout");
  } catch (err) {
    console.error("[auth/logout] Failed to reach core-api:", err);
    return NextResponse.json({ detail: "auth_service_unreachable" }, { status: 503 });
  }
}
