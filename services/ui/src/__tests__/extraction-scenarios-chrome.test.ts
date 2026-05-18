/**
 * VT-24D7A846 -- Extraction Scenarios admin surface chrome.
 *
 * Static-source verification that the Extraction Scenarios tab is correctly
 * registered in the Knowledge hub and the UI surface has the required
 * structural invariants:
 *   - KnowledgeTabKey and TAB_COPY entries exist
 *   - TABS, TAB_WIDTH, TAB_PANELS wired correctly in knowledge/page.tsx
 *   - API route strings are correct
 *   - Status chip data-testid pattern is present
 *   - Atlas manual record callout references VT-29880CC8 and VAL-87173594
 *   - /admin/extraction-scenarios redirect exists in next.config.mjs
 *
 * Atlas:
 *   DI: DI-1B3B5375, DI-B492CAFD
 *   DO: DO-416BA91D
 *   Risk: R-80E8BD96
 *   VT-24D7A846  extraction scenarios admin UI chrome
 *   VT-29880CC8   extraction scenario verification
 *   VAL-87173594  phrase-level F1 validation
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function src(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const KNOWLEDGE_PAGE = "services/ui/src/app/admin/knowledge/page.tsx";
const KNOWLEDGE_COPY = "services/ui/src/lib/knowledgeCopy.ts";
const PANEL = "services/ui/src/app/admin/extraction-scenarios/ExtractionScenarioPanel.tsx";
const CASE_DRAWER = "services/ui/src/app/admin/extraction-scenarios/CaseReviewDrawer.tsx";
const RUN_DRAWER = "services/ui/src/app/admin/extraction-scenarios/RunResultsDrawer.tsx";
const NEXT_CONFIG = "services/ui/next.config.mjs";
const PROXY = "services/ui/src/proxy.ts";
const API_FILE = "services/ui/src/app/admin/extraction-scenarios/api.ts";
const FAST_API_ROUTER = "services/api/app/routers/extraction_scenarios.py";
const CYPHER = "libs/cypher/extraction_scenario_queries.py";

describe("VT-24D7A846 - Extraction Scenarios admin surface chrome", () => {
  test("TC-001: KnowledgeTabKey union includes extraction-scenarios", () => {
    const copy = src(KNOWLEDGE_COPY);
    expect(copy).toMatch(/["']extraction-scenarios["']/);
  });

  test("TC-002: KNOWLEDGE_TAB_COPY has an extraction-scenarios entry", () => {
    const copy = src(KNOWLEDGE_COPY);
    expect(copy).toMatch(/"extraction-scenarios"\s*:/);
    expect(copy).toMatch(/VAL-87173594/);
  });

  test("TC-003: knowledge/page.tsx TAB_WIDTH includes extraction-scenarios as wide", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/"extraction-scenarios":\s*"wide"/);
  });

  test("TC-004: knowledge/page.tsx TABS list includes extraction-scenarios", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/key:\s*["']extraction-scenarios["']/);
    expect(page).toMatch(/label:\s*["']Extraction Scenarios["']/);
  });

  test("TC-005: knowledge/page.tsx TAB_PANELS includes extraction-scenarios component", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/"extraction-scenarios":\s*ExtractionScenariosPage/);
  });

  test("TC-006: knowledge/page.tsx declares ExtractionScenariosPage with dynamic()", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/ExtractionScenariosPage\s*=\s*dynamic/);
    expect(page).toMatch(/admin\/extraction-scenarios\/page/);
  });

  test("TC-007: API file has the correct base route", () => {
    const api = src(API_FILE);
    expect(api).toMatch(/\/api\/extraction-scenarios/);
    expect(api).toMatch(/listScenarios/);
    expect(api).toMatch(/getScenario/);
    expect(api).toMatch(/approveScenario/);
    expect(api).toMatch(/triggerRun/);
    expect(api).toMatch(/getRunStatus/);
  });

  test("TC-008: ExtractionScenarioPanel has data-testid for status chips", () => {
    const panel = src(PANEL);
    expect(panel).toMatch(/data-testid=\{`status-chip-\$\{row\.case_id\}`\}/);
  });

  test("TC-009: ExtractionScenarioPanel has Run validation toolbar action", () => {
    const panel = src(PANEL);
    expect(panel).toMatch(/Run validation/);
    expect(panel).toMatch(/run-validation/);
    expect(panel).toMatch(/data-testid="extraction-scenario-panel"/);
  });

  test("TC-010: review surface is a dialog with raw Markdown payload and values", () => {
    const drawer = src(CASE_DRAWER);
    expect(drawer).toMatch(/data-testid="approve-button"/);
    expect(drawer).toMatch(/data-testid="markdown-viewer"/);
    expect(drawer).toMatch(/data-view-mode="raw"/);
    expect(drawer).toMatch(/Raw Markdown sent to pipeline/);
    expect(drawer).toMatch(/exact document payload from markdown_body/);
    expect(drawer).toMatch(/data-testid="case-review-dialog"/);
    expect(drawer).toMatch(/<Dialog/);
    expect(drawer).not.toMatch(/<Drawer/);
    expect(drawer).toMatch(/expected-value-/);
    expect(drawer).toMatch(/expected_observables/);
    expect(drawer).not.toMatch(/<TableCell[^>]*>Flag<\/TableCell>/);
    expect(drawer).toMatch(/must-not-extract-toggle/);
  });

  test("TC-011: RunResultsDrawer references both Atlas artefact IDs", () => {
    const drawer = src(RUN_DRAWER);
    expect(drawer).toMatch(/VT-29880CC8/);
    expect(drawer).toMatch(/VAL-87173594/);
    expect(drawer).toMatch(/data-testid="atlas-callout"/);
    expect(drawer).toMatch(/data-testid="pass-fail-badge"/);
    expect(drawer).toMatch(/data-testid="run-results-drawer"/);
  });

  test("TC-012: RunResultsDrawer polls every 1500 ms", () => {
    const drawer = src(RUN_DRAWER);
    expect(drawer).toMatch(/POLL_INTERVAL_MS\s*=\s*1500/);
    expect(drawer).toMatch(/setInterval/);
  });

  test("TC-013: /admin/extraction-scenarios redirect exists in next.config.mjs", () => {
    const config = src(NEXT_CONFIG);
    expect(config).toMatch(/source.*\/admin\/extraction-scenarios/);
    expect(config).toMatch(/destination.*\/admin\/knowledge\?tab=extraction-scenarios/);
  });

  test("TC-014: FastAPI router exposes all required endpoints", () => {
    const router = src(FAST_API_ROUTER);
    expect(router).toMatch(/prefix.*extraction-scenarios/);
    expect(router).toMatch(/@router\.get\(""\)/);
    expect(router).toMatch(/@router\.get\("\/{case_id}"\)/);
    expect(router).toMatch(/@router\.patch\("\/{case_id}"\)/);
    expect(router).toMatch(/@router\.post\("\/runs"\)/);
    expect(router).toMatch(/@router\.get\("\/runs\/{run_id}"\)/);
  });

  test("TC-015: FastAPI router uses threading.Thread for background runs", () => {
    const router = src(FAST_API_ROUTER);
    expect(router).toMatch(/threading\.Thread/);
    expect(router).toMatch(/_runs_lock/);
    expect(router).toMatch(/_PASS_THRESHOLD\s*=\s*0\.95/);
  });

  test("TC-016: Next proxy forwards extraction scenario API calls to Core API", () => {
    const proxy = src(PROXY);
    expect(proxy).toMatch(/prefix:\s*["']\/api\/extraction-scenarios\/["']/);
    expect(proxy).toMatch(/prefix:\s*["']\/api\/extraction-scenarios["']/);
    expect(proxy).toMatch(/coreApi\(\)}\/extraction-scenarios/);
    expect(proxy).toMatch(/["']\/api\/extraction-scenarios["']/);
    expect(proxy).toMatch(/["']\/api\/extraction-scenarios\/:path\*["']/);
  });

  test("TC-017: API detail includes expected observables for phrase values", () => {
    const cypher = src(CYPHER);
    const router = src(FAST_API_ROUTER);
    expect(cypher).toMatch(/s\.expected_observables\s+AS expected_observables/);
    expect(router).toMatch(/"expected_observables"/);
  });
});
