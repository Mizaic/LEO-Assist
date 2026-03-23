/**
 * Legacy NextAuth route - redirects to backend auth.
 * Kept for any existing links; new auth uses Python backend.
 *
 * Must redirect same-origin to /auth/login so the browser never follows
 * INTERNAL_API_BASE (e.g. http://core-api), which is not reachable from clients.
 */
import { NextRequest, NextResponse } from "next/server";

function loginRedirect(request: NextRequest) {
  const u = request.nextUrl.clone();
  u.pathname = "/auth/login";
  u.search = "?next_url=/care/dashboard";
  return NextResponse.redirect(u);
}

export async function GET(request: NextRequest) {
  return loginRedirect(request);
}

export async function POST(request: NextRequest) {
  return loginRedirect(request);
}
