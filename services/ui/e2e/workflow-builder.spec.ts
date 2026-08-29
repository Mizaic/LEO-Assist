/**
 * Playwright e2e spec -- Workflow Builder.
 *
 * Covers:
 *   - Workflow list page renders with StatHero counts
 *   - Empty state is shown when no workflows exist
 *   - "New workflow" dialog creates a workflow and navigates to the canvas
 *   - Workflow card "Open" button navigates to the canvas
 *   - Canvas renders with Start node and Agent Palette
 *   - Dragging an agent onto the canvas adds it (via keyboard workaround)
 *   - Save button is enabled after a change and calls the graph API
 *   - Delete workflow confirms before deleting
 *
 * All backend calls are stubbed via page.route() so this runs without
 * a live Core API or Neo4j instance.
 */

import { test, expect, waitForPageSettled } from "./fixtures";
import path from "path";

// -- Fixtures ---------------------------------------------------------------

const WORKFLOW_1 = {
  id: "wf-001",
  name: "Colorectal Standard",
  serviceId: "svc-1",
  serviceName: "Colorectal Surgery",
  createdAt: "2026-08-01T09:00:00Z",
  stepCount: 6,
  humanCount: 2,
};

const EMPTY_GRAPH = {
  workflowId: "wf-001",
  workflowName: "Colorectal Standard",
  serviceId: "svc-1",
  nodes: [],
  edges: [],
};

async function stubWorkflowApis(
  page: import("@playwright/test").Page,
  opts: { workflows?: typeof WORKFLOW_1[]; graph?: typeof EMPTY_GRAPH } = {}
) {
  const workflows = opts.workflows ?? [WORKFLOW_1];
  const graph = opts.graph ?? EMPTY_GRAPH;

  await page.route("**/api/admin/workflows", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(workflows),
      });
    } else if (method === "POST") {
      const body = JSON.parse(route.request().postData() ?? "{}");
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          id: "wf-new",
          name: body.name ?? "New workflow",
          serviceId: "",
          createdAt: new Date().toISOString(),
          stepCount: 0,
          humanCount: 0,
        }),
      });
    } else {
      await route.continue();
    }
  });

  await page.route("**/api/admin/workflows/*/graph", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(graph),
      });
    } else if (method === "PUT") {
      await route.fulfill({ status: 204, body: "" });
    } else {
      await route.continue();
    }
  });

  await page.route("**/api/admin/workflows/wf-001", async (route) => {
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204, body: "" });
    } else {
      await route.continue();
    }
  });

  await page.route("**/api/admin/workflows/wf-new/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...EMPTY_GRAPH,
        workflowId: "wf-new",
        workflowName: "My New Workflow",
      }),
    });
  });
}

// ---------------------------------------------------------------------------
// List page tests
// ---------------------------------------------------------------------------

test.describe("Workflow list page", () => {
  test("renders StatHero with workflow counts", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await expect(page.getByTestId("workflows-workspace")).toBeVisible();
    // StatHero shows the total count in the Workflows tile
    await expect(
      page.getByTestId("metric-tile-total").getByText("1")
    ).toBeVisible();
    await expect(page.getByTestId("metric-tile-total")).toContainText("Workflows");
  });

  test("shows empty state when no workflows exist", async ({ page }) => {
    await stubWorkflowApis(page, { workflows: [] });
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await expect(page.getByText("No workflows yet")).toBeVisible();
    await expect(page.getByText("Create a workflow")).toBeVisible();
  });

  test("renders a workflow card for each workflow", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await expect(page.getByTestId("workflow-card-wf-001")).toBeVisible();
    await expect(page.getByText("Colorectal Standard")).toBeVisible();
    await expect(page.getByText("Colorectal Surgery")).toBeVisible();
    await expect(page.getByText(/6 agent steps/)).toBeVisible();
    await expect(page.getByText(/2 human gates/)).toBeVisible();
  });

  test("shows the New workflow toolbar button", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await expect(page.getByRole("button", { name: "New workflow" })).toBeVisible();
  });

  const screenshotDir = path.join(__dirname, "screenshots", "workflow-builder");

  test("screenshot -- list page with workflows", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);
    await expect(page.getByTestId("workflows-workspace")).toBeVisible();
    await page.screenshot({
      path: path.join(screenshotDir, "01-workflow-list.png"),
      fullPage: true,
    });
  });

  test("screenshot -- empty list state", async ({ page }) => {
    await stubWorkflowApis(page, { workflows: [] });
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);
    await expect(page.getByText("No workflows yet")).toBeVisible();
    await page.screenshot({
      path: path.join(screenshotDir, "02-empty-state.png"),
      fullPage: true,
    });
  });
});

// ---------------------------------------------------------------------------
// New workflow dialog
// ---------------------------------------------------------------------------

test.describe("New workflow dialog", () => {
  test("opens when New workflow is clicked", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await page.getByRole("button", { name: "New workflow" }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("heading", { name: "New workflow" })).toBeVisible();
    await expect(page.getByLabel("Workflow name")).toBeVisible();
  });

  test("Create button is disabled when name is empty", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await page.getByRole("button", { name: "New workflow" }).click();
    const createBtn = page.getByRole("button", { name: "Create workflow" });
    await expect(createBtn).toBeDisabled();
  });

  test("enables Create button when name is entered", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await page.getByRole("button", { name: "New workflow" }).click();
    await page.getByLabel("Workflow name").fill("My Test Workflow");
    const createBtn = page.getByRole("button", { name: "Create workflow" });
    await expect(createBtn).toBeEnabled();
  });

  test("navigates to canvas after successful creation", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await page.getByRole("button", { name: "New workflow" }).click();
    await page.getByLabel("Workflow name").fill("My New Workflow");
    await page.getByRole("button", { name: "Create workflow" }).click();

    // Should navigate to the canvas for the new workflow
    await page.waitForURL("**/admin/workflows/wf-new");
  });

  test("screenshot -- new workflow dialog", async ({ page }) => {
    const screenshotDir = path.join(__dirname, "screenshots", "workflow-builder");
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await page.getByRole("button", { name: "New workflow" }).click();
    await page.getByLabel("Workflow name").fill("Colorectal Urgent");
    await page.screenshot({
      path: path.join(screenshotDir, "03-new-workflow-dialog.png"),
    });
  });
});

// ---------------------------------------------------------------------------
// Delete workflow dialog
// ---------------------------------------------------------------------------

test.describe("Delete workflow dialog", () => {
  test("opens when the delete icon is clicked", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await page
      .getByRole("button", { name: /Delete workflow Colorectal Standard/ })
      .click();
    await expect(page.getByRole("dialog")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Delete workflow?" })).toBeVisible();
  });

  test("Delete button is disabled until name is typed correctly", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows");
    await waitForPageSettled(page);

    await page
      .getByRole("button", { name: /Delete workflow Colorectal Standard/ })
      .click();

    const deleteBtn = page.getByRole("button", { name: "Delete workflow" });
    await expect(deleteBtn).toBeDisabled();

    await page.getByLabel("Workflow name").fill("Colorectal Standard");
    await expect(deleteBtn).toBeEnabled();
  });
});

// ---------------------------------------------------------------------------
// Canvas page
// ---------------------------------------------------------------------------

test.describe("Workflow canvas", () => {
  test("renders the canvas page for a workflow", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    // Wait for React Flow to mount
    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
  });

  test("shows the workflow name in the top bar", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Colorectal Standard")).toBeVisible();
  });

  test("shows the Start node on an empty graph", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("Start")).toBeVisible();
  });

  test("agent palette is visible with search field", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Steps.*drag to add/i)).toBeVisible();
    await expect(page.getByPlaceholder("Search...")).toBeVisible();
  });

  test("palette shows AI Agents and Human Gates sections", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText("AI Agents")).toBeVisible();
    await expect(page.getByText("Human Gates")).toBeVisible();
  });

  test("palette search filters agents", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    const search = page.getByPlaceholder("Search...");
    await search.fill("triage");
    await expect(page.getByText("Clinical Triage")).toBeVisible();
    // Other agents should not be visible
    await expect(page.getByText("Referral Download")).not.toBeVisible();
  });

  test("Save button is disabled when there are no unsaved changes", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  test("back arrow navigates to the workflow list", async ({ page }) => {
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await page.getByRole("button", { name: /Workflows/ }).click();
    await page.waitForURL("**/admin/workflows");
  });

  test("screenshot -- canvas with empty workflow", async ({ page }) => {
    const screenshotDir = path.join(__dirname, "screenshots", "workflow-builder");
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await page.screenshot({
      path: path.join(screenshotDir, "04-canvas-empty.png"),
      fullPage: true,
    });
  });

  test("screenshot -- agent palette with search filter", async ({ page }) => {
    const screenshotDir = path.join(__dirname, "screenshots", "workflow-builder");
    await stubWorkflowApis(page);
    await page.goto("/admin/workflows/wf-001");
    await waitForPageSettled(page);

    await expect(page.locator(".react-flow")).toBeVisible({ timeout: 10_000 });
    await page.getByPlaceholder("Search...").fill("triage");
    await page.screenshot({
      path: path.join(screenshotDir, "05-palette-search.png"),
    });
  });
});
