/**
 * Auto-stamped Atlas trace.
 *
 * Atlas trace:
 *   DO: DO-CD075278
 *   DI: DI-B5EEBC4C
 *   Look up via: get_design_control(dc_type="design-output", dc_id="DO-CD075278")
 */
"use client";

/**
 * Auth context - fetches session from Python backend.
 * Replaces NextAuth. Token stays server-side; frontend uses session cookie only.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { setAuthReauthPolicy } from "@/lib/authReauthPolicy";

function resolveApiBase(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return (process.env.INTERNAL_API_BASE || "http://localhost:8000").replace(/\/+$/, "");
}

const API_BASE = resolveApiBase();

export interface OrgInfo {
  id: string;
  name: string;
  odsCode?: string;
  shortName?: string;
  type?: string;
}

export type DensityPreference = "compact" | "comfortable" | "spacious";

export interface Session {
  user: { email?: string; name?: string; image?: string };
  isPlatformAdmin: boolean;
  organizations: OrgInfo[];
  idleTimeoutMinutes: number;
  selectedRole: string | null;
  allowedRoles: string[];
  /** Multi-role: true until PATCH /auth/session/role for this browser session. */
  needsRoleChoice: boolean;
  densityPreference: DensityPreference | null;
}

interface AuthContextValue {
  session: Session | null;
  status: "loading" | "authenticated" | "unauthenticated";
  signIn: () => void;
  signOut: () => Promise<void>;
  refetch: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

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

function _parseSessionPayload(data: RawSessionPayload | null): Session | null {
  if (!data || data.user == null) return null;
  const rawDensity = data.density_preference;
  const density: DensityPreference | null =
    rawDensity === "compact" ||
    rawDensity === "comfortable" ||
    rawDensity === "spacious"
      ? rawDensity
      : null;
  return {
    user: data.user,
    isPlatformAdmin: data.isPlatformAdmin ?? false,
    organizations: Array.isArray(data.organizations) ? data.organizations : [],
    idleTimeoutMinutes: data.idleTimeoutMinutes ?? 30,
    selectedRole: data.selected_role ?? null,
    allowedRoles: Array.isArray(data.allowed_roles)
      ? (data.allowed_roles as string[])
      : [],
    needsRoleChoice: data.needs_role_choice === true,
    densityPreference: density,
  };
}

export function AuthProvider({
  children,
  initialSession = null,
}: {
  children: ReactNode;
  initialSession?: Session | null;
}) {
  // When the server-rendered layout resolved the session, hydrate straight
  // into "authenticated". When it did not, wait for the client-side
  // /auth/session check before showing the sign-in screen; otherwise ACA
  // users can see a false unauthenticated state immediately after OAuth.
  const [session, setSession] = useState<Session | null>(initialSession);
  const [status, setStatus] = useState<
    "loading" | "authenticated" | "unauthenticated"
  >(initialSession ? "authenticated" : "loading");
  const trustedSessionRef = useRef<Session | null>(initialSession);

  const fetchSession = useCallback(async () => {
    try {
      // Use the Next.js-proxied path (same origin) so the leo_session cookie is
      // always sent. The rewrite in next.config.mjs forwards this to core-api.
      const res = await fetch(`/auth/session`, { credentials: "include" });
      const data = res.ok
        ? ((await res.json()) as RawSessionPayload | null)
        : null;
      const parsed = _parseSessionPayload(data);
      if (parsed) {
        trustedSessionRef.current = parsed;
        setSession(parsed);
        setStatus("authenticated");
        return;
      }
      if (trustedSessionRef.current) {
        // SSR or a prior client fetch already proved the cookie; do not flash
        // unauthenticated when the background refetch is empty or unreachable.
        return;
      }
      setSession(null);
      setStatus("unauthenticated");
    } catch {
      if (trustedSessionRef.current) {
        return;
      }
      setSession(null);
      setStatus("unauthenticated");
    }
  }, []);

  useEffect(() => {
    setAuthReauthPolicy({
      needsRoleChoice: session?.needsRoleChoice === true,
    });
  }, [session?.needsRoleChoice]);

  // Always re-confirm the session on the client so role / density updates
  // made in another tab become visible. When we already hydrated from the
  // server this just refreshes the in-memory copy in the background.
  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  const signIn = useCallback(() => {
    const currentPath = typeof window !== "undefined" ? window.location.pathname : "";
    const isPublicPath = currentPath === "/" || currentPath === "/sign-in" || currentPath.startsWith("/auth/callback");
    const next = isPublicPath ? "/care/dashboard" : currentPath || "/care/dashboard";
    // Use same-origin path so the nonce cookie is set on localhost:3000.
    window.location.href = `/auth/login?next_url=${encodeURIComponent(next)}`;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await fetch(`/auth/logout`, { method: "POST", credentials: "include" });
    } finally {
      trustedSessionRef.current = null;
      setAuthReauthPolicy({ needsRoleChoice: false });
      setSession(null);
      setStatus("unauthenticated");
      if (typeof window !== "undefined") {
        window.location.href = "/";
      }
    }
  }, []);

  const value: AuthContextValue = {
    session,
    status,
    signIn,
    signOut,
    refetch: fetchSession,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
