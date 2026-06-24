/**
 * VT-8DE34E84 -- Surface form approval workflow (Knowledge admin UI).
 *
 * Verifies DI-47D2CD86 AC1/AC2/AC5 through the Surface Forms tab.
 * Atlas VAL evidence is recorded separately in val-surface-forms-d681ea88.spec.ts.
 */

import { expect, test } from "@playwright/test";
import {
  buildGroupedSurfaceFormsPayload,
  fulfillJson,
  gotoSurfaceFormsTab,
  runSurfaceFormApprovalFlow,
  stubKnowledgeAdminAuth,
  stubSurfaceFormAuditLog,
  stubSurfaceFormRoutes,
  SURFACE_FORM_LABEL,
  SURFACE_FORM_NORMALIZED,
} from "./helpers/surface-forms-fixtures";

test.describe("Surface form approval workflow (VT-8DE34E84)", () => {
  test.describe.configure({ mode: "serial" });

  test("pending alias can be approved then deactivated", async ({ page }) => {
    const counters = await stubSurfaceFormRoutes(page);
    await gotoSurfaceFormsTab(page);
    await runSurfaceFormApprovalFlow(page);
    await expect.poll(counters.getApproveCalls).toBe(1);
    await expect.poll(counters.getDeactivateCalls).toBe(1);
    await expect(
      page.getByRole("button", { name: `Approve alias ${SURFACE_FORM_LABEL}` }),
    ).toHaveCount(0);
  });

  test("change log dialog lists audit entries", async ({ page }) => {
    await stubKnowledgeAdminAuth(page);
    await page.route("**/api/terminology/surface-forms/grouped**", (route) =>
      fulfillJson(route, buildGroupedSurfaceFormsPayload("approved")),
    );
    await stubSurfaceFormAuditLog(page);
    await gotoSurfaceFormsTab(page);
    await page.getByTestId("toolbar-action-audit-log").click();
    await expect(page.getByRole("dialog", { name: "Surface form change log" })).toBeVisible();
    await expect(page.getByText(`approve · ${SURFACE_FORM_NORMALIZED}`)).toBeVisible();
    await expect(page.getByText(`upsert · ${SURFACE_FORM_NORMALIZED}`)).toBeVisible();
    await expect(page.getByText("Mapping approved for runtime resolve")).toBeVisible();
  });
});
