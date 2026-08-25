/**
 * Playwright stubs for VAL-9F92DC97 (durable long-running clinical jobs).
 */

import type { Page } from "@playwright/test";

export const GOLD_PLAN_ID = "pd-gold-training-audit";
export const GOLD_PLAN_NAME = "Gold training audit";
export const VAL_PLAN_ID = "pd-val-sbar-summary";
export const VAL_PLAN_NAME = "Validation SBAR summary";
export const EPISODE_PLAN_ID = "pd-episode-bundle-coding";
export const EPISODE_PLAN_NAME = "Episode bundle coding";
export const DURABLE_MODE_COPY =
  "Edges publish the next event after a persisted stage completes.";

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown) {
  return route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function durablePlan(
  id: string,
  name: string,
  description: string,
  event: string,
) {
  return {
    id,
    name,
    status: "active",
    description,
    version: "1",
    source: "seed",
    meta: { seeded: true },
    trigger: { event },
    actionCount: 2,
    actions: [],
    edges: [],
    _workflowMode: "durable_pubsub",
    _durableSteps: [
      {
        step_id: "step-1",
        event_type: event,
        loads: ["PipelineStageRun"],
        persists: ["PipelineStageRun"],
        emits_on_success: "next",
        emits_on_failure: null,
        idempotency_key: "run_id:step_id",
      },
    ],
  };
}

function goldPlan() {
  return durablePlan(
    GOLD_PLAN_ID,
    GOLD_PLAN_NAME,
    "Gold training jobs run on the durable publish/subscribe runner.",
    "gold-training-run",
  );
}

function validationPlan() {
  return durablePlan(
    VAL_PLAN_ID,
    VAL_PLAN_NAME,
    "Validation jobs run on the durable publish/subscribe runner.",
    "val-sbar-summary",
  );
}

function episodePlan() {
  return durablePlan(
    EPISODE_PLAN_ID,
    EPISODE_PLAN_NAME,
    "Episode bundle jobs run on the durable publish/subscribe runner.",
    "episode_bundle",
  );
}

function bundle() {
  return {
    resourceType: "Bundle",
    type: "searchset",
    entry: [
      { resource: goldPlan() },
      { resource: validationPlan() },
      { resource: episodePlan() },
    ],
  };
}

export async function stubDurableJobsValRoutes(page: Page): Promise<void> {
  await page.route("**/api/proxy/fhir/PlanDefinition**", (route) => {
    const url = route.request().url();
    if (url.includes("/" + GOLD_PLAN_ID)) return json(route, goldPlan());
    if (url.includes("/" + VAL_PLAN_ID)) return json(route, validationPlan());
    if (url.includes("/" + EPISODE_PLAN_ID)) return json(route, episodePlan());
    return json(route, bundle());
  });
}
