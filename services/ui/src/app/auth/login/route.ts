/**
 * OAuth login relay - server-side.
 *
 * Browser requests /auth/login on the UI origin.
 * This handler calls core-api /auth/login, relays Set-Cookie (nonce),
 * then redirects the browser to Azure AD.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 */
import { NextRequest, NextResponse } from "next/server";
import {
  fetchAuthUpstream,
  getInternalApiBase,
  publicAuthOrigin,
  relayAuthCookies,
} from "@/lib/authUpstreamRelay";

export async function GET(request: NextRequest) {
  const origin = publicAuthOrigin(request);
  const target = new URL(`${getInternalApiBase()}/auth/login`);
  const nextUrl = request.nextUrl.searchParams.get("next_url");
  if (nextUrl) target.searchParams.set("next_url", nextUrl);

  let upstream: Awaited<ReturnType<typeof fetchAuthUpstream>>;
  try {
    upstream = await fetchAuthUpstream(
      target.toString(),
      request.headers.get("cookie") || "",
    );
  } catch (err) {
    console.error("[auth/login] Failed to reach core-api:", err);
    const redirect = new URL("/sign-in", origin);
    redirect.searchParams.set("error", "Auth service unreachable");
    return NextResponse.redirect(redirect);
  }

  const location = upstream.response.headers.get("location");
  const destination = location
    ? new URL(location)
    : new URL("/sign-in", origin);
  const response = NextResponse.redirect(destination);
  response.headers.set("Cache-Control", "no-store");
  relayAuthCookies(upstream.setCookieHeaders, response);
  return response;
}
