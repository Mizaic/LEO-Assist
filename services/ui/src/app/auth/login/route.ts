/**
 * OAuth login relay - server-side.
 *
 * Browser requests /auth/login on the UI origin.
 * This handler calls core-api /auth/login, relays Set-Cookie (nonce),
 * then redirects the browser to Azure AD.
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
  const target = new URL(`${API_BASE}/auth/login`);
  const nextUrl = request.nextUrl.searchParams.get("next_url");
  if (nextUrl) target.searchParams.set("next_url", nextUrl);

  let upstream: Response;
  try {
    upstream = await fetch(target.toString(), {
      method: "GET",
      headers: { cookie: request.headers.get("cookie") || "" },
      redirect: "manual",
    });
  } catch (err) {
    console.error("[auth/login] Failed to reach core-api:", err);
    const redirect = new URL("/sign-in", origin);
    redirect.searchParams.set("error", "Auth service unreachable");
    return NextResponse.redirect(redirect);
  }

  const location = upstream.headers.get("location");
  const destination = location ? new URL(location) : new URL("/sign-in", origin);
  const response = NextResponse.redirect(destination);
  // Prevent Cloudflare or any CDN from caching auth redirect responses.
  response.headers.set("Cache-Control", "no-store");

  _relayCookies(upstream, response);
  return response;
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
    // Domain is intentionally not relayed: the nonce cookie must be scoped
    // to the UI origin, not core-api's internal hostname.
  }

  return { name, value, options };
}

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
