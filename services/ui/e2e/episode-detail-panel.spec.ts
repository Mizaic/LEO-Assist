/**
 * Atlas trace:
 *   DI: DI-CC0BD732 (per-episode SBAR with coherence)
 *   DI: DI-885930F8 (canonical episode-level code)
 *   DI: DI-E8FE404D (cross-encounter coding QA)
 *   UN: UN-782EE657 (clinician sees one SBAR per episode)
 *
 * Smoke-level e2e for the EpisodeDetailPanel surface inside Mission
 * Control. The panel is rendered when a single EpisodeOfCare is
 * selected from the patient detail drawer. Because the cohort and
 * episode IDs vary by environment, this spec is defensive: it
 * verifies the panel + its key affordances render whenever an
 * episode is selectable, and it never fails the suite when the
 * environment has no episodes to show.
 */
import { test, expect } from "@playwright/test";

test.describe("EpisodeDetailPanel (Mission Control)", () => {
  test("mission control page loads", async ({ page }) => {
    await page.goto("/mission-control");
    await expect(
      page.getByRole("heading", { name: /Mission Control/i }),
    ).toBeVisible({ timeout: 15000 });
  });

  test("when an episode is selectable, panel + chips + SBAR scope chip render", async ({
    page,
  }) => {
    await page.goto("/mission-control");
    await expect(
      page.getByRole("heading", { name: /Mission Control/i }),
    ).toBeVisible({ timeout: 15000 });

    const patientRow = page.locator("[data-testid^='patient-row-']").first();
    if (!(await patientRow.isVisible().catch(() => false))) {
      test.skip(true, "No patients in this environment to exercise the panel.");
      return;
    }
    await patientRow.click();

    const episodeChip = page
      .locator("[data-testid^='episode-chip-']")
      .first();
    if (!(await episodeChip.isVisible().catch(() => false))) {
      test.skip(true, "Drawer has no episode chips to select.");
      return;
    }
    await episodeChip.click();

    const panel = page.getByTestId("episode-detail-panel");
    await expect(panel).toBeVisible({ timeout: 10000 });

    await expect(panel.getByTestId("episode-detail-site-chip")).toBeVisible();
    await expect(panel.getByTestId("episode-detail-status-chip")).toBeVisible();
    await expect(
      panel.getByTestId("episode-detail-encounter-count"),
    ).toBeVisible();

    await expect(
      panel
        .getByTestId("canonical-code-card")
        .or(panel.getByTestId("canonical-code-empty")),
    ).toBeVisible();

    await expect(panel.getByTestId("episode-sbar-scope-chip")).toBeVisible();
  });
});
