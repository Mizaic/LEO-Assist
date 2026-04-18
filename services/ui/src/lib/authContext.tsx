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
  useState,
  type ReactNode,
} from "react";

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

export function AuthProvider({
  children,
  initialSession = null,
}: {
  children: ReactNode;
  initialSession?: Session | null;
}) {
  // When the server-rendered layout already resolved the session we hydrate
  // straight into "authenticated" (or "unauthenticated") so the UI never
  // shows a loading spinner on the very first paint. Only fall back to
  // "loading" when we genuinely have no information yet (legacy callers
  // that don't pass an initial session).
  const [session, setSession] = useState<Session | null>(initialSession);
  const [status, setStatus] = useState<
    "loading" | "authenticated" | "unauthenticated"
  >(initialSession ? "authenticated" : "unauthenticated");

  const fetchSession = useCallback(async () => {
    try {
      // Use the Next.js-proxied path (same origin) so the leo_session cookie is
      // always sent. The rewrite in next.config.mjs forwards this to core-api.
      const res = await fetch(`/auth/session`, { credentials: "include" });
      const data = res.ok ? await res.json() : null;
      if (data?.user != null) {
        const rawDensity = data.density_preference;
        const density: DensityPreference | null =
          rawDensity === "compact" ||
          rawDensity === "comfortable" ||
          rawDensity === "spacious"
            ? rawDensity
            : null;
        setSession({
          user: data.user,
          isPlatformAdmin: data.isPlatformAdmin ?? false,
          organizations: data.organizations ?? [],
          idleTimeoutMinutes: data.idleTimeoutMinutes ?? 30,
          selectedRole: data.selected_role ?? null,
          allowedRoles: Array.isArray(data.allowed_roles)
            ? data.allowed_roles
            : [],
          densityPreference: density,
        });
        setStatus("authenticated");
      } else {
        setSession(null);
        setStatus("unauthenticated");
      }
    } catch {
      setSession(null);
      setStatus("unauthenticated");
    }
  }, []);

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
