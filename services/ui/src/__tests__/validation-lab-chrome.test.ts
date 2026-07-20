/**
 * VT-22F3EF6A -- Validation Lab chrome + retire redirects.
 *
 * Atlas: DI-A898556B / DO-158BE606
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
    expect(src).toMatch(/Fold into Validation Lab/);
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

  test("TC-007: DocumentViewer prefers LeoSbarHost when assessment id present", () => {
    const src = readFile(
      "services/ui/src/components/patients/DocumentViewer.tsx",
    );
    expect(src).toMatch(/LeoSbarHost/);
    expect(src).not.toMatch(/SbarFinalView/);
  });

  test("TC-008: Lab Cases panel exposes promote-gold and the wizard's phase outputs", () => {
    const src = readFile(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const wizard = readFile(
      "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
    );
    expect(src).toMatch(/validation-lab-promote/);
    expect(wizard).toMatch(/wizard-phase-outputs/);
    expect(wizard).toMatch(/wizard-sbar/);
  });
});
