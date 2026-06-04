/**
 * Server-side core-api auth relay helpers.
 *
 * ACA sets INTERNAL_API_BASE to http://core-api.<env>.azurecontainerapps.io.
 * Ingress upgrades HTTP to HTTPS with a 301 before the app handler runs. The
 * browser must never see that Location; only same-host infra redirects are
 * followed here so the final response (Azure AD or post-login dashboard) and
 * Set-Cookie headers are relayed on the UI origin.
 */
import { NextRequest, NextResponse } from "next/server";
import { serverFetch } from "@/lib/serverFetch";

const MAX_INFRA_REDIRECTS = 5;

export function getInternalApiBase(): string {
  return (process.env.INTERNAL_API_BASE ?? "http://localhost:8000").replace(
    /\/+$/,
    "",
  );
}

export function publicAuthOrigin(request: NextRequest): string {
  const authUrl = (process.env.AUTH_URL ?? "").trim().replace(/\/+$/, "");
  if (authUrl) return authUrl;
  return request.nextUrl.origin;
}

function _isRedirectStatus(status: number): boolean {
  return status === 301 || status === 302 || status === 307 || status === 308;
}

function _collectSetCookies(res: Response): string[] {
  if (res.headers.getSetCookie) {
    return res.headers.getSetCookie();
  }
  const raw = res.headers.get("set-cookie");
  return raw ? [raw] : [];
}

/**
 * GET core-api auth endpoints, following same-host HTTP->HTTPS upgrades only.
 */
export async function fetchAuthUpstream(
  startUrl: string,
  cookieHeader: string,
): Promise<{ response: Response; setCookieHeaders: string[] }> {
  const apiHost = new URL(getInternalApiBase()).host;
  let current = startUrl;
  const setCookieHeaders: string[] = [];

  for (let hop = 0; hop < MAX_INFRA_REDIRECTS; hop += 1) {
    const res = await serverFetch(current, {
      method: "GET",
      headers: { cookie: cookieHeader },
      redirect: "manual",
    });
    setCookieHeaders.push(..._collectSetCookies(res));

    const location = res.headers.get("location");
    if (!location || !_isRedirectStatus(res.status)) {
      return { response: res, setCookieHeaders };
    }

    const next = new URL(location, current);
    const isHttp = next.protocol === "http:" || next.protocol === "https:";
    if (!isHttp || next.host !== apiHost) {
      return { response: res, setCookieHeaders };
    }
    current = next.toString();
  }

  throw new Error("auth upstream: too many same-host redirects");
}

interface CookieOptions {
  httpOnly: boolean;
  secure: boolean;
  sameSite: "strict" | "lax" | "none";
  maxAge?: number;
  path: string;
}

function _parseCookieStr(
  raw: string,
): { name: string; value: string; options: CookieOptions } | null {
  const parts = raw.split(";").map((s) => s.trim());
  const nameValue = parts[0];
  const eqIdx = nameValue.indexOf("=");
  if (eqIdx < 1) return null;

  const name = nameValue.slice(0, eqIdx);
  const value = nameValue.slice(eqIdx + 1);
  const options: CookieOptions = {
    httpOnly: false,
    secure: false,
    sameSite: "lax",
    path: "/",
  };

  for (const attr of parts.slice(1)) {
    const lc = attr.toLowerCase();
    if (lc === "httponly") options.httpOnly = true;
    else if (lc === "secure") options.secure = true;
    else if (lc.startsWith("samesite=")) {
      const sv = lc.slice(9);
      options.sameSite =
        sv === "strict" ? "strict" : sv === "none" ? "none" : "lax";
    } else if (lc.startsWith("max-age=")) {
      options.maxAge = parseInt(lc.slice(8), 10);
    } else if (lc.startsWith("path=")) {
      options.path = attr.slice(5);
    }
  }

  return { name, value, options };
}

/** Relay Set-Cookie values onto the UI redirect (domain is never forwarded). */
export function relayAuthCookies(
  setCookieHeaders: string[],
  response: NextResponse,
): void {
  for (const raw of setCookieHeaders) {
    const parsed = _parseCookieStr(raw);
    if (parsed) {
      response.cookies.set(parsed.name, parsed.value, parsed.options);
    }
  }
}
