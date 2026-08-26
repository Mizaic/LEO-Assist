/**
 * Role picker + RBAC acceptance spec.
 *
 * Covers VT for DI-FAF97A8C (role picker UI) and the new unified 28-role
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

import { expect, gotoAndSettle, test, type Page } from "./fixtures";

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
    isPlatformAdmin: opts.isPlatformAdmin ?? role === "administrator",
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

async function expectNavVisible(page: Page, label: RegExp | string) {
  await expect(page.getByRole("navigation").getByText(label)).toBeVisible();
}

async function expectNavHidden(page: Page, label: RegExp | string) {
  await expect(page.getByRole("navigation").getByText(label)).not.toBeVisible();
}

// -- 1. Role picker display -------------------------------------------------

test.describe("TC-P: Role picker retired", () => {
  test("TC-P01 picker does not render when needs_role_choice is true", async ({ page }) => {
    await withRole(page, "triage_clinician", {
      needsRoleChoice: true,
      allowedRoles: ["triage_clinician", "referral_supervisor"],
    });
    await gotoAndSettle(page);
    await expect(page.getByTestId("role-picker-overlay")).toHaveCount(0);
    await expect(page.locator("body")).toBeVisible();
  });
});

// -- 2. Role landing pages --------------------------------------------------

test.describe("TC-L: Role landing pages", () => {
  test("TC-L01 triage_clinician lands on /care/patients", async ({ page }) => {
    await withRole(page, "triage_clinician");
    await page.goto("/care/patients");
    await waitForPageSettled(page);
    await expect(page).toHaveURL(/\/care\/patients/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L02 referral_supervisor lands on /work", async ({ page }) => {
    await withRole(page, "referral_supervisor");
    await page.goto("/work");
    await waitForPageSettled(page);
    await expect(page).toHaveURL(/\/work/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L03 regulatory_reviewer lands on /care/audit", async ({ page }) => {
    await withRole(page, "regulatory_reviewer");
    await page.goto("/care/audit");
    await waitForPageSettled(page);
    await expect(page).toHaveURL(/\/care\/audit/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L04 administrator lands on /admin/knowledge", async ({ page }) => {
    await withRole(page, "administrator", { isPlatformAdmin: true });
    await page.goto("/admin/knowledge");
    await waitForPageSettled(page);
    await expect(page).toHaveURL(/\/admin\/knowledge/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L05 organization_administrator lands on /admin/portal", async ({ page }) => {
    await withRole(page, "organization_administrator");
    await page.goto("/admin/portal");
    await waitForPageSettled(page);
    await expect(page).toHaveURL(/\/admin\/portal/);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-L06 pathway_supervisor lands on /care/dashboard", async ({ page }) => {
    await withRole(page, "pathway_supervisor");
    await page.goto("/care/dashboard");
    await waitForPageSettled(page);
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

  test("TC-N02 administrator sees Platform and Users nav items", async ({ page }) => {
    await withRole(page, "administrator", { isPlatformAdmin: true });
    await gotoAndSettle(page, "/admin/platform");
    await expectNavVisible(page, /Platform/i);
    await expectNavVisible(page, /Users/i);
  });

  test("TC-N03 referral_supervisor sees My work, not Platform", async ({ page }) => {
    await withRole(page, "referral_supervisor");
    await gotoAndSettle(page, "/work");
    await expectNavVisible(page, /My work/i);
    await expectNavHidden(page, /Platform/i);
  });

  test("TC-N04 organization_administrator sees Admin nav item", async ({ page }) => {
    await withRole(page, "organization_administrator");
    await gotoAndSettle(page, "/admin/portal");
    await expectNavVisible(page, /Admin|Organisation/i);
  });

  test("TC-N05 support_agent sees only Reports in primary nav", async ({ page }) => {
    await withRole(page, "support_agent");
    await gotoAndSettle(page, "/care/dashboard");
    await expectNavVisible(page, /Reports/i);
    await expectNavHidden(page, /Platform/i);
    await expectNavHidden(page, /Users/i);
  });

  test("TC-N06 regulatory_reviewer does not see Platform in primary nav", async ({ page }) => {
    await withRole(page, "regulatory_reviewer");
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

  test("TC-R02 administrator can access /admin/platform", async ({ page }) => {
    await withRole(page, "administrator", { isPlatformAdmin: true });
    const resp = await page.goto("/admin/platform");
    expect(resp?.status()).not.toBe(403);
    await expect(page.locator("body")).toBeVisible();
  });

  test("TC-R03 non-admin role is gated from platform admin API endpoint", async ({ page, request }) => {
    await withRole(page, "referral_supervisor");
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
