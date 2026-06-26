/**
 * VT-8DE34E84 -- Surface form approval workflow (Knowledge admin UI).
 *
 * Verifies DI-47D2CD86 AC1/AC2/AC5 through the Surface Forms tab:
 *   - pending alias shows an approve control
 *   - approve transitions the alias to approved (deactivate control appears)
 *   - deactivate transitions the alias to deactivated
 *   - change log dialog lists audit entries
 *
 * Backend calls are stubbed via page.route so the spec stays deterministic
 * without a live terminology-api or Neo4j stack.
 */

import { test, expect, type Page, type Route } from "@playwright/test";

const CONCEPT_ID = "44054006";
const NORMALIZED = "e2e-t2dm";
const FORM = "T2DM";

type AliasStatus = "pending" | "approved" | "deactivated";

function buildGroupedPayload(status: AliasStatus) {
  return {
    items: [
      {
        concept_id: CONCEPT_ID,
        concept_fsn: "Diabetes mellitus type 2 (disorder)",
        semantic_tag: "disorder",
        read_code: null,
        icd10: null,
        surface_forms: [
          {
            normalized: NORMALIZED,
            form: FORM,
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

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function stubAuth(page: Page) {
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

async function gotoSurfaceFormsTab(page: Page) {
  await page.goto("/admin/knowledge?tab=surface-forms");
  await expect(page.getByRole("heading", { name: "Knowledge" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page).toHaveURL(/tab=surface-forms/);
  await expect(page.getByText("Diabetes mellitus type 2 (disorder)")).toBeVisible({
    timeout: 15_000,
  });
}

test.describe("Surface form approval workflow (VT-8DE34E84)", () => {
  test.describe.configure({ mode: "serial" });

  test("pending alias can be approved then deactivated", async ({ page }) => {
    let aliasStatus: AliasStatus = "pending";
    let approveCalls = 0;
    let deactivateCalls = 0;

    await stubAuth(page);

    await page.route("**/api/terminology/surface-forms/grouped**", (route) =>
      fulfillJson(route, buildGroupedPayload(aliasStatus)),
    );

    await page.route(`**/api/terminology/surface-forms/${NORMALIZED}/approve`, (route) => {
      approveCalls += 1;
      aliasStatus = "approved";
      return fulfillJson(route, {
        normalized: NORMALIZED,
        form: FORM,
        status: "approved",
        reviewer: "knowledge-admin",
        reviewed_at: "2026-05-21T10:00:00Z",
        effective_at: "2026-05-21T10:00:00Z",
        concept_id: CONCEPT_ID,
        concept_fsn: "Diabetes mellitus type 2 (disorder)",
        confidence: 1.0,
      });
    });

    await page.route(`**/api/terminology/surface-forms/${NORMALIZED}/deactivate`, (route) => {
      deactivateCalls += 1;
      aliasStatus = "deactivated";
      return fulfillJson(route, {
        normalized: NORMALIZED,
        form: FORM,
        status: "deactivated",
        concept_id: CONCEPT_ID,
        concept_fsn: "Diabetes mellitus type 2 (disorder)",
        confidence: 1.0,
      });
    });

    await gotoSurfaceFormsTab(page);

    await expect(page.getByText(`${FORM} (pending)`)).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Approve alias ${FORM}` }),
    ).toBeVisible();

    await page.getByRole("button", { name: `Approve alias ${FORM}` }).click();

    await expect.poll(() => approveCalls).toBe(1);
    await expect(page.getByText(`${FORM} (pending)`)).toHaveCount(0);
    await expect(page.getByText(FORM, { exact: true })).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Deactivate alias ${FORM}` }),
    ).toBeVisible();

    await page.getByRole("button", { name: `Deactivate alias ${FORM}` }).click();

    await expect.poll(() => deactivateCalls).toBe(1);
    await expect(page.getByText(`${FORM} (deactivated)`)).toBeVisible();
    await expect(
      page.getByRole("button", { name: `Approve alias ${FORM}` }),
    ).toHaveCount(0);
  });

  test("change log dialog lists audit entries", async ({ page }) => {
    await stubAuth(page);

    await page.route("**/api/terminology/surface-forms/grouped**", (route) =>
      fulfillJson(route, buildGroupedPayload("approved")),
    );

    await page.route("**/api/terminology/surface-forms/audit-log**", (route) =>
      fulfillJson(route, {
        items: [
          {
            id: "log-approve-1",
            normalized: NORMALIZED,
            action: "approve",
            actor: "knowledge-admin",
            outcome: "success",
            detail: "Mapping approved for runtime resolve",
            concept_id: CONCEPT_ID,
            created_at: "2026-05-21T10:00:00Z",
          },
          {
            id: "log-upsert-1",
            normalized: NORMALIZED,
            action: "upsert",
            actor: "knowledge-admin",
            outcome: "success",
            detail: "Mapping saved as pending review",
            concept_id: CONCEPT_ID,
            created_at: "2026-05-21T09:59:00Z",
          },
        ],
        total: 2,
        offset: 0,
        limit: 100,
      }),
    );

    await gotoSurfaceFormsTab(page);

    await page.getByTestId("toolbar-action-audit-log").click();

    await expect(page.getByRole("dialog", { name: "Surface form change log" })).toBeVisible();
    await expect(page.getByText(`approve · ${NORMALIZED}`)).toBeVisible();
    await expect(page.getByText(`upsert · ${NORMALIZED}`)).toBeVisible();
    await expect(page.getByText("Mapping approved for runtime resolve")).toBeVisible();
  });
});
