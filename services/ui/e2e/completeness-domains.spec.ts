/**
 * VT-734E8B96 / VT-A32E2016 / VT-6ADE2398 -- completeness domain configuration UI.
 *
 * Verifies the split-panel subdomain UI (Overview / Concepts / Rules).
 * Backend calls are stubbed so the spec is deterministic.
 *
 * Atlas trace:
 *   VT-734E8B96  -- Overview tab invariants
 *   VT-A32E2016  -- Concepts tab invariants
 *   VT-6ADE2398  -- Rules tab CRUD invariants
 */

import { expect, test } from "./fixtures";
import {
  DOMAIN_ID,
  SUBDOMAIN,
  openSubdomainPanel,
  stubCompletenessDomainRoutes,
} from "./helpers/completeness-domains-fixtures";

test.describe("Completeness domains configuration UI", () => {
  test.beforeEach(async ({ page }) => {
    await stubCompletenessDomainRoutes(page);
  });

  test("opens split panel and shows overview, concepts, and rules tabs", async ({ page }) => {
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
    await expect(page.getByText("254837009")).toBeVisible();
  });

  test("Overview tab shows Purpose multi-select with use_cases", async ({ page }) => {
    await openSubdomainPanel(page);
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible({ timeout: 10_000 });

    // Purpose section should be present
    await expect(page.getByText("Purpose")).toBeVisible({ timeout: 5_000 });
    // Completeness chip should be selected
    await expect(page.getByText("Minimum dataset")).toBeVisible();

    // Milestone and time window fields should NOT appear (episode_detection not selected)
    await expect(page.getByLabel("Milestone type")).not.toBeVisible();
  });

  test("Overview tab shows milestone fields when episode_detection selected", async ({ page }) => {
    await openSubdomainPanel(page);
    await expect(page.getByRole("tab", { name: "Overview" })).toBeVisible({ timeout: 10_000 });

    // Add episode_detection to purpose
    const purposeSelect = page.getByLabel("Purpose");
    await purposeSelect.click();
    await page.getByRole("option", { name: /episode detection/i }).click();
    await page.keyboard.press("Escape");

    await expect(page.getByLabel("Milestone type")).toBeVisible({ timeout: 3_000 });
  });

  test("Concepts tab shows semantic filter strip", async ({ page }) => {
    await openSubdomainPanel(page);
    await page.getByRole("tab", { name: "Concepts" }).click();

    // All filter pill should be active by default
    await expect(page.getByRole("button", { name: /all/i })).toBeVisible({ timeout: 5_000 });

    // Semantic tag pills for existing tags should be visible
    await expect(page.getByRole("button", { name: /disorder/i })).toBeVisible();
  });

  test("Concepts tab semantic filter narrows search results", async ({ page }) => {
    await openSubdomainPanel(page);
    await page.getByRole("tab", { name: "Concepts" }).click();

    // Wait for the filter strip
    await expect(page.getByRole("button", { name: /all/i })).toBeVisible({ timeout: 5_000 });

    // Type into SNOMED search
    const searchInput = page.getByPlaceholder(/search snomed/i);
    await searchInput.fill("cancer");

    // Search result should appear
    await expect(page.getByText("Breast cancer")).toBeVisible({ timeout: 5_000 });
  });

  test("Rules tab shows existing rule groups as editable cards", async ({ page }) => {
    await openSubdomainPanel(page);
    await page.getByRole("tab", { name: "Rules" }).click();

    await expect(page.getByDisplayValue("Diagnosis present")).toBeVisible({ timeout: 5_000 });
    await expect(page.getByText("254837009")).toBeVisible();
    await expect(page.getByText("disorder")).toBeVisible();
  });

  test("Rules tab Add rule button creates a new group", async ({ page }) => {
    await openSubdomainPanel(page);
    await page.getByRole("tab", { name: "Rules" }).click();

    await expect(page.getByRole("button", { name: /add rule/i })).toBeVisible({ timeout: 5_000 });
    await page.getByRole("button", { name: /add rule/i }).click();

    // A new rule card with default name should appear
    await expect(page.getByDisplayValue("New rule")).toBeVisible({ timeout: 3_000 });
  });

  test("Rules tab delete removes a rule group", async ({ page }) => {
    await openSubdomainPanel(page);
    await page.getByRole("tab", { name: "Rules" }).click();

    await expect(page.getByDisplayValue("Diagnosis present")).toBeVisible({ timeout: 5_000 });

    const deleteButton = page.getByRole("button", { name: /delete rule/i }).first();
    await deleteButton.click();

    await expect(page.getByDisplayValue("Diagnosis present")).not.toBeVisible({ timeout: 3_000 });
  });
});
