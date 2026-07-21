/**
 * Access gate: authenticated users without LEO roles must not paint the shell.
 *
 * Static-source + unit checks for the no-access flash fix.
 */

import * as fs from "fs";
import * as path from "path";

import { sessionHasLeoAccess } from "@/lib/sessionAccess";
import type { Session } from "@/lib/authContext";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

function baseSession(overrides: Partial<Session> = {}): Session {
  return {
    user: { email: "user@example.com", name: "Test User" },
    isPlatformAdmin: false,
    organizations: [],
    idleTimeoutMinutes: 30,
    selectedRole: null,
    allowedRoles: [],
    needsRoleChoice: false,
    densityPreference: null,
    ...overrides,
  };
}

describe("session access gate", () => {
  test("TC-001: non-admin with no roles has no access", () => {
    expect(sessionHasLeoAccess(baseSession())).toBe(false);
  });

  test("TC-002: non-admin with a LEO role has access", () => {
    expect(
      sessionHasLeoAccess(baseSession({ allowedRoles: ["triage_clinician"] })),
    ).toBe(true);
  });

  test("TC-003: platform admin has access even with empty roles", () => {
    expect(
      sessionHasLeoAccess(baseSession({ isPlatformAdmin: true })),
    ).toBe(true);
  });

  test("TC-004: AppShell blocks protected paint when session has no access", () => {
    const src = readFile("services/ui/src/components/AppShell.tsx");
    expect(src).toMatch(/sessionHasLeoAccess/);
    expect(src).toMatch(/variant=["']no-access["']/);
    expect(src).toMatch(/UnauthorizedScreen/);
  });

  test("TC-005: OAuth callback rejects no-role users before save_session", () => {
    const src = readFile("services/api/app/routers/auth.py");
    expect(src).toMatch(/may_issue_session/);
    expect(src).toMatch(/error=no_access/);
    const gateIdx = src.indexOf("may_issue_session(is_admin, resolved_roles)");
    const saveIdx = src.indexOf("save_session(");
    expect(gateIdx).toBeGreaterThan(-1);
    expect(saveIdx).toBeGreaterThan(gateIdx);
  });

  test("TC-006: sign-in page explains no_access", () => {
    const src = readFile("services/ui/src/app/sign-in/page.tsx");
    expect(src).toMatch(/no_access:/);
    expect(src).toMatch(/assign a LEO role/);
  });
});
