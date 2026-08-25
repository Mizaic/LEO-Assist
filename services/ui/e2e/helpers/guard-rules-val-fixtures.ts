/**
 * Playwright stubs for VAL-0CE7EB38 (fine-tune extraction rules).
 */

import type { Page } from "@playwright/test";

export const CUSTOM_GLOBAL_ID = "rule-global-1";
export const NEW_PATTERN = "if symptoms worsen";
export const CHANGED_BY = "Ada Admin";
export const SCOPE_PLATFORM = "Applies to every organisation";
export const SCOPE_ORG = "Applies to Oak GP only";
export const SCOPE_PATHWAY = "Applies to suspected-cancer pathway";
export const IMPACT_NOTE =
  "This change applies on the next note check. No restart needed.";

const NEW_RULE_ID = "rule-new-1";

export const createdBodies: Record<string, unknown>[] = [];

function json(route: { fulfill: (r: object) => Promise<void> }, body: unknown, status = 200) {
  return route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function rule(partial: Record<string, unknown>) {
  return {
    family: "scope_guard",
    rule_type: "safety_netting",
    active: true,
    source: "custom",
    readonly: false,
    ...partial,
  };
}

function seedRules() {
  return [
    rule({
      rule_id: CUSTOM_GLOBAL_ID,
      pattern: "come back if it gets worse",
      summary: SCOPE_PLATFORM,
      org_id: null,
    }),
    rule({
      rule_id: "rule-oak-1",
      pattern: "oak gp local cue",
      summary: SCOPE_ORG,
      org_id: "org-oak",
    }),
    rule({
      rule_id: "rule-pathway-1",
      pattern: "pathway local cue",
      summary: SCOPE_PATHWAY,
      plan_definition_id: "pd-cancer-1",
    }),
    rule({
      rule_id: "builtin-scope-1",
      pattern: "call 999 if chest pain",
      source: "builtin",
      readonly: true,
    }),
  ];
}

function history() {
  return [
    {
      version: 2,
      changed_at: "2026-08-22T12:00:00Z",
      changed_by: CHANGED_BY,
      pattern: "come back if it gets worse",
      rule_type: "safety_netting",
      active: true,
      revert_available: true,
    },
    {
      version: 1,
      changed_at: "2026-08-01T09:00:00Z",
      changed_by: CHANGED_BY,
      pattern: "return if worse",
      rule_type: "safety_netting",
      active: true,
      revert_available: true,
    },
  ];
}

export async function stubGuardRulesValRoutes(page: Page): Promise<void> {
  createdBodies.length = 0;
  const rules = seedRules();

  await page.route("**/api/admin/workbench/guard-rules**", async (route) => {
    const method = route.request().method();
    if (method === "POST") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      createdBodies.push(body);
      rules.unshift(
        rule({
          rule_id: NEW_RULE_ID,
          pattern: String(body.pattern || NEW_PATTERN),
          summary: String(body.pattern || NEW_PATTERN),
          active: body.active !== false,
        }),
      );
      return json(route, { rule_id: NEW_RULE_ID, created: true }, 201);
    }
    if (method === "PUT") {
      return json(route, { updated: true });
    }
    return json(route, rules);
  });
  await page.route("**/api/admin/workbench/guard-rules/**/history", (route) =>
    json(route, history()),
  );
  await page.route("**/api/admin/workbench/rule-impact-preview**", (route) =>
    json(route, { match_count: 2, encounter_sample: [], message: IMPACT_NOTE }),
  );
}
