import { expect, type Page, type Route } from "@playwright/test";

export const SURFACE_FORM_CONCEPT_ID = "44054006";
export const SURFACE_FORM_NORMALIZED = "e2e-t2dm";
export const SURFACE_FORM_LABEL = "T2DM";

export type SurfaceFormAliasStatus = "pending" | "approved" | "deactivated";

export function buildGroupedSurfaceFormsPayload(status: SurfaceFormAliasStatus) {
  return {
    items: [
      {
        concept_id: SURFACE_FORM_CONCEPT_ID,
        concept_fsn: "Diabetes mellitus type 2 (disorder)",
        semantic_tag: "disorder",
        read_code: null,
        icd10: null,
        surface_forms: [
          {
            normalized: SURFACE_FORM_NORMALIZED,
            form: SURFACE_FORM_LABEL,
            source: "manual",
            status,
            reviewer: status === "approved" ? "knowledge-admin" : undefined,
            reviewed_at: status === "approved" ? "2026-05-21T10:00:00Z" : undefined,
            effective_at: status === "approved" ? "2026-05-21T10:00:00Z" : undefined,
            confidence: 1.0,
          },
        ],
      },
    ],
    total: 1,
    offset: 0,
    limit: 50,
  };
}

export async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

export async function stubKnowledgeAdminAuth(page: Page) {
  await page.route("**/auth/session", (route) =>
    fulfillJson(route, {
      user: {
        email: "e2e@example.com",
        name: "E2E Knowledge Admin",
      },
      isPlatformAdmin: true,
      organizations: [],
      idleTimeoutMinutes: 30,
      selected_role: "platform_admin",
      allowed_roles: ["platform_admin", "developer"],
      needs_role_choice: false,
    }),
  );
}

export async function gotoSurfaceFormsTab(page: Page) {
  await page.goto("/admin/knowledge?tab=surface-forms");
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page).toHaveURL(/tab=surface-forms/);
  await expect(page.getByText("Diabetes mellitus type 2 (disorder)")).toBeVisible({
    timeout: 15_000,
  });
}

export async function stubSurfaceFormRoutes(page: Page) {
  let aliasStatus: SurfaceFormAliasStatus = "pending";
  let approveCalls = 0;
  let deactivateCalls = 0;

  await stubKnowledgeAdminAuth(page);

  await page.route("**/api/terminology/surface-forms/grouped**", (route) =>
    fulfillJson(route, buildGroupedSurfaceFormsPayload(aliasStatus)),
  );

  await page.route(
    `**/api/terminology/surface-forms/${SURFACE_FORM_NORMALIZED}/approve`,
    (route) => {
      approveCalls += 1;
      aliasStatus = "approved";
      return fulfillJson(route, {
        normalized: SURFACE_FORM_NORMALIZED,
        form: SURFACE_FORM_LABEL,
        status: "approved",
        reviewer: "knowledge-admin",
        reviewed_at: "2026-05-21T10:00:00Z",
        effective_at: "2026-05-21T10:00:00Z",
        concept_id: SURFACE_FORM_CONCEPT_ID,
        concept_fsn: "Diabetes mellitus type 2 (disorder)",
        confidence: 1.0,
      });
    },
  );

  await page.route(
    `**/api/terminology/surface-forms/${SURFACE_FORM_NORMALIZED}/deactivate`,
    (route) => {
      deactivateCalls += 1;
      aliasStatus = "deactivated";
      return fulfillJson(route, {
        normalized: SURFACE_FORM_NORMALIZED,
        form: SURFACE_FORM_LABEL,
        status: "deactivated",
        concept_id: SURFACE_FORM_CONCEPT_ID,
        concept_fsn: "Diabetes mellitus type 2 (disorder)",
        confidence: 1.0,
      });
    },
  );

  return {
    getApproveCalls: () => approveCalls,
    getDeactivateCalls: () => deactivateCalls,
  };
}

export async function runSurfaceFormApprovalFlow(page: Page) {
  await expect(page.getByText(`${SURFACE_FORM_LABEL} (pending)`)).toBeVisible();
  await page.getByRole("button", { name: `Approve alias ${SURFACE_FORM_LABEL}` }).click();
  await expect(page.getByText(`${SURFACE_FORM_LABEL} (pending)`)).toHaveCount(0);
  await expect(page.getByText(SURFACE_FORM_LABEL, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: `Deactivate alias ${SURFACE_FORM_LABEL}` }).click();
  await expect(page.getByText(`${SURFACE_FORM_LABEL} (deactivated)`)).toBeVisible();
}

export async function stubSurfaceFormAuditLog(page: Page) {
  await page.route("**/api/terminology/surface-forms/audit-log**", (route) =>
    fulfillJson(route, {
      items: [
        {
          id: "log-approve-1",
          normalized: SURFACE_FORM_NORMALIZED,
          action: "approve",
          actor: "knowledge-admin",
          outcome: "success",
          detail: "Mapping approved for runtime resolve",
          concept_id: SURFACE_FORM_CONCEPT_ID,
          created_at: "2026-05-21T10:00:00Z",
        },
        {
          id: "log-upsert-1",
          normalized: SURFACE_FORM_NORMALIZED,
          action: "upsert",
          actor: "knowledge-admin",
          outcome: "success",
          detail: "Mapping saved as pending review",
          concept_id: SURFACE_FORM_CONCEPT_ID,
          created_at: "2026-05-21T09:59:00Z",
        },
      ],
      total: 2,
      offset: 0,
      limit: 100,
    }),
  );
}
