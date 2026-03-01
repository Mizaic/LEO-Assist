/**
 * OAuth callback relay - server-side.
 *
 * Azure AD redirects here (http://localhost:3000/auth/callback) after login.
 * This handler fetches the core-api callback server-side so that the
 * leo_session cookie is issued from localhost:3000 (the UI origin), not from
 * localhost:8000. This avoids cross-port cookie delivery issues where some
 * browsers silently drop credentials-include cookies that were set by a
 * different port.
 *
 * Flow:
 *   1. Azure AD -> localhost:3000/auth/callback?code=...
 *   2. This handler POSTs the code to core-api server-side (forwarding the
 *      leo_oauth_nonce cookie for CSRF validation).
 *   3. Core-api exchanges the code, saves the session in Redis, and returns
 *      a 302 redirect with Set-Cookie.
 *   4. We capture the Set-Cookie header and relay it to the browser under the
 *      localhost:3000 origin, then redirect to the intended page.
 */
import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/+$/, "") ||
  "http://localhost:8000";

export async function GET(request: NextRequest) {
  const { searchParams } = request.nextUrl;
  const code = searchParams.get("code");
  const state = searchParams.get("state") || "/dashboard";
  const error = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");

  if (error) {
    const redirect = new URL("/sign-in", request.nextUrl.origin);
    redirect.searchParams.set("error", errorDescription || error);
    return NextResponse.redirect(redirect);
  }

  if (!code) {
    const redirect = new URL("/sign-in", request.nextUrl.origin);
    redirect.searchParams.set("error", "No authorisation code returned");
    return NextResponse.redirect(redirect);
  }

  const target = new URL(`${API_BASE}/auth/callback`);
  target.searchParams.set("code", code);
  target.searchParams.set("state", state);

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), {
      method: "GET",
      headers: {
        // Forward the nonce cookie so core-api can validate the OAuth state.
        cookie: request.headers.get("cookie") || "",
      },
      redirect: "manual",
    });
  } catch (err) {
    console.error("[auth/callback] Failed to reach core-api:", err);
    const redirect = new URL("/sign-in", request.nextUrl.origin);
    redirect.searchParams.set("error", "Auth service unreachable");
    return NextResponse.redirect(redirect);
  }

  const destination = _safeDestination(upstream.headers.get("location"), state, request.nextUrl.origin);
  const response = NextResponse.redirect(destination);

  // Relay Set-Cookie headers from core-api onto the UI origin so the browser
  // receives the session cookie from localhost:3000 (same origin as the UI).
  const setCookieHeaders = upstream.headers.getSetCookie
    ? upstream.headers.getSetCookie()
    : _parseSetCookieFallback(upstream.headers.get("set-cookie"));

  for (const cookieStr of setCookieHeaders) {
    response.headers.append("Set-Cookie", cookieStr);
  }

  return response;
}

function _safeDestination(location: string | null, state: string, origin: string): URL {
  if (location) {
    try {
      const url = new URL(location);
      // Only follow redirects back to the frontend origin.
      if (url.origin === origin || url.hostname === "localhost") {
        return new URL(url.pathname + url.search, origin);
      }
    } catch {
      // Ignore malformed location.
    }
  }
  const dest = state.startsWith("/") ? state : `/${state}`;
  return new URL(dest === "/sign-in" || dest === "/" ? "/dashboard" : dest, origin);
}

function _parseSetCookieFallback(raw: string | null): string[] {
  if (!raw) return [];
  // Naive split - only handles the common single-cookie case in older runtimes.
  return [raw];
}
