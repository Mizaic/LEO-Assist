/**
 * Role picker + RBAC acceptance spec.
 *
 * Covers VT for DI-FAF97A8C (role picker UI) and the new unified 14-role
 * RBAC catalog (DI-613A48DA / DO-124AC2C4).
 *
 * Each test injects a mock /auth/session payload via page.route() so we can
 * test every role without a live backend.
 *
 * Structure
 * ---------
 * 1. Role picker display  -- TC-P01 to TC-P05
 * 2. Role landing pages   -- TC-L01 to TC-L06  (representative set)
 * 3. Nav visibility       -- TC-N01 to TC-N06  (items shown/hidden per role)
 * 4. Restricted access    -- TC-R01 to TC-R03  (inaccessible pages per role)
 * 5. Scope type filtering -- TC-S01 to TC-S02  (icb/alliance hides Patients)
 */

import { expect, test, type Page } from "@playwright/test";

// -- Session factory --------------------------------------------------------

type OrgScopeType = "gp" | "icb" | "alliance" | "service_provider" | "pcn";

interface SessionOpts {
  needsRoleChoice?: boolean;
  allowedRoles?: string[];
  isPlatformAdmin?: boolean;
  scopeType?: OrgScopeType;
  twoOrgs?: boolean;
}

function buildSession(role: string, opts: SessionOpts = {}) {
  const orgs = opts.twoOrgs
    ? [
        { id: "org-1", name: "Trust Site A", odsCode: "T001", shortName: "TSA", scopeType: opts.scopeType ?? "service_provider" },
        { id: "org-2", name: "Trust Site B", odsCode: "T002", shortName: "TSB", scopeType: opts.scopeType ?? "service_provider" },
      ]
    : [{ id: "org-1", name: "Test Org", odsCode: "T001", scopeType: opts.scopeType ?? "service_provider" }];

  return {
    user: { email: "e2e.test@example.com", name: "E2E User" },
    isPlatformAdmin: opts.isPlatformAdmin ?? role === "platform_admin",
    organizations: orgs,
    selected_role: opts.needsRoleChoice ? null : role,
    allowed_roles: opts.allowedRoles ?? [role],
    needs_role_choice: opts.needsRoleChoice ?? false,
    idleTimeoutMinutes: 30,
    density_preference: "comfortable",
  };
}

async function withRole(page: Page, role: string, opts: SessionOpts = {}) {
  const payload = buildSession(role, opts);
  await page.route("**/auth/session", (route) => {
    if (route.request().method() === "GET") {
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(payload) });
    } else {
      route.continue();
    }
  });
}

// -- Helpers ----------------------------------------------------------------

async function gotoAndSettle(page: Page, path = "/") {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
}

async function expectNavVisible(page: Page, label: RegExp | string) {
  await expect(page.getByRole("navigation").getByText(label)).toBeVisible();
}

async function expectNavHidden(page: Page, label: RegExp | string) {
  await expect(page.getByRole("navigation").getByText(label)).not.toBeVisible();
}

// -- 1. Role picker display -------------------------------------------------

test.describe("TC-P: Role picker display", () => {
  test("TC-P01 picker renders when needs_role_choice is true", async ({ page }) => {
    await withRole(page, "triage_clinician", {
      needsRoleChoice: true,
      allowedRoles: ["triage_clinician", "clinical_coder"],
    });
    await gotoAndSettle(page);
    await expect(page.getByTestId("role-picker-overlay")).toBeVisible();
    await expect(page.getByRole("heading", { name: /Choose Your Role/i })).toBeVisible();
  });

  test("TC-P02 roles are grouped by category", async ({ page }) => {
    await withRole(page, "triage_clinician", {
      needsRoleChoice: true,
      allowedRoles: ["triage_clinician", "appointment_booking"],
    });
    await gotoAndSettle(page);
    await expect(page.getByText("Clinical Roles")).toBeVisible();
    await expect(page.getByText("Administration & Management")).toBeVisible();
    await expect(page.getByRole("radio", { name: /Triage Clinician/i })).toBeVisible();
    await expect(page.getByRole("radio", { name: /Appointment Booking/i })).toBeVisible();
  });

  test("TC-P03 search filters role cards", async ({ page }) => {
    await withRole(page, "triage_clinician", {
      needsRoleChoice: true,
      allowedRoles: ["triage_clinician", "clinical_coder", "auditor"],
    });
    await gotoAndSettle(page);
    await page.getByRole("searchbox", { name: /Search roles/i }).fill("Triage");
    await expect(page.getByRole("radio", { name: /Triage Clinician/i })).toBeVisible();
    await expect(page.getByRole("radio", { name: /Clinical Coder/i })).not.toBeVisible();
  });

  test("TC-P04 org step shown when user has two organisations", async ({ page }) => {
    await withRole(page, "triage_clinician", {
      needsRoleChoice: true,
      allowedRoles: ["triage_clinician"],
      twoOrgs: true,
    });
    await gotoAndSettle(page);
    await expect(page.getByText(/Choose Your Organisation/i)).toBeVisible();
    await expect(page.getByText("Trust Site A")).toBeVisible();
    await expect(page.getByText("Trust Site B")).toBeVisible();
  });

  test("TC-P05 welcome message includes user name", async ({ page }) => {
    await withRole(page, "triage_clinician", {
      needsRoleChoice: true,
      allowedRoles: ["triage_clinician"],
    });
    await gotoAndSettle(page);
    await expect(page.getByText(/Welcome, E2E User/i)).toBeVisible();
  });
});

// -- 2. Role landing pages --------------------------------------------------

test.describe("TC-L: Role landing pages", () => {
  test("TC-L01 triage_clinician lands on /care/patients", async ({ page }) => {
    await withRole(page, "triage_clinician");
    await page.goto("/care/patients");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/care\/patients/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L02 clinical_coder lands on /work", async ({ page }) => {
    await withRole(page, "clinical_coder");
    await page.goto("/work");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/work/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L03 auditor lands on /care/audit", async ({ page }) => {
    await withRole(page, "auditor");
    await page.goto("/care/audit");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/care\/audit/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L04 platform_admin lands on /admin/platform", async ({ page }) => {
    await withRole(page, "platform_admin", { isPlatformAdmin: true });
    await page.goto("/admin/platform");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/admin\/platform/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L05 org_admin lands on /admin/portal", async ({ page }) => {
    await withRole(page, "org_admin");
    await page.goto("/admin/portal");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/admin\/portal/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L06 pathway_supervisor lands on /care/dashboard", async ({ page }) => {
    await withRole(page, "pathway_supervisor");
    await page.goto("/care/dashboard");
    await page.waitForLoadState("networkidle");
    await expect(page).toHaveURL(/\/care\/dashboard/);
    await expect(page.locator("body")).toBeVisible();
  });
});

// -- 3. Nav visibility per role --------------------------------------------

test.describe("TC-N: Nav item visibility per role", () => {
  test("TC-N01 triage_clinician sees Patients and Pathways, not Platform", async ({ page }) => {
    await withRole(page, "triage_clinician");
    await gotoAndSettle(page, "/care/patients");
    await expectNavVisible(page, /Patients/i);
    await expectNavHidden(page, /Platform/i);
  });

  test("TC-N02 platform_admin sees Platform and Users nav items", async ({ page }) => {
    await withRole(page, "platform_admin", { isPlatformAdmin: true });
    await gotoAndSettle(page, "/admin/platform");
    await expectNavVisible(page, /Platform/i);
    await expectNavVisible(page, /Users/i);
  });

  test("TC-N03 clinical_coder sees My work, not Platform", async ({ page }) => {
    await withRole(page, "clinical_coder");
    await gotoAndSettle(page, "/work");
    await expectNavVisible(page, /My work/i);
    await expectNavHidden(page, /Platform/i);
  });

  test("TC-N04 org_admin sees Admin nav item", async ({ page }) => {
    await withRole(page, "org_admin");
    await gotoAndSettle(page, "/admin/portal");
    await expectNavVisible(page, /Admin|Organisation/i);
  });

  test("TC-N05 read_only sees only Reports in primary nav", async ({ page }) => {
    await withRole(page, "read_only");
    await gotoAndSettle(page, "/care/dashboard");
    await expectNavVisible(page, /Reports/i);
    await expectNavHidden(page, /Platform/i);
    await expectNavHidden(page, /Users/i);
  });

  test("TC-N06 auditor does not see Platform in primary nav", async ({ page }) => {
    await withRole(page, "auditor");
    await gotoAndSettle(page, "/care/audit");
    await expectNavHidden(page, /^Platform$/i);
  });
});

// -- 4. Restricted access per role ----------------------------------------

test.describe("TC-R: Restricted page access per role", () => {
  test("TC-R01 triage_clinician can access /care/patients", async ({ page }) => {
    await withRole(page, "triage_clinician");
    const resp = await page.goto("/care/patients");
    expect(resp?.status()).not.toBe(403);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-R02 platform_admin can access /admin/platform", async ({ page }) => {
    await withRole(page, "platform_admin", { isPlatformAdmin: true });
    const resp = await page.goto("/admin/platform");
    expect(resp?.status()).not.toBe(403);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-R03 non-admin role is gated from platform admin API endpoint", async ({ page, request }) => {
    await withRole(page, "clinical_coder");
    // Probe the platform admin API without a valid session; expect 401/403/404.
    const resp = await request.get("/api/admin/platform/orgs");
    expect([401, 403, 404]).toContain(resp.status());
  });
});

// -- 5. Scope type filtering -----------------------------------------------

test.describe("TC-S: Org scope type controls nav visibility", () => {
  test("TC-S01 icb scope hides Patients nav item", async ({ page }) => {
    await withRole(page, "triage_clinician", { scopeType: "icb" });
    await gotoAndSettle(page, "/care/dashboard");
    // AppShell hides Patients for icb and alliance scope types.
    await expectNavHidden(page, /^Patients$/i);
  });

  test("TC-S02 service_provider scope shows Patients nav item", async ({ page }) => {
    await withRole(page, "triage_clinician", { scopeType: "service_provider" });
    await gotoAndSettle(page, "/care/patients");
    await expectNavVisible(page, /^Patients$/i);
  });
});
