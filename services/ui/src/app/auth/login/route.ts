/**
 * OAuth login relay - server-side.
 *
 * Browser requests /auth/login on the UI origin.
 * This handler calls core-api /auth/login, relays Set-Cookie (nonce),
 * then redirects the browser to Azure AD.
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
      headers: {
        cookie: request.headers.get("cookie") || "",
      },
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

  const setCookieHeaders = upstream.headers.getSetCookie
    ? upstream.headers.getSetCookie()
    : _parseSetCookieFallback(upstream.headers.get("set-cookie"));

  for (const cookieStr of setCookieHeaders) {
    response.headers.append("Set-Cookie", cookieStr);
  }

  return response;
}

function _parseSetCookieFallback(raw: string | null): string[] {
  if (!raw) return [];
  return [raw];
}
