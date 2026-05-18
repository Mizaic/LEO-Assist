/**
 * OAuth callback relay - server-side.
 *
 * Azure AD redirects to /auth/callback with code/state.
 * This handler relays callback to core-api, forwards nonce cookie,
 * relays Set-Cookie back to UI origin, then redirects to destination.
 *
 * Cookies are relayed via response.cookies.set() (not raw header append)
 * to ensure Next.js includes them on redirect responses.
 *
 * Atlas trace:
 *   DO: DO-21936FDD
 *   DI: DI-09DF0A10
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-21936FDD")
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

  const target = new URL(`${API_BASE}/auth/callback`);
  target.searchParams.set("code", code);
  target.searchParams.set("state", state);

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), {
      method: "GET",
      headers: { cookie: request.headers.get("cookie") || "" },
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
  // Prevent Cloudflare or any CDN from caching auth redirect responses.
  response.headers.set("Cache-Control", "no-store");

  _relayCookies(upstream, response);
  return response;
}

/**
 * Build a redirect URL that is guaranteed to live on the UI origin.
 *
 * Why the strict checks:
 *   - `URL` accepts scheme-relative inputs like `//evil.example/x` that
 *     would otherwise route the browser off-origin if naively appended.
 *   - The upstream `Location` header is attacker-influenceable via
 *     redirect_uri / state on the OAuth callback, so we only honour it
 *     when its scheme is http(s) AND its origin exactly matches the UI
 *     origin. Localhost is never trusted in production, only in dev
 *     (NODE_ENV !== "production").
 *   - Any `state` string is forced to be an absolute UI path. We strip
 *     leading slashes and rebuild from `origin` to defeat
 *     `state=//evil.example/x` and `state=https://evil.example`.
 */
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
  // Reject anything that could escape the origin: absolute URLs, schemes,
  // backslashes (interpreted as separators by some browsers), or
  // protocol-relative paths starting with "//".
  const looksAbsolute = /^[a-z][a-z0-9+.-]*:/i.test(trimmed);
  const looksProtocolRelative = trimmed.startsWith("//") || trimmed.startsWith("\\\\");
  if (!trimmed || looksAbsolute || looksProtocolRelative || trimmed.includes("\\")) {
    return new URL("/care/dashboard", origin);
  }
  let dest = trimmed.startsWith("/") ? trimmed : `/${trimmed}`;
  // Collapse any leading run of slashes to a single slash so /////evil
  // cannot be reinterpreted as a host by URL().
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

/**
 * Relay upstream Set-Cookie headers onto the Next.js response using
 * response.cookies.set() so Next.js serialises them correctly on redirects.
 * Raw response.headers.append("Set-Cookie", ...) can be silently dropped.
 */
function _relayCookies(upstream: Response, response: NextResponse): void {
  const rawHeaders = upstream.headers.getSetCookie
    ? upstream.headers.getSetCookie()
    : _fallbackSetCookies(upstream.headers.get("set-cookie"));

  for (const raw of rawHeaders) {
    const parsed = _parseCookieStr(raw);
    if (parsed) {
      response.cookies.set(parsed.name, parsed.value, parsed.options);
    }
  }
}

function _fallbackSetCookies(raw: string | null): string[] {
  return raw ? [raw] : [];
}

interface CookieOptions {
  httpOnly: boolean;
  secure: boolean;
  sameSite: "strict" | "lax" | "none";
  maxAge?: number;
  path: string;
}

function _parseCookieStr(raw: string): { name: string; value: string; options: CookieOptions } | null {
  const parts = raw.split(";").map((s) => s.trim());
  const nameValue = parts[0];
  const eqIdx = nameValue.indexOf("=");
  if (eqIdx < 1) return null;

  const name = nameValue.slice(0, eqIdx);
  const value = nameValue.slice(eqIdx + 1);
  const options: CookieOptions = { httpOnly: false, secure: false, sameSite: "lax", path: "/" };

  for (const attr of parts.slice(1)) {
    const lc = attr.toLowerCase();
    if (lc === "httponly") options.httpOnly = true;
    else if (lc === "secure") options.secure = true;
    else if (lc.startsWith("samesite=")) {
      const sv = lc.slice(9);
      options.sameSite = sv === "strict" ? "strict" : sv === "none" ? "none" : "lax";
    } else if (lc.startsWith("max-age=")) {
      options.maxAge = parseInt(lc.slice(8), 10);
    } else if (lc.startsWith("path=")) {
      options.path = attr.slice(5);
    }
    // Domain is intentionally not relayed: the cookie must be scoped to the
    // UI origin (leo-ai-audit.healthcarecopilot.ai), not core-api's hostname.
  }

  return { name, value, options };
}
