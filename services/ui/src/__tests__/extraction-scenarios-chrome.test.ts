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
 *   DI: DI-1B3B5375, DI-B492CAFD (AC1 and AC4 via this VT)
 *   DO: DO-416BA91D
 *   Risk: R-80E8BD96
 *   VT-24D7A846  extraction scenarios admin UI chrome (5 ACs)
 *   VT-C0D7D50C  run lifecycle + Neo4j persistence (DI-B492CAFD AC2-AC3)
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
const EDITOR_DIALOG = "services/ui/src/app/admin/extraction-scenarios/ScenarioEditorDialog.tsx";
const PIPELINE_PLACEHOLDERS =
  "services/ui/src/app/admin/extraction-scenarios/ScenarioPipelinePlaceholders.tsx";
const RUN_DRAWER = "services/ui/src/app/admin/extraction-scenarios/RunResultsDrawer.tsx";
const NEXT_CONFIG = "services/ui/next.config.mjs";
const PROXY = "services/ui/src/proxy.ts";
const API_FILE = "services/ui/src/app/admin/extraction-scenarios/api.ts";
const FAST_API_ROUTER = "services/api/app/routers/extraction_scenarios.py";
const MUTATIONS_ROUTER = "services/api/app/routers/extraction_scenario_mutations.py";
const CYPHER = "libs/cypher/extraction_scenario_queries.py";

describe("VT-24D7A846 - Extraction Scenarios folded into Validation Lab", () => {
  test("TC-001: KnowledgeTabKey union includes validation-lab", () => {
    const copy = src(KNOWLEDGE_COPY);
    expect(copy).toMatch(/["']validation-lab["']/);
    expect(copy).not.toMatch(/["']extraction-scenarios["']/);
  });

  test("TC-002: KNOWLEDGE_TAB_COPY has a validation-lab entry", () => {
    const copy = src(KNOWLEDGE_COPY);
    expect(copy).toMatch(/"validation-lab"\s*:/);
    expect(copy).toMatch(/Validation Lab/);
  });

  test("TC-003: knowledge/page.tsx TAB_WIDTH includes validation-lab as wide", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/"validation-lab":\s*"wide"/);
  });

  test("TC-004: knowledge/page.tsx TABS list includes validation-lab", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/key:\s*["']validation-lab["']/);
    expect(page).toMatch(/label:\s*["']Validation Lab["']/);
  });

  test("TC-005: knowledge/page.tsx TAB_PANELS includes Validation Lab", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/"validation-lab":\s*ValidationLabPage/);
  });

  test("TC-006: knowledge/page.tsx declares ValidationLabPage with dynamic()", () => {
    const page = src(KNOWLEDGE_PAGE);
    expect(page).toMatch(/ValidationLabPage\s*=\s*dynamic/);
    expect(page).toMatch(/admin\/validation-lab\/page/);
  });

  test("TC-007: API file has the correct base route", () => {
    const api = src(API_FILE);
    expect(api).toMatch(/\/api\/extraction-scenarios/);
    expect(api).toMatch(/listScenarios/);
    expect(api).toMatch(/getScenario/);
    expect(api).toMatch(/approveScenario/);
    expect(api).toMatch(/createScenario/);
    expect(api).toMatch(/updateScenario/);
    expect(api).toMatch(/deleteScenario/);
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
    expect(panel).toMatch(/New scenario/);
    expect(panel).toMatch(/new-scenario/);
    expect(panel).toMatch(/data-testid="extraction-scenario-panel"/);
  });

  test("TC-009b: panel exposes edit and delete row actions", () => {
    const panel = src(PANEL);
    expect(panel).toMatch(/edit-btn-/);
    expect(panel).toMatch(/delete-btn-/);
    expect(panel).toMatch(/ScenarioEditorDialog/);
    expect(panel).toMatch(/ConfirmDialog/);
  });

  test("TC-010: review surface is a dialog with rendered Markdown and expected values", () => {
    const drawer = src(CASE_DRAWER);
    expect(drawer).toMatch(/data-testid="approve-button"/);
    expect(drawer).toMatch(/data-testid="markdown-viewer"/);
    expect(drawer).toMatch(/data-view-mode="rendered"/);
    expect(drawer).toMatch(/data-view-mode="raw"/);
    expect(drawer).toMatch(/data-testid="markdown-view-toggle"/);
    expect(drawer).toMatch(/Clinical document/);
    expect(drawer).toMatch(/markdown_body payload sent to the extraction pipeline/);
    expect(drawer).toMatch(/MarkdownEditor/);
    expect(drawer).toMatch(/data-testid="expected-phrases-panel"/);
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
    expect(config).toMatch(/destination.*\/admin\/validation-lab/);
  });

  test("TC-014: FastAPI router exposes all required endpoints", () => {
    const router = src(FAST_API_ROUTER);
    const mutations = src(MUTATIONS_ROUTER);
    expect(router).toMatch(/prefix.*extraction-scenarios/);
    expect(router).toMatch(/@router\.get\(""\)/);
    expect(router).toMatch(/@router\.get\("\/{case_id}"\)/);
    expect(router).toMatch(/@router\.patch\("\/{case_id}"\)/);
    expect(router).toMatch(/@router\.post\("\/runs"\)/);
    expect(router).toMatch(/@router\.get\("\/runs\/{run_id}"\)/);
    expect(mutations).toMatch(/@router\.post\(""\)/);
    expect(mutations).toMatch(/@router\.put\("\/{case_id}"\)/);
    expect(mutations).toMatch(/@router\.delete\("\/{case_id}"\)/);
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
    const editor = src(EDITOR_DIALOG);
    expect(cypher).toMatch(/s\.expected_observables\s+AS expected_observables/);
    expect(cypher).toMatch(/s\.expected_analysis\s+AS expected_analysis/);
    expect(cypher).toMatch(/s\.expected_sbar\s+AS expected_sbar/);
    expect(cypher).toMatch(/CREATE_EXTRACTION_SCENARIO/);
    expect(cypher).toMatch(/UPDATE_EXTRACTION_SCENARIO/);
    expect(cypher).toMatch(/DELETE_EXTRACTION_SCENARIO/);
    expect(router).toMatch(/"expected_observables"/);
    expect(editor).toMatch(/data-testid="scenario-editor-dialog"/);
    expect(editor).toMatch(/data-testid="scenario-save-button"/);
    expect(editor).toMatch(/maxWidth="xl"/);
    expect(editor).toMatch(/expected-phrase-value-/);
    expect(editor).toMatch(/expected-phrase-unit-/);
    expect(editor).toMatch(/expected-phrase-concept-id-/);
    expect(editor).toMatch(/ScenarioPipelinePlaceholders/);
    const placeholders = src(PIPELINE_PLACEHOLDERS);
    expect(placeholders).toMatch(/expected-analysis-panel/);
    expect(placeholders).toMatch(/expected-sbar-panel/);
    expect(placeholders).toMatch(/expected-sbar-situation/);
  });
});
