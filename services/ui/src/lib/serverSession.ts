/**
 * Server-side session bootstrap.
 *
 * Reads the leo_session cookie on the server and asks core-api for the
 * current session shape. Returning the result from the root layout means
 * the first HTML byte already reflects the authenticated state, so the
 * client never has to render a loading spinner before hydration.
 *
 * This file is server-only -- it must never be imported from a "use client"
 * module.
 *
 * Traceability: DI-LEO-AI-218 (UI shell SSR session bootstrap and cache
 * strategy), VT-LEO-AI-218.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
import { cookies, headers } from "next/headers";
import type { Session, DensityPreference } from "@/lib/authContext";

const INTERNAL_API_BASE = (
  process.env.INTERNAL_API_BASE ?? "http://localhost:8000"
).replace(/\/+$/, "");

const SESSION_COOKIE_NAME = "leo_session";

interface RawSessionPayload {
  user?: { email?: string; name?: string; image?: string } | null;
  isPlatformAdmin?: boolean;
  organizations?: unknown;
  idleTimeoutMinutes?: number;
  selected_role?: string | null;
  allowed_roles?: unknown;
  needs_role_choice?: boolean;
  density_preference?: string | null;
}

function _coerceDensity(value: unknown): DensityPreference | null {
  if (value === "compact" || value === "comfortable" || value === "spacious") {
    return value;
  }
  return null;
}

function _coerceSession(data: RawSessionPayload | null): Session | null {
  if (!data || data.user == null) return null;
  const organizations = Array.isArray(data.organizations) ? data.organizations : [];
  const allowedRoles = Array.isArray(data.allowed_roles)
    ? (data.allowed_roles as string[])
    : [];
  return {
    user: {
      email: data.user.email,
      name: data.user.name,
      image: data.user.image,
    },
    isPlatformAdmin: data.isPlatformAdmin ?? false,
    organizations: organizations as Session["organizations"],
    idleTimeoutMinutes: data.idleTimeoutMinutes ?? 30,
    selectedRole: data.selected_role ?? null,
    allowedRoles,
    needsRoleChoice: data.needs_role_choice === true,
    densityPreference: _coerceDensity(data.density_preference),
  };
}

/**
 * Fetch the current session from core-api using the request cookies.
 *
 * Returns null when no session cookie is present, when core-api is
 * unreachable, or when the upstream returns an unauthenticated payload.
 * Failures must never throw -- the UI must still render an unauthenticated
 * shell that can prompt the user to sign in.
 */
export async function fetchInitialSession(): Promise<Session | null> {
  let cookieHeader = "";
  try {
    const store = await cookies();
    const all = store.getAll();
    if (all.length === 0) return null;
    const hasSession = all.some((c) => c.name === SESSION_COOKIE_NAME);
    if (!hasSession) return null;
    cookieHeader = all.map((c) => `${c.name}=${c.value}`).join("; ");
  } catch {
    return null;
  }

  let forwardedFor: string | null = null;
  try {
    const headerStore = await headers();
    forwardedFor =
      headerStore.get("x-forwarded-for") ?? headerStore.get("x-real-ip");
  } catch {
    forwardedFor = null;
  }

  const requestHeaders: Record<string, string> = {
    cookie: cookieHeader,
    accept: "application/json",
  };
  if (forwardedFor) {
    requestHeaders["x-forwarded-for"] = forwardedFor;
  }

  try {
    const res = await fetch(`${INTERNAL_API_BASE}/auth/session`, {
      method: "GET",
      headers: requestHeaders,
      cache: "no-store",
    });
    if (!res.ok) return null;
    const data = (await res.json()) as RawSessionPayload | null;
    return _coerceSession(data);
  } catch (err) {
    if (process.env.NODE_ENV !== "production") {
      console.warn("[serverSession] fetchInitialSession failed:", err);
    }
    return null;
  }
}
