import type { Page, Route } from "@playwright/test";

export const VAL_TEMPLATE_A_ID = "tpl-referral-assessment-001";
export const VAL_TEMPLATE_B_ID = "tpl-primary-care-001";
export const VAL_ORG_A_ID = "org-referral-assessment";
export const VAL_ORG_A_NAME = "Referral Assessment NHS Trust";
export const VAL_ORG_B_ID = "org-primary-care";
export const VAL_ORG_B_NAME = "Primary Care Partnership";

export type AuditAuthRole = "qm" | "clinician_a" | "clinician_b";

export type AuditFixtureState = {
  authRole: AuditAuthRole;
  orgATemplateId: string | null;
  orgBTemplateId: string | null;
  savedTemplates: Map<string, Record<string, unknown>>;
};

export function createAuditFixtureState(): AuditFixtureState {
  return {
    authRole: "qm",
    orgATemplateId: null,
    orgBTemplateId: null,
    savedTemplates: new Map(),
  };
}

export function setAuditAuthRole(state: AuditFixtureState, role: AuditAuthRole): void {
  state.authRole = role;
}

async function fulfillJson(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

function sessionPayload(role: AuditAuthRole) {
  const sessions = {
    qm: {
      user: { email: "qm@example.com", name: "Quality Manager" },
      isPlatformAdmin: true,
      organizations: [
        { id: VAL_ORG_A_ID, name: VAL_ORG_A_NAME },
        { id: VAL_ORG_B_ID, name: VAL_ORG_B_NAME },
      ],
      idleTimeoutMinutes: 30,
      selected_role: "administrator",
      allowed_roles: ["regulatory_reviewer", "administrator"],
      needs_role_choice: false,
      density_preference: "comfortable",
    },
    clinician_a: {
      user: { email: "clinician-a@example.com", name: "Clinician org-A" },
      isPlatformAdmin: false,
      organizations: [{ id: VAL_ORG_A_ID, name: VAL_ORG_A_NAME }],
      idleTimeoutMinutes: 30,
      selected_role: "clinician",
      allowed_roles: ["clinician"],
      needs_role_choice: false,
    },
    clinician_b: {
      user: { email: "clinician-b@example.com", name: "Clinician org-B" },
      isPlatformAdmin: false,
      organizations: [{ id: VAL_ORG_B_ID, name: VAL_ORG_B_NAME }],
      idleTimeoutMinutes: 30,
      selected_role: "clinician",
      allowed_roles: ["clinician"],
      needs_role_choice: false,
    },
  };
  return sessions[role];
}

function metricCatalogue() {
  const tiers: [string, string, string, string[]][] = [
    ["referral_stt_rate", "Referral STT Rate", "kpi_strip", ["kpi_strip"]],
    ["referral_guideline_compliance_rate", "Guideline Compliance Rate", "kpi_strip", ["kpi_strip"]],
    ["patient_gender_distribution", "Gender Distribution", "bar_chart", ["bar_chart", "pie_chart"]],
    ["patient_age_band_distribution", "Age Band Distribution", "bar_chart", ["bar_chart"]],
    ["early_stage_detection_rate", "Early Stage Detection Rate", "kpi_strip", ["kpi_strip"]],
    ["cancer_conversion_rate", "Cancer Conversion Rate", "kpi_strip", ["kpi_strip"]],
    ["unactioned_alerts_by_age", "Unactioned Alerts by Age", "table", ["table"]],
    ["alert_escalation_rate", "Alert Escalation Rate", "kpi_strip", ["kpi_strip"]],
    ["episode_open_age_distribution", "Episode Open-Age Distribution", "bar_chart", ["bar_chart"]],
    ["referral_completion_rate", "Referral Completion Rate", "kpi_strip", ["kpi_strip"]],
  ];
  // Give the STT Rate metric a real parameter schema so the builder's
  // "Parameters" tab is exercisable (VAL-E7BE67D0 step 3). All other metrics
  // keep an empty schema.
  const paramSchemas: Record<string, Record<string, unknown>> = {
    referral_stt_rate: {
      lookback_months: {
        type: "integer",
        default: 12,
        minimum: 1,
        maximum: 36,
        required: true,
      },
      include_screening: { type: "boolean", default: false },
    },
  };
  return tiers.map(([metric_id, title, output_type, compatible_tile_types]) => ({
    metric_id,
    title,
    description: `${title} metric`,
    output_type,
    compatible_tile_types,
    param_schema: paramSchemas[metric_id] ?? {},
    output_schema: [],
  }));
}

function sampleTiles() {
  return [
    {
      tile_id: "tile-preview-1",
      label: "STT Rate",
      tile_type: "kpi_strip",
      metric_id: "referral_stt_rate",
      param_overrides: {},
      layout: { x: 0, y: 0, w: 4, h: 3 },
    },
  ];
}

function buildTemplate(
  templateId: string,
  title: string,
  status: "draft" | "published" = "published",
) {
  const now = new Date().toISOString();
  return {
    template_id: templateId,
    title,
    status,
    version: 1,
    tiles: sampleTiles(),
    created_by: "qm@example.com",
    created_at: now,
    updated_at: now,
  };
}

function emptyAuditSectionResult() {
  return {
    scopes: {
      practice: null,
      alliance_live: null,
      england_live: null,
    },
    benchmark: null,
  };
}

function emptyAuditSummary() {
  return {
    total_episodes: 0,
    cohort_1a_n: 0,
    cohort_3_n: 0,
    confirmed_cancers_via_2ww_excluding_screening_pct: null,
  };
}

function ncdaAnalyticsBody(pathname: string, method: string): unknown {
  if (method !== "GET") {
    return { rows: [], columns: [] };
  }
  if (pathname.includes("/analytics/audit/summary")) {
    return emptyAuditSummary();
  }
  if (pathname.includes("/analytics/audit/symptoms")) {
    return { by_cancer_type: [], total_episodes: 0 };
  }
  if (pathname.includes("/analytics/audit/blood-signal")) {
    return { tests: [], distributions: [], values: [], matrix: [] };
  }
  if (pathname.includes("/analytics/audit/")) {
    return emptyAuditSectionResult();
  }
  return {};
}

function activeTemplateForRole(state: AuditFixtureState) {
  if (state.authRole === "clinician_a" && state.orgATemplateId) {
    return buildTemplate(state.orgATemplateId, "Referral Assessment Audit");
  }
  if (state.authRole === "clinician_b" && state.orgBTemplateId) {
    return buildTemplate(state.orgBTemplateId, "Primary Care Audit");
  }
  return null;
}

export async function clickFirstAvailableMetricAdd(page: Page): Promise<void> {
  const card = page
    .locator('[draggable="true"]')
    .filter({ hasText: "Referral STT Rate" })
    .first();
  await card.waitFor({ state: "visible", timeout: 20_000 });
  await card.locator(".MuiChip-root").first().click({ timeout: 15_000 });
}

export async function selectOrgInBrowser(
  page: Page,
  orgId: string,
  orgName?: string,
): Promise<void> {
  await page.evaluate((id) => {
    window.localStorage.setItem("leo_selected_org", id);
  }, orgId);

  const label = orgName ?? orgId;
  const expandedPicker = await visibleLocator(page.locator('[role="combobox"]'));
  if (expandedPicker) {
    await expandedPicker.click({ timeout: 5_000 });
    const option = page.getByRole("listbox").getByRole("option", { name: label });
    if (await option.isVisible({ timeout: 2_000 }).catch(() => false)) {
      await option.click();
    } else {
      await page.keyboard.press("ArrowDown");
      await page.keyboard.press("Enter");
    }
    await page.waitForFunction(
      (id) => window.localStorage.getItem("leo_selected_org") === id,
      orgId,
    );
    return;
  }

  const collapsedPicker = page.getByRole("button", { name: "Select organisation" });
  if (await collapsedPicker.isVisible().catch(() => false)) {
    await collapsedPicker.click({ timeout: 5_000 });
    await page.getByRole("menuitem", { name: label }).click({ timeout: 5_000 });
    await page.waitForFunction(
      (id) => window.localStorage.getItem("leo_selected_org") === id,
      orgId,
    );
  }
}

async function visibleLocator(locator: ReturnType<Page["locator"]>) {
  for (let i = 0; i < await locator.count(); i += 1) {
    const candidate = locator.nth(i);
    if (await candidate.isVisible().catch(() => false)) {
      return candidate;
    }
  }
  return null;
}

export async function primeOrgSelection(page: Page, orgId: string): Promise<void> {
  await page.evaluate((id) => {
    window.localStorage.setItem("leo_selected_org", id);
  }, orgId);
}

export async function hardNavigate(page: Page, path: string): Promise<void> {
  await page.evaluate((target) => {
    window.location.href = target;
  }, path);
  await page.waitForURL(`**${path}`);
}

export async function openCareAuditAsClinician(
  page: Page,
  state: AuditFixtureState,
  role: "clinician_a" | "clinician_b",
  orgId: string,
): Promise<void> {
  setAuditAuthRole(state, role);
  await primeOrgSelection(page, orgId);
  await hardNavigate(page, "/care/audit");
  await page.waitForLoadState("domcontentloaded");
}

export async function installAuditTemplateFixtures(
  page: Page,
  state: AuditFixtureState,
): Promise<void> {
  await page.route(
    (url) => url.pathname.includes("/api/proxy/analytics/audit-templates/active"),
    (route) => fulfillJson(route, activeTemplateForRole(state)),
  );

  await page.route(
    (url) =>
      url.pathname.includes("/api/proxy/analytics/") &&
      !url.pathname.includes("/audit-templates") &&
      !url.pathname.includes("/audit-metrics"),
    (route) => {
      const pathname = route.request().url();
      const parsed = new URL(pathname);
      if (route.request().method() === "GET") {
        return fulfillJson(route, ncdaAnalyticsBody(parsed.pathname, "GET"));
      }
      if (route.request().method() === "POST") {
        return fulfillJson(route, ncdaAnalyticsBody(parsed.pathname, "POST"));
      }
      return route.continue();
    },
  );

  await page.route("**/api/proxy/benchmarks/**", (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    return fulfillJson(route, []);
  });

  await page.route("**/auth/session", (route) =>
    fulfillJson(route, sessionPayload(state.authRole)),
  );

  await page.route("**/api/proxy/analytics/audit-metrics", (route) => {
    if (route.request().method() !== "GET") {
      return route.continue();
    }
    return fulfillJson(route, metricCatalogue());
  });

  await page.route("**/api/proxy/analytics/audit-metrics/*/run", (route) =>
    fulfillJson(route, {
      metric_id: "referral_stt_rate",
      columns: ["label", "value"],
      rows: [["STT rate", "92%"]],
    }),
  );

  await page.route("**/api/proxy/analytics/audit-templates", async (route) => {
    const method = route.request().method();
    if (method === "GET") {
      return fulfillJson(route, [...state.savedTemplates.values()]);
    }
    if (method === "POST") {
      const body = route.request().postDataJSON() as {
        title: string;
        tiles: unknown[];
      };
      const templateId = `tpl-saved-${Date.now()}`;
      const tpl = buildTemplate(templateId, body.title, "draft");
      tpl.tiles = body.tiles as typeof tpl.tiles;
      state.savedTemplates.set(templateId, tpl);
      return fulfillJson(route, tpl, 201);
    }
    return route.continue();
  });

  await page.route(
    (url) =>
      url.pathname.includes("/api/proxy/analytics/audit-templates/") &&
      !url.pathname.includes("/active"),
    async (route) => {
      const url = route.request().url();
      if (url.includes("/publish")) {
      return fulfillJson(route, {
        assignment_id: `assign-${Date.now()}`,
        template_id: "tpl-saved",
        version: 1,
        scope_type: "org",
        scope_id: VAL_ORG_A_ID,
        published_at: new Date().toISOString(),
        published_by: "qm@example.com",
      });
      }
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON() as {
          title?: string;
          tiles?: unknown[];
        };
        const tpl = buildTemplate(`tpl-saved-${Date.now()}`, body.title ?? "Draft", "draft");
        if (body.tiles) {
          tpl.tiles = body.tiles as typeof tpl.tiles;
        }
        return fulfillJson(route, tpl);
      }
      return route.continue();
    },
  );

  // Multi-phase SSE stub: tracks call count to route intent->discover->build phases
  let draftCallCount = 0;
  await page.route("**/api/audit-draft", async (route) => {
    if (route.request().method() !== "POST") {
      return route.continue();
    }
    draftCallCount += 1;
    let sseBody: string;

    if (draftCallCount === 1) {
      // intent phase -> questions-available
      sseBody = [
        `data: {"type":"text-delta","delta":"Let me understand your needs."}\n\n`,
        `data: ${JSON.stringify({
          type: "questions-available",
          input: {
            intent_summary: "Build a referral quality audit dashboard",
            questions: [
              {
                id: "audience",
                question: "Who is the primary audience?",
                options: [
                  { id: "gp", label: "GP partner", recommended: true },
                  { id: "board", label: "PCN board", recommended: false },
                ],
              },
              {
                id: "focus",
                question: "What is the main focus area?",
                options: [
                  { id: "referral", label: "Referral quality", recommended: true },
                  { id: "safety", label: "Safety netting", recommended: false },
                ],
              },
            ],
          },
        })}

`,
        `data: {"type":"finish"}\n\n`,
      ].join("");
    } else if (draftCallCount === 2) {
      // discover phase -> plan-available
      sseBody = [
        `data: ${JSON.stringify({
          type: "plan-available",
          input: {
            rationale: "Based on your answers, a referral quality dashboard suits a GP partner audience.",
            warnings: [],
            tiles: [
              {
                metric_id: "referral_stt_rate",
                label: "STT Rate",
                tile_type: "kpi_strip",
                section: "Referral quality",
                reason: "Core referral quality KPI.",
              },
              {
                metric_id: "referral_guideline_compliance_rate",
                label: "Guideline Compliance",
                tile_type: "kpi_strip",
                section: "Referral quality",
                reason: "NG12 compliance metric.",
              },
              {
                metric_id: "early_stage_detection_rate",
                label: "Early Stage Detection",
                tile_type: "kpi_strip",
                section: "Outcomes",
                reason: "Measures early diagnosis rate.",
              },
            ],
          },
        })}

`,
        `data: {"type":"finish"}\n\n`,
      ].join("");
    } else {
      // build phase -> tile-added + build-complete
      sseBody = [
        `data: ${JSON.stringify({ type: "tile-added", tile: { metric_id: "referral_stt_rate", label: "STT Rate", tile_type: "kpi_strip" } })}

`,
        `data: ${JSON.stringify({ type: "tile-added", tile: { metric_id: "referral_guideline_compliance_rate", label: "Guideline Compliance", tile_type: "kpi_strip" } })}

`,
        `data: ${JSON.stringify({ type: "tile-added", tile: { metric_id: "early_stage_detection_rate", label: "Early Stage Detection", tile_type: "kpi_strip" } })}

`,
        `data: ${JSON.stringify({ type: "build-complete", added: 3, skipped: [], warnings: [] })}

`,
        `data: {"type":"finish"}\n\n`,
      ].join("");
    }

    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache",
      },
      body: sseBody,
    });
  });
}