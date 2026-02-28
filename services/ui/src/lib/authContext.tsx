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
  const envBase =
    typeof process !== "undefined" && process.env?.NEXT_PUBLIC_API_BASE
      ? process.env.NEXT_PUBLIC_API_BASE.replace(/\/+$/, "")
      : "http://localhost:8000";

  if (typeof window === "undefined") return envBase;

  try {
    const parsed = new URL(envBase);
    const uiHost = window.location.hostname;
    const loopbackHosts = new Set(["localhost", "127.0.0.1"]);

    // Align loopback host with the current UI host to avoid SameSite cookie issues.
    if (loopbackHosts.has(parsed.hostname) && loopbackHosts.has(uiHost) && parsed.hostname !== uiHost) {
      parsed.hostname = uiHost;
      return parsed.toString().replace(/\/+$/, "");
    }
  } catch {
    // Keep env value if parsing fails.
  }

  return envBase;
}

const API_BASE = resolveApiBase();

export interface OrgInfo {
  id: string;
  name: string;
  odsCode?: string;
  shortName?: string;
  type?: string;
}

export interface Session {
  user: { email?: string; name?: string; image?: string };
  isPlatformAdmin: boolean;
  organizations: OrgInfo[];
}

interface AuthContextValue {
  session: Session | null;
  status: "loading" | "authenticated" | "unauthenticated";
  signIn: () => void;
  signOut: () => Promise<void>;
  refetch: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [status, setStatus] = useState<"loading" | "authenticated" | "unauthenticated">("loading");

  const fetchSession = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/auth/session`, { credentials: "include" });
      const data = res.ok ? await res.json() : null;
      if (data?.user != null) {
        setSession({
          user: data.user,
          isPlatformAdmin: data.isPlatformAdmin ?? false,
          organizations: data.organizations ?? [],
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

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  const signIn = useCallback(() => {
    const next = typeof window !== "undefined" ? window.location.pathname || "/dashboard" : "/dashboard";
    window.location.href = `${API_BASE}/auth/login?next_url=${encodeURIComponent(next)}`;
  }, []);

  const signOut = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/auth/logout`, { method: "POST", credentials: "include" });
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
