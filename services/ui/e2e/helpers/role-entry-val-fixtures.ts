/**
 * Playwright stubs for VAL-8AE95F1A (staff enter with assigned role).
 */

import type { Page } from "@playwright/test";

export const FIRST_ROLE = "triage_clinician";
export const BANNER_COPY = "You are trying this role. Changes you make are real.";
export const EXIT_LABEL = "Exit to platform admin";

export type RoleEntryMode =
  | "clinician"
  | "auto_role"
  | "admin_impersonate";

export const patchedRoles: string[] = [];

let mode: RoleEntryMode = "clinician";
let selectedRole: string | null = FIRST_ROLE;

export function setRoleEntryMode(next: RoleEntryMode): void {
  mode = next;
  if (next === "clinician") {
    selectedRole = FIRST_ROLE;
    return;
  }
  if (next === "auto_role") {
    selectedRole = null;
    return;
  }
  selectedRole = FIRST_ROLE;
}

function json(
  route: { fulfill: (r: object) => Promise<void> },
  body: unknown,
) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function isAdmin(): boolean {
  return mode === "admin_impersonate";
}

function allowedRoles(): string[] {
  if (isAdmin()) {
    return ["platform_admin", FIRST_ROLE, "clinical_coder"];
  }
  return [FIRST_ROLE, "clinical_coder"];
}

function sessionPayload() {
  return {
    user: { email: "e2e.staff@example.com", name: "E2E Staff" },
    isPlatformAdmin: isAdmin(),
    organizations: [
      {
        id: "org-e2e",
        name: "E2E Org",
        odsCode: "E2E",
        shortName: "E2E",
        scopeType: "gp",
      },
    ],
    idleTimeoutMinutes: 30,
    selected_role: selectedRole,
    allowed_roles: allowedRoles(),
    needs_role_choice: false,
    density_preference: "comfortable",
  };
}

export async function stubRoleEntryValRoutes(page: Page): Promise<void> {
  patchedRoles.length = 0;
  mode = "clinician";
  selectedRole = FIRST_ROLE;

  await page.route("**/auth/session", (route) => {
    const url = route.request().url();
    if (url.includes("/session/role")) {
      return route.fallback();
    }
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    return json(route, sessionPayload());
  });

  await page.route("**/session/role", (route) => {
    if (route.request().method() !== "PATCH") {
      return route.continue();
    }
    const body = route.request().postDataJSON() as { role?: string };
    const role = typeof body.role === "string" ? body.role : FIRST_ROLE;
    patchedRoles.push(role);
    selectedRole = role;
    return json(route, sessionPayload());
  });
}
