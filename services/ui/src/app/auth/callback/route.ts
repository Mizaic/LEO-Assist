/**
 * OAuth callback relay - server-side.
 *
 * Azure AD redirects to /auth/callback with code/state.
 * This handler relays callback to core-api, forwards nonce cookie,
 * relays Set-Cookie back to UI origin, then redirects to destination.
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
  const { searchParams } = request.nextUrl;
  const code = searchParams.get("code");
  const state = searchParams.get("state") || "/care/dashboard";
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

  const target = new URL(`${getInternalApiBase()}/auth/callback`);
  target.searchParams.set("code", code);
  target.searchParams.set("state", state);

  let upstream: Awaited<ReturnType<typeof fetchAuthUpstream>>;
  try {
    upstream = await fetchAuthUpstream(
      target.toString(),
      request.headers.get("cookie") || "",
    );
  } catch (err) {
    console.error("[auth/callback] Failed to reach core-api:", err);
    const redirect = new URL("/sign-in", origin);
    redirect.searchParams.set("error", "Auth service unreachable");
    return NextResponse.redirect(redirect);
  }

  const destination = _safeDestination(
    upstream.response.headers.get("location"),
    state,
    origin,
  );
  const response = NextResponse.redirect(destination);
  response.headers.set("Cache-Control", "no-store");
  relayAuthCookies(upstream.setCookieHeaders, response);
  return response;
}

function _safeDestination(
  location: string | null,
  state: string,
  origin: string,
): URL {
  if (location) {
    try {
      const url = new URL(location);
      const isHttp = url.protocol === "http:" || url.protocol === "https:";
      const isOrigin = url.origin === origin;
      const isDevLocalhost =
        process.env.NODE_ENV !== "production" &&
        (url.hostname === "localhost" || url.hostname === "127.0.0.1");
      if (isHttp && (isOrigin || isDevLocalhost)) {
        return new URL(url.pathname + url.search, origin);
      }
    } catch {
      // Ignore malformed location.
    }
  }
  return _safeStatePath(state, origin);
}

function _safeStatePath(state: string, origin: string): URL {
  const trimmed = (state || "").trim();
  const looksAbsolute = /^[a-z][a-z0-9+.-]*:/i.test(trimmed);
  const looksProtocolRelative =
    trimmed.startsWith("//") || trimmed.startsWith("\\\\");
  if (
    !trimmed ||
    looksAbsolute ||
    looksProtocolRelative ||
    trimmed.includes("\\")
  ) {
    return new URL("/care/dashboard", origin);
  }
  let dest = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  dest = dest.replace(/^\/{2,}/, "/");
  if (dest === "/sign-in" || dest === "/") {
    dest = "/care/dashboard";
  }
  try {
    const url = new URL(dest, origin);
    if (url.origin !== origin) {
      return new URL("/care/dashboard", origin);
    }
    return url;
  } catch {
    return new URL("/care/dashboard", origin);
  }
}
