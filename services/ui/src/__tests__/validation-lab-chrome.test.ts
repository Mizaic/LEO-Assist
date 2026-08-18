/**
 * VT-22F3EF6A / VT-D30C96EF / VT-3959DFB3 -- Validation Lab chrome + retire redirects.
 *
 * Atlas: DI-A898556B / DI-12D40786 / DI-43E908C6 / DO-158BE606
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("VT-22F3EF6A - Validation Lab chrome", () => {
  test("TC-001: Validation Lab page mounts the three-path clinical home", () => {
    const page = readFile(
      "services/ui/src/app/admin/validation-lab/page.tsx",
    );
    const home =
      readFile("services/ui/src/app/admin/validation-lab/AccuracyLoopHome.tsx") +
      readFile("services/ui/src/app/admin/validation-lab/accuracyLoopDoors.ts");
    const cases = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const wizard = readFile(
      "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
    );
    const ruleDoor = readFile(
      "services/ui/src/app/admin/validation-lab/RuleDoor.tsx",
    );
    expect(page).toMatch(/validation-lab-page/);
    expect(page).toMatch(/AccuracyLoopHome/);
    expect(page).toMatch(/LabCasesPanel/);
    expect(page).not.toMatch(/TestPatientLibraryKnowledgeTab/);
    expect(home).toMatch(/Investigate a non-conformance/);
    expect(home).toMatch(/Run baseline tests/);
    expect(home).toMatch(/Build new tests/);
    expect(home).toMatch(/Test a guideline rule/);
    expect(ruleDoor).toMatch(/CreatePatientWizard/);
    expect(cases).toMatch(/LeoSbarHost/);
    expect(wizard).toMatch(/Submit referral/);
    expect(wizard).toMatch(/wizard-step-referral/);
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    expect(api).toMatch(/formatLabApiError/);
    expect(api).toMatch(/Could not reach the Validation Lab API/);
  });

  test("TC-002: LeoSbarHost mints widget token and mounts leo-sbar", () => {
    const src = readFile(
      "services/ui/src/components/sbar-final/LeoSbarHost.tsx",
    );
    expect(src).toMatch(/\/api\/sdk\/widget-token/);
    expect(src).toMatch(/import\("@mizaic\/leo-widget"\)/);
    expect(src).toMatch(/<leo-sbar/);
    expect(src).toMatch(/assessment-id=\{assessmentId\}/);
    expect(src).toMatch(/widget-token=\{token\}/);
  });

  test("TC-003: retired harness pages redirect to Validation Lab", () => {
    for (const rel of [
      "services/ui/src/app/admin/ai-summarisation/page.tsx",
      "services/ui/src/app/admin/extraction-scenarios/page.tsx",
      "services/ui/src/app/admin/coding-validation/page.tsx",
    ]) {
      const src = readFile(rel);
      expect(src).toMatch(/\/admin\/validation-lab/);
      expect(src).toMatch(/router\.replace/);
    }
  });

  test("TC-004: keep/retire matrix documented", () => {
    const src = readFile("docs/VALIDATION-LAB.md");
    expect(src).toMatch(/Pathway Builder probes/);
    expect(src).toMatch(/Retired -- all synthetic-data surfaces/);
    expect(src).toMatch(/production/);
  });

  test("TC-005: OverviewPanel uses LeoSbarHost for clinical SBAR", () => {
    const src = readFile(
      "services/ui/src/components/patients/OverviewPanel.tsx",
    );
    expect(src).toMatch(/LeoSbarHost/);
    expect(src).not.toMatch(/SbarFinalView/);
  });

  test("TC-006: Knowledge hub registers Validation Lab only (no Test Patients tab)", () => {
    const page = readFile("services/ui/src/app/admin/knowledge/page.tsx");
    const sidebar = readFile(
      "services/ui/src/components/ui/KnowledgeSidebar.tsx",
    );
    expect(page).toMatch(/validation-lab/);
    expect(page).toMatch(/"test-patients"/);
    expect(page).toMatch(/set\("tab", "validation-lab"\)/);
    expect(sidebar).toMatch(/Validation Lab/);
    expect(sidebar).not.toMatch(/Test Patients/);
    expect(sidebar).not.toMatch(/AI Summarisation/);
    expect(sidebar).not.toMatch(/Coding Validation/);
  });

  test("TC-007: DocumentViewer uses LeoSbarHost only for SBAR document types", () => {
    const src = readFile(
      "services/ui/src/components/patients/DocumentViewer.tsx",
    );
    const fmt = readFile(
      "services/ui/src/components/patients/documentFormat.ts",
    );
    expect(src).toMatch(/LeoSbarHost/);
    expect(src).toMatch(/isSbarDocument/);
    expect(src).not.toMatch(/SbarFinalView/);
    expect(fmt).toMatch(/mergeDocumentsNewestFirst/);
    expect(fmt).toMatch(/assessmentToDocumentRow/);
  });

  test("TC-008: Lab Cases panel exposes promote-gold and the wizard's phase outputs", () => {
    const src = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const rolodex = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientRolodex.tsx",
    );
    const filters = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientRolodexFilters.tsx",
    );
    const card = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientCard.tsx",
    );
    const wizard = readFile(
      "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
    );
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    expect(src).toMatch(/validation-lab-promote/);
    expect(src).toMatch(/validation-lab-view-patient/);
    expect(src).toMatch(/validation-lab-patient-dialog/);
    expect(src).toMatch(/PatientShell/);
    expect(src).toMatch(/TestPatientRolodex/);
    expect(filters).toMatch(/validation-lab-case-search/);
    expect(filters).toMatch(/validation-lab-filter-scenario/);
    expect(filters).toMatch(/validation-lab-filter-tag/);
    expect(rolodex).toMatch(/caseSearchHaystack/);
    expect(rolodex).toMatch(/TestPatientRolodexFilters/);
    expect(rolodex).toMatch(/TestPatientCard/);
    expect(card).toMatch(/validation-lab-summary-/);
    expect(card).toMatch(/validation-lab-tags-/);
    expect(card).toMatch(/validation-lab-delete-/);
    expect(card).toMatch(/validation-lab-view-/);
    expect(api).toMatch(/function deleteCase/);
    expect(api).toMatch(/function updateCase/);
    expect(wizard).toMatch(/wizard-phase-outputs/);
    expect(wizard).toMatch(/wizard-sbar/);
  });

  test("TC-012: rolodex multi-select delete uses ConfirmDialog", () => {
    const panel = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const rolodex = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientRolodex.tsx",
    );
    const card = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientCard.tsx",
    );
    expect(rolodex).toMatch(/ConfirmDialog/);
    expect(rolodex).toMatch(/validation-lab-select-all/);
    expect(rolodex).toMatch(/validation-lab-delete-selected/);
    expect(rolodex).toMatch(/onDeleteMany/);
    expect(rolodex).not.toMatch(/window\.confirm/);
    expect(card).toMatch(/validation-lab-check-/);
    expect(card).toMatch(/onToggleCheck/);
    expect(panel).toMatch(/async function onDeleteMany/);
    expect(panel).toMatch(/onDeleteMany=\{onDeleteMany\}/);
  });

  test("TC-011: test-patient card Test control starts a production Lab run", () => {
    const src = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const rolodex = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientRolodex.tsx",
    );
    const card = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientCard.tsx",
    );
    const labRun = readFile(
      "services/ui/src/app/admin/validation-lab/labRun.ts",
    );
    expect(rolodex).toMatch(/onTest/);
    expect(card).toMatch(/validation-lab-test-/);
    expect(card).toMatch(/Test pipeline for/);
    expect(src).toMatch(/async function onTest/);
    expect(src).toMatch(/queueCasePipeline/);
    expect(src).toMatch(/pollCasePipeline/);
    expect(src).toMatch(/validation-lab-test-pipeline/);
    expect(src).toMatch(/testingCaseId/);
    expect(labRun).toMatch(/persist_mode: "production"/);
    expect(labRun).toMatch(/pd-referral-assessment/);
    expect(labRun).toMatch(/pollRunUntilTerminal/);
    expect(labRun).toMatch(/startRun/);
  });

  test("TC-013: rolodex Test selected queues then live-polls in parallel", () => {
    const panel = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const rolodex = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientRolodex.tsx",
    );
    const labRun = readFile(
      "services/ui/src/app/admin/validation-lab/labRun.ts",
    );
    const batch = readFile(
      "services/ui/src/app/admin/validation-lab/labBatchRunner.ts",
    );
    expect(rolodex).toMatch(/validation-lab-test-selected/);
    expect(rolodex).toMatch(/onTestMany/);
    expect(rolodex).toMatch(/Test selected/);
    expect(panel).toMatch(/async function onTestMany/);
    expect(panel).toMatch(/runBatchWithLiveProgress/);
    expect(panel).toMatch(/onTestMany=\{onTestMany\}/);
    expect(batch).toMatch(/queueCasePipelines/);
    expect(batch).toMatch(/pollManyCasePipelines/);
    expect(labRun).toMatch(/export async function queueCasePipelines/);
    expect(labRun).toMatch(/export async function pollManyCasePipelines/);
    expect(labRun).toMatch(/export async function queueCasePipeline/);
    expect(labRun).toMatch(/persist_mode: "production"/);
    const queueFn = labRun.match(
      /export async function queueCasePipelines[\s\S]*?^}/m,
    )?.[0];
    expect(queueFn).toBeTruthy();
    expect(queueFn).not.toMatch(/pollRunUntilTerminal/);
    const pollMany = labRun.match(
      /export async function pollManyCasePipelines[\s\S]*?^}/m,
    )?.[0];
    expect(pollMany).toBeTruthy();
    expect(pollMany).toMatch(/Promise\.all/);
    expect(pollMany).toMatch(/getRun/);
  });

  test("TC-014: run sheet dialog covers single and multi Lab runs", () => {
    const panel = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const sheet = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetDialog.tsx",
    );
    expect(panel).toMatch(/RunSheetDialog/);
    expect(panel).toMatch(/pollCasePipeline/);
    expect(panel).toMatch(/runBatchWithLiveProgress/);
    expect(panel).toMatch(/setRunSheet/);
    expect(sheet).toMatch(/validation-lab-run-sheet/);
    expect(sheet).toMatch(/validation-lab-run-sheet-dismiss/);
    expect(sheet).toMatch(/Work in background/);
    expect(sheet).toMatch(/Live pipeline progress/);
    expect(sheet).toMatch(/phase: "queueing" \| "watching"/);
    expect(sheet).toMatch(/ProgressStrip/);
    expect(sheet).toMatch(/useMotion/);
    expect(sheet).toMatch(/reducedMotion/);
    expect(sheet).toMatch(/framer-motion/);
    expect(sheet).not.toMatch(/window\.confirm/);
    expect(sheet).not.toMatch(/\balert\s*\(/);
    expect(sheet).toMatch(/RunInspectorPanel/);
    expect(sheet).toMatch(/useLabRunInspector/);
    expect(sheet).toMatch(/liveSpans/);
    expect(sheet).toMatch(/maxWidth="lg"/);
    const inspectorPanel = readFile(
      "services/ui/src/app/admin/validation-lab/inspector/RunInspectorPanel.tsx",
    );
    expect(inspectorPanel).toMatch(/validation-lab-run-inspector/);
    expect(inspectorPanel).toMatch(/RunInspectorSummaryTab/);
    expect(inspectorPanel).toMatch(/validation-lab-inspector-tab-summary/);
    expect(inspectorPanel).toMatch(/validation-lab-inspector-tab-data/);
    const dataTab = readFile(
      "services/ui/src/app/admin/validation-lab/inspector/RunInspectorDataTab.tsx",
    );
    expect(dataTab).toMatch(/TraceWaterfallChart/);
    expect(dataTab).toMatch(/TraceFlowGraph/);
    expect(dataTab).toMatch(/TraceEndpointPanel/);
    const stagePane =
      readFile(
        "services/ui/src/app/admin/validation-lab/inspector/StageDetailPane.tsx",
      ) +
      readFile(
        "services/ui/src/app/admin/validation-lab/inspector/StageExtraDetail.tsx",
      );
    expect(stagePane).toMatch(/extraction_model_name/);
    expect(stagePane).toMatch(/Model /);
  });

  test("TC-016: single run sheet lists stages task-by-task and skips queued as done", () => {
    const panel = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const sheet = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetDialog.tsx",
    );
    const tasks = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetTasks.tsx",
    );
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    expect(api).toMatch(/StageProgress/);
    expect(api).toMatch(/stage_progress\?:/);
    expect(panel).toMatch(/stage_progress/);
    expect(sheet).toMatch(/TaskList/);
    expect(sheet).toMatch(/stages\?:/);
    expect(tasks).toMatch(/validation-lab-run-sheet-tasks/);
    expect(tasks).toMatch(/liveSpans\?:/);
    expect(tasks).toMatch(/DONE_STATUSES/);
    expect(tasks).toMatch(
      /DONE_STATUSES = new Set\(\[\s*"completed",\s*"failed",\s*"skipped_persist",\s*\]\)/,
    );
  });

  test("TC-017: run sheet shows agent name and copy support details", () => {
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    const tasks = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetTasks.tsx",
    );
    const sheet = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetDialog.tsx",
    );
    const support = readFile(
      "services/ui/src/app/admin/validation-lab/runSheetSupport.ts",
    );
    const roster = readFile(
      "services/ui/src/app/admin/validation-lab/agentRoster.ts",
    );
    expect(api).toMatch(/worker_id\?:/);
    expect(tasks).toMatch(/workerId/);
    expect(tasks).toMatch(/formatAgentName/);
    expect(tasks).toMatch(/Agent:/);
    expect(tasks).toMatch(/validation-lab-run-sheet-worker-/);
    expect(sheet).toMatch(/validation-lab-run-sheet-copy-support/);
    expect(sheet).toMatch(/Copy support details/);
    expect(support).toMatch(/buildSupportContext/);
    expect(support).toMatch(/agent=/);
    expect(support).toMatch(/worker=/);
    expect(roster).toMatch(/PIPELINE_AGENT_ROSTER/);
    expect(roster).toMatch(/formatAgentName/);
    expect(roster).toMatch(/"Ada"/);
  });

  test("TC-018: completed single run sheet opens SBAR in a Drawer via CDN host", () => {
    const sheet = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetDialog.tsx",
    );
    const sbar = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetSbar.tsx",
    );
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    expect(sheet).toMatch(/RunSheetSbarActions/);
    expect(sbar).toMatch(/Open SBAR result/);
    expect(sbar).toMatch(/validation-lab-run-sheet-open-sbar/);
    expect(sbar).toMatch(/from\s+["']@mui\/material\/Drawer["']/);
    expect(sbar).toMatch(/validation-lab-run-sheet-sbar-drawer/);
    expect(sbar).toMatch(/LeoSbarHost/);
    expect(sbar).toMatch(/loadSbarAssessmentId/);
    expect(sbar).toMatch(/sheet\.status !== "completed"/);
    expect(api).toMatch(/export async function loadSbarAssessmentId/);
    expect(api).toMatch(/sbar_assessment_id/);
  });

  test("TC-015: Lab run cost from Assessment telemetry shown on card and sheet", () => {
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    const card = readFile(
      "services/ui/src/app/admin/validation-lab/TestPatientCard.tsx",
    );
    const sheet = readFile(
      "services/ui/src/app/admin/validation-lab/RunSheetDialog.tsx",
    );
    const panel = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const format = readFile(
      "services/ui/src/app/admin/validation-lab/labRunFormat.ts",
    );
    expect(api).toMatch(/LabRunLlmUsage/);
    expect(api).toMatch(/llm_usage\?:/);
    expect(api).toMatch(/latest_llm_cost_usd/);
    expect(card).toMatch(/validation-lab-cost-/);
    expect(card).toMatch(/formatUsd/);
    expect(card).toMatch(/latest_llm_cost_usd/);
    expect(sheet).toMatch(/validation-lab-run-sheet-cost/);
    expect(sheet).toMatch(/Cost n\/a/);
    expect(sheet).toMatch(/sumBatchCostUsd/);
    expect(sheet).toMatch(/validation-lab-run-sheet-batch-cost/);
    expect(sheet).toMatch(/Batch cost:/);
    expect(format).toMatch(/export function sumBatchCostUsd/);
    expect(panel).toMatch(/formatUsd\(latestCost\)/);
  });

  test("TC-009: wizard supports A&G case type and thread builder chrome", () => {
    const wizard = readFile(
      "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
    );
    const hook = readFile(
      "services/ui/src/app/admin/validation-lab/useCreatePatientWizard.ts",
    );
    const agStep = readFile(
      "services/ui/src/app/admin/validation-lab/WizardAgThreadSteps.tsx",
    );
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    expect(wizard).toMatch(/wizard-scenario/);
    expect(wizard).toMatch(/generic_ag/);
    expect(wizard).toMatch(/WizardAgThreadStep/);
    expect(agStep).toMatch(/wizard-step-ag-thread/);
    expect(hook).toMatch(/case_type: caseType/);
    expect(agStep).toMatch(/wizard-ag-add-requester/);
    expect(agStep).toMatch(/wizard-ag-formal-response/);
    expect(api).toMatch(/startAgRun/);
    expect(api).toMatch(/ag_thread/);
  });

  test("TC-010: SPoA scenario chrome exposes GP consult, reason, and PMH preview", () => {
    const wizard = readFile(
      "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
    );
    const hook = readFile(
      "services/ui/src/app/admin/validation-lab/useCreatePatientWizard.ts",
    );
    const gpStep = readFile(
      "services/ui/src/app/admin/validation-lab/WizardGpConsultStep.tsx",
    );
    const api = readFile("services/ui/src/app/admin/validation-lab/labApi.ts");
    expect(wizard).toMatch(/spo_ag/);
    expect(wizard).toMatch(/ras_referral/);
    expect(wizard).toMatch(/WizardGpConsultStep/);
    expect(wizard).toMatch(/wizard-reason-for-submission/);
    expect(wizard).toMatch(/wizard-preview-pmh/);
    expect(gpStep).toMatch(/wizard-step-gp-consult/);
    expect(gpStep).toMatch(/wizard-gp-consult-text/);
    expect(hook).toMatch(/scenario_type:/);
    expect(hook).toMatch(/gp_encounter:/);
    expect(hook).toMatch(/previewPmhNarrative/);
    expect(api).toMatch(/previewPmhNarrative/);
    expect(api).toMatch(/LabScenarioType/);
  });
});

describe("VT-10011926 - Validation Lab three-path home", () => {
  test("home shows the three paths and the findings strip", () => {
    const home =
      readFile("services/ui/src/app/admin/validation-lab/AccuracyLoopHome.tsx") +
      readFile("services/ui/src/app/admin/validation-lab/accuracyLoopDoors.ts") +
      readFile(
        "services/ui/src/app/admin/validation-lab/AccuracyLoopHomeParts.tsx",
      );
    const page = readFile(
      "services/ui/src/app/admin/validation-lab/page.tsx",
    );
    const rule = readFile(
      "services/ui/src/app/admin/validation-lab/RuleDoor.tsx",
    );
    const clinical = readFile(
      "services/ui/src/app/admin/validation-lab/ClinicalDoor.tsx",
    );
    const picker = readFile(
      "services/ui/src/app/admin/validation-lab/ClinicalPatientPicker.tsx",
    );
    const lists = readFile(
      "services/ui/src/app/admin/validation-lab/ClinicalPatientLists.tsx",
    );
    const chrome = readFile(
      "services/ui/src/app/admin/validation-lab/clinicalDoorChrome.ts",
    );
    const doorState = readFile(
      "services/ui/src/app/admin/validation-lab/clinicalDoorState.ts",
    );
    const used = readFile(
      "services/ui/src/app/admin/validation-lab/clinicalUsedPatients.ts",
    );
    expect(home).toMatch(/Investigate a non-conformance/);
    expect(home).toMatch(/Run baseline tests/);
    expect(home).toMatch(/Build new tests/);
    expect(home).toMatch(/gold cases/);
    expect(home).toMatch(/Open findings/);
    expect(home).toMatch(/validation-lab-home-strip/);
    expect(rule).toMatch(/listGuidanceRules/);
    expect(rule).toMatch(/queueCasePipeline/);
    expect(rule).toMatch(/uniqueByRuleId/);
    expect(doorState).toMatch(/listClinicalPipelineRuns/);
    expect(doorState).toMatch(/listClinicalPatients/);
    expect(doorState).toMatch(/searchMode/);
    expect(doorState).toMatch(/listClinicalPipelineRuns\(\{ q, mode \}\)/);
    expect(clinical).toMatch(/does not start a new job/);
    expect(clinical).toMatch(/ClinicalNcrPanel/);
    expect(clinical).toMatch(/Why did you open this\?/);
    expect(clinical).not.toMatch(/label="Why did you open this\?"/);
    expect(picker).toMatch(/NHS number, or referral number/);
    expect(picker).toMatch(/UBRN/);
    expect(picker).toMatch(/In letters/);
    expect(picker).toMatch(/Words from the letter/);
    expect(lists).toMatch(/Recently used/);
    expect(lists).toMatch(/Frequently used/);
    expect(lists).toMatch(/All patients/);
    expect(chrome).toMatch(/backdropFilter/);
    expect(chrome).toMatch(/prefers-reduced-motion/);
    expect(chrome).toMatch(/matchLabel/);
    expect(picker).toMatch(/glassPanel/);
    expect(used).toMatch(/recentlyUsed/);
    expect(used).toMatch(/frequentlyUsed/);
    expect(doorState).toMatch(/whyOpened/);
    expect(doorState).not.toMatch(/referralText: why/);
    expect(home).toMatch(/Look up or open the product NCR/);
    expect(page).toMatch(/AccuracyLoopHome/);
  });
});

describe("VT-F0A6B9F4 - run review mark as wrong", () => {
  test("lightbox shows letter, stages, mark as wrong, SBAR, and log", () => {
    const lightbox = readFile(
      "services/ui/src/app/admin/validation-lab/RunReviewLightbox.tsx",
    );
    const letter = readFile(
      "services/ui/src/app/admin/validation-lab/LetterPane.tsx",
    );
    const pane =
      readFile(
        "services/ui/src/app/admin/validation-lab/inspector/StageDetailPane.tsx",
      ) +
      readFile(
        "services/ui/src/app/admin/validation-lab/inspector/StageExtraDetail.tsx",
      );
    const dialog = readFile(
      "services/ui/src/app/admin/validation-lab/MarkWrongDialog.tsx",
    );
    const types = readFile(
      "services/ui/src/app/admin/validation-lab/findingTypes.ts",
    );
    const marks = readFile(
      "services/ui/src/app/admin/validation-lab/LetterMarks.tsx",
    );
    const legend = readFile(
      "services/ui/src/app/admin/validation-lab/LetterMarkLegend.tsx",
    );
    const style = readFile(
      "services/ui/src/app/admin/validation-lab/letterMarkStyle.ts",
    );
    const highlight = readFile(
      "services/ui/src/app/admin/validation-lab/letterHighlight.ts",
    );
    expect(lightbox).toMatch(/LetterPane/);
    expect(lightbox).toMatch(/source_text/);
    expect(lightbox).toMatch(/stageLetterHighlights/);
    expect(lightbox).not.toMatch(/items\?\.\[0\]\?\.text/);
    expect(letter).toMatch(/LetterMarks/);
    expect(letter).toMatch(/LetterMarkLegend/);
    expect(letter).toMatch(/marks=\{marks\}/);
    expect(letter).not.toMatch(/HighlightedText/);
    expect(highlight).toMatch(/letterHighlightMarks/);
    expect(highlight).toMatch(/semanticTag/);
    expect(marks).toMatch(/data-assertion/);
    expect(marks).toMatch(/data-semantic-tag/);
    expect(marks).toMatch(/LetterMarkLegend/);
    expect(marks).toMatch(/borderLeft/);
    expect(marks).toMatch(/markContextBar/);
    expect(legend).toMatch(/How to read a highlight/);
    expect(legend).toMatch(/When it applies -- the bar/);
    expect(legend).toMatch(/What it is -- the colour/);
    expect(legend).toMatch(/LEGEND_WHEN_KEYS/);
    expect(legend).toMatch(/LEGEND_WHAT_KEYS/);
    expect(legend).toMatch(/the colour means finding. The bar means present/);
    expect(style).toMatch(/export const ASSERTION_STYLE/);
    expect(style).toMatch(/export const TAG_STYLE/);
    expect(style).toMatch(/LEGEND_WHEN_KEYS/);
    expect(style).toMatch(/markContextBar/);
    expect(style).toMatch(/CONTEXT_BAR_PX/);
    expect(style).toMatch(/#CA8A04/);
    expect(style).toMatch(/#DC2626/);
    expect(style).not.toMatch(/linear-gradient/);
    expect(marks).toMatch(/CONTEXT_BAR_PX/);
    expect(legend).toMatch(/CONTEXT_BAR_PX/);
    expect(marks).toMatch(/data-change/);
    expect(marks).toMatch(/leoUncoded/);
    expect(style).toMatch(/historical/);
    expect(style).toMatch(/#CBD5E1/);
    expect(style).toMatch(/#99F6E4/);
    expect(style).toMatch(/#F9A8D4/);
    expect(lightbox).toMatch(/PipelineWizard/);
    expect(lightbox).toMatch(/MarkWrongDialog/);
    expect(lightbox).toMatch(/RunSheetSbarActions/);
    expect(lightbox).toMatch(/Show live log/);
    expect(pane).toMatch(/Yes, this step looks right/);
    expect(pane).toMatch(/No, mark something wrong/);
    expect(pane).toMatch(/validation-lab-next-step/);
    expect(pane).toMatch(/validation-lab-mark-wrong/);
    expect(pane).toMatch(/Next step/);
    expect(pane).toMatch(/Show extra detail/);
    expect(pane).not.toMatch(/Mark as wrong/);
    expect(lightbox).toMatch(/findingSavedAt/);
    expect(dialog).toMatch(/extraction/);
    expect(types).toMatch(/phrase_mapping/);
    expect(types).toMatch(/guideline_rule/);
    expect(types).toMatch(/semantic_tag/);
    expect(types).toMatch(/Wrong kind of fact/);
    expect(types).toMatch(/Other instead of a procedure/);
    expect(dialog).not.toMatch(/ConText/);
  });
});

describe("VT-5E51F5D9 - findings persist and fix routing", () => {
  test("findings API and fix URLs cover each category", () => {
    const api = readFile(
      "services/ui/src/app/admin/validation-lab/labFindingsApi.ts",
    );
    const routes = readFile(
      "services/ui/src/app/admin/validation-lab/fixRoutes.ts",
    );
    const clinical = readFile(
      "services/api/app/routers/validation_lab_clinical.py",
    );
    expect(api).toMatch(/createFinding/);
    expect(api).toMatch(/listClinicalPipelineRuns/);
    expect(api).toMatch(/listClinicalPatients/);
    expect(api).toMatch(/mode=\$\{mode\}/);
    expect(api).toMatch(/getPipelineRunInspector/);
    expect(routes).toMatch(/tab: "ai-instructions"/);
    expect(routes).toMatch(/tab: "context-rules"/);
    expect(routes).toMatch(/tab: "guard-rules"/);
    expect(routes).toMatch(/tab: "surface-forms"/);
    expect(routes).toMatch(/tab: "clinical-guidelines"/);
    expect(routes).toMatch(/semantic_tag/);
    expect(clinical).toMatch(/Does not enqueue/);
    expect(clinical).toMatch(/get_pipeline_inspector/);
    expect(clinical).toMatch(/find_pipeline_runs/);
    expect(clinical).toMatch(/list_clinical_patients/);
    expect(clinical).toMatch(/clinical-patients/);
    expect(clinical).toMatch(/semantic_tag/);
  });
});
