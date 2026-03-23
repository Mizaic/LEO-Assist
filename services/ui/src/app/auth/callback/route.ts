/**
 * OAuth callback relay - server-side.
 *
 * Azure AD redirects to /auth/callback with code/state.
 * This handler relays callback to core-api, forwards nonce cookie,
 * relays Set-Cookie back to UI origin, then redirects to destination.
 */
import { NextRequest, NextResponse } from "next/server";

const API_BASE =
  (process.env.INTERNAL_API_BASE ?? "http://localhost:8000").replace(/\/+$/, "");

function publicOrigin(request: NextRequest): string {
  const authUrl = (process.env.AUTH_URL ?? "").trim().replace(/\/+$/, "");
  if (authUrl) return authUrl;
  return request.nextUrl.origin;
}

export async function GET(request: NextRequest) {
  const origin = publicOrigin(request);
  const { searchParams } = request.nextUrl;
  const code = searchParams.get("code");
  const state = searchParams.get("state") || "/dashboard";
  const error = searchParams.get("error");
  const errorDescription = searchParams.get("error_description");

  if (error) {
    const redirect = new URL("/sign-in", origin);
    redirect.searchParams.set("error", errorDescription || error);
    return NextResponse.redirect(redirect);
  }

  if (!code) {
    const redirect = new URL("/sign-in", origin);
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
        cookie: request.headers.get("cookie") || "",
      },
      redirect: "manual",
    });
  } catch (err) {
    console.error("[auth/callback] Failed to reach core-api:", err);
    const redirect = new URL("/sign-in", origin);
    redirect.searchParams.set("error", "Auth service unreachable");
    return NextResponse.redirect(redirect);
  }

  const destination = _safeDestination(
    upstream.headers.get("location"),
    state,
    origin,
  );
  const response = NextResponse.redirect(destination);

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
  return [raw];
}
