/**
 * VT-734E8B96 / VT-A32E2016 -- completeness domain configuration UI.
 *
 * Verifies the split-panel subdomain UI (Overview / Concepts / Rules).
 * Backend calls are stubbed so the spec is deterministic.
 */

import { expect, test } from "@playwright/test";
import {
  DOMAIN_ID,
  SUBDOMAIN,
  stubCompletenessDomainRoutes,
} from "./helpers/completeness-domains-fixtures";

test.describe("Completeness domains configuration UI", () => {
  test("opens split panel and shows overview, concepts, and rules tabs", async ({ page }) => {
    await stubCompletenessDomainRoutes(page);
    await page.goto(`/settings/domains/${DOMAIN_ID}`);
    await expect(page.getByText("Breast referral completeness")).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole("button", { name: `Configure ${SUBDOMAIN}` }).click();
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByLabel("Description")).toHaveValue("Breast referral completeness");

    await page.getByRole("tab", { name: "Concepts" }).click();
    await expect(page.getByText("Breast cancer")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Malignant neoplastic disease")).toBeVisible();

    await page.getByRole("tab", { name: "Rules" }).click();
    await expect(page.getByText("Diagnosis present")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("Required")).toBeVisible();
    await expect(page.getByText("254837009, 363346000")).toBeVisible();
  });
});
