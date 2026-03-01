/**
 * OAuth callback landing page.
 * Azure AD redirects here with code/state; we forward to the backend to complete
 * the token exchange and set the session cookie.
 */
import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const code = searchParams.get("code");
  const state = searchParams.get("state");
  const error = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");

  if (error) {
    const params = new URLSearchParams({ error });
    if (errorDescription) params.set("error_description", errorDescription);
    return NextResponse.redirect(new URL(`/sign-in?${params}`, request.url));
  }

  if (!code) {
    return NextResponse.redirect(new URL("/sign-in?error=missing_code", request.url));
  }

  const url = new URL(`${API_BASE}/auth/callback`);
  url.searchParams.set("code", code);
  if (state) url.searchParams.set("state", state);

  return NextResponse.redirect(url.toString());
}
