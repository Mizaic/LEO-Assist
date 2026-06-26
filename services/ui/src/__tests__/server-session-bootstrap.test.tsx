/**
 * VT-LEO-AI-218 - Server-side session bootstrap.
 *
 * Verifies that the root layout resolves the user's session on the server
 * via fetchInitialSession() and that the AuthProvider hydrates straight
 * into "authenticated" when SSR found a session, or waits for the
 * client-side session check before showing an unauthenticated state.
 * This avoids a false sign-in screen after OAuth when SSR misses a cookie.
 *
 * Traceability: DI-LEO-AI-218 (UI shell SSR session bootstrap and cache
 * strategy), R-LEO-AI-205 (stale prerender hides authenticated content).
 */

import React from "react";
import { render, waitFor } from "@testing-library/react";
import * as fs from "fs";
import * as path from "path";

import { AuthProvider, useAuth, type Session } from "@/lib/authContext";

const SAMPLE_SESSION: Session = {
  user: { email: "clinician@example.com", name: "Dr Example" },
  isPlatformAdmin: false,
  organizations: [],
  idleTimeoutMinutes: 30,
  selectedRole: "triage_clinician",
  allowedRoles: ["triage_clinician"],
  needsRoleChoice: false,
  densityPreference: "comfortable",
};

beforeEach(() => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ user: null }),
    }),
  ) as unknown as jest.Mock;
});

function StatusProbe({
  capture,
}: {
  capture: (value: ReturnType<typeof useAuth>) => void;
}) {
  const value = useAuth();
  React.useEffect(() => {
    capture(value);
  }, [capture, value]);
  return null;
}

describe("VT-LEO-AI-218 SSR session bootstrap", () => {
  test("TC-001 AuthProvider hydrates straight into authenticated when given an initial session", async () => {
    const captured: Array<ReturnType<typeof useAuth>> = [];
    render(
      <AuthProvider initialSession={SAMPLE_SESSION}>
        <StatusProbe capture={(value) => captured.push(value)} />
      </AuthProvider>,
    );
    expect(captured.length).toBeGreaterThan(0);
    // The very first render must already be authenticated -- no loading flash.
    expect(captured[0].status).toBe("authenticated");
    expect(captured[0].session?.user.email).toBe("clinician@example.com");
    // The background refetch must not regress us back to loading.
    await waitFor(() => {
      const last = captured[captured.length - 1];
      expect(last.status).not.toBe("loading");
    });
  });

  test("TC-002 AuthProvider with no initial session waits for client session check", async () => {
    const captured: Array<ReturnType<typeof useAuth>> = [];
    render(
      <AuthProvider initialSession={null}>
        <StatusProbe capture={(value) => captured.push(value)} />
      </AuthProvider>,
    );
    expect(captured[0].status).toBe("loading");
    expect(captured[0].session).toBeNull();
    await waitFor(() => {
      const last = captured[captured.length - 1];
      expect(last.status).toBe("unauthenticated");
    });
  });

  test("TC-003 AuthProvider refetches in the background when hydrated from server data", async () => {
    let resolveFetch: (value: unknown) => void = () => {};
    global.fetch = jest.fn(
      () =>
        new Promise((resolve) => {
          resolveFetch = resolve;
        }),
    ) as unknown as jest.Mock;

    const captured: Array<ReturnType<typeof useAuth>> = [];
    render(
      <AuthProvider initialSession={SAMPLE_SESSION}>
        <StatusProbe capture={(value) => captured.push(value)} />
      </AuthProvider>,
    );
    expect(global.fetch).toHaveBeenCalledWith(
      "/auth/session",
      expect.objectContaining({ credentials: "include" }),
    );

    resolveFetch({
      ok: true,
      status: 200,
      json: async () => ({
        user: { email: "clinician@example.com" },
        isPlatformAdmin: false,
        organizations: [],
        idleTimeoutMinutes: 30,
        selected_role: "triage_clinician",
        allowed_roles: ["triage_clinician"],
        needs_role_choice: false,
        density_preference: "comfortable",
      }),
    });

    await waitFor(() => {
      const last = captured[captured.length - 1];
      expect(last.status).toBe("authenticated");
    });
  });

  test("TC-004 layout.tsx declares force-dynamic so the Next.js Full Route Cache cannot serve a stale spinner", () => {
    const layoutPath = path.resolve(__dirname, "../app/layout.tsx");
    const source = fs.readFileSync(layoutPath, "utf-8");
    expect(source).toMatch(/export\s+const\s+dynamic\s*=\s*"force-dynamic"/);
    expect(source).toMatch(/export\s+const\s+revalidate\s*=\s*0/);
    expect(source).toMatch(/fetchInitialSession\s*\(/);
  });

  test("TC-005 auth route handlers set Cache-Control: no-store so Cloudflare never caches OAuth redirects", () => {
    const loginPath = path.resolve(__dirname, "../app/auth/login/route.ts");
    const callbackPath = path.resolve(
      __dirname,
      "../app/auth/callback/route.ts",
    );
    const loginSrc = fs.readFileSync(loginPath, "utf-8");
    const callbackSrc = fs.readFileSync(callbackPath, "utf-8");
    expect(loginSrc).toMatch(/Cache-Control["'\s,]+["']no-store/i);
    expect(callbackSrc).toMatch(/Cache-Control["'\s,]+["']no-store/i);
  });

  test("TC-006 e2e mode supplies the same mock session to proxy and SSR bootstrap", () => {
    const proxyPath = path.resolve(__dirname, "../proxy.ts");
    const serverSessionPath = path.resolve(__dirname, "../lib/serverSession.ts");
    const e2eSessionPath = path.resolve(__dirname, "../lib/e2eSession.ts");
    const proxySrc = fs.readFileSync(proxyPath, "utf-8");
    const serverSessionSrc = fs.readFileSync(serverSessionPath, "utf-8");
    const e2eSessionSrc = fs.readFileSync(e2eSessionPath, "utf-8");

    expect(proxySrc).toMatch(/pathname\s*===\s*"\/auth\/session"/);
    expect(proxySrc).toMatch(/NextResponse\.json\(E2E_SESSION_PAYLOAD/);
    expect(serverSessionSrc).toMatch(/isE2eAuthMode\(\)/);
    expect(serverSessionSrc).toMatch(/_coerceSession\(E2E_SESSION_PAYLOAD\)/);
    expect(e2eSessionSrc).toMatch(/NODE_ENV\s*!==\s*"production"/);
    expect(e2eSessionSrc).toMatch(/NEXT_PUBLIC_E2E_MODE\s*===\s*"true"/);
  });
});
