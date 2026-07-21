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
  test("TC-001: Validation Lab page mounts the single patient wizard flow", () => {
    const page = readFile(
      "services/ui/src/app/admin/validation-lab/page.tsx",
    );
    const cases = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const wizard = readFile(
      "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
    );
    expect(page).toMatch(/validation-lab-page/);
    expect(page).toMatch(/LabCasesPanel/);
    expect(page).not.toMatch(/TestPatientLibraryKnowledgeTab/);
    expect(cases).toMatch(/CreatePatientWizard/);
    expect(cases).toMatch(/LeoSbarHost/);
    expect(wizard).toMatch(/Submit referral/);
    expect(wizard).toMatch(/wizard-step-referral/);
  });

  test("TC-002: LeoSbarHost mints widget token and mounts leo-sbar", () => {
    const src = readFile(
      "services/ui/src/components/sbar-final/LeoSbarHost.tsx",
    );
    expect(src).toMatch(/\/api\/sdk\/widget-token/);
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
    expect(src).toMatch(/runCasePipeline/);
    expect(src).toMatch(/validation-lab-test-pipeline/);
    expect(src).toMatch(/testingCaseId/);
    expect(labRun).toMatch(/persist_mode: "production"/);
    expect(labRun).toMatch(/pd-referral-assessment/);
    expect(labRun).toMatch(/pollRunUntilTerminal/);
    expect(labRun).toMatch(/startRun/);
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
