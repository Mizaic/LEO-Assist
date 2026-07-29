/**
 * VT-A34EE50D -- CandidateLabTestDialog chrome (case pick, live progress, SBAR drawer).
 *
 * Atlas: DI-8DD23CE2 / DO-599B9828 / VT-A34EE50D
 *
 * Static-source verification of the candidate Lab test dialog wiring.
 */

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../../services/ui/src/app/admin/guidance");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("VT - CandidateLabTestDialog chrome", () => {
  test("TC-001: dialog opens from bitmap lifecycle Test candidate action", () => {
    const section = read("BitmapLifecycleSection.tsx");
    const hook = read("useBitmapLifecycle.ts");
    expect(section).toMatch(/CandidateLabTestDialog/);
    expect(section).toMatch(/labTestOpen/);
    expect(hook).toMatch(/setLabTestOpen\(true\)/);
    expect(hook).toMatch(/handleTestOnLabPatients/);
    expect(hook).not.toMatch(/MAX_LAB_PATIENTS_TESTED/);
  });

  test("TC-002: pick stage supports all or multi-select before run", () => {
    const dialog = read("CandidateLabTestDialog.tsx");
    expect(dialog).toMatch(/candidate-lab-test-pick/);
    expect(dialog).toMatch(/toggleId/);
    expect(dialog).toMatch(/>\s*All\s*</);
    expect(dialog).toMatch(/>\s*Clear\s*</);
    expect(dialog).toMatch(/Run \{selectedCount\}/);
  });

  test("TC-003: run stage reuses labBatchRunner with ruleset_version pinned", () => {
    const dialog = read("CandidateLabTestDialog.tsx");
    const batch = fs.readFileSync(
      path.resolve(
        ROOT,
        "../validation-lab/labBatchRunner.ts",
      ),
      "utf8",
    );
    const labRun = fs.readFileSync(
      path.resolve(ROOT, "../validation-lab/labRun.ts"),
      "utf8",
    );
    expect(dialog).toMatch(/runBatchWithLiveProgress/);
    expect(dialog).toMatch(/rulesetVersion:\s*candidateVersion/);
    expect(dialog).toMatch(/ProgressStrip/);
    expect(batch).toMatch(/rulesetVersion\?:/);
    expect(labRun).toMatch(/ruleset_version:\s*rulesetVersion/);
  });

  test("TC-004: completed runs open SBAR in a Drawer not a nested dialog", () => {
    const dialog = read("CandidateLabTestDialog.tsx");
    expect(dialog).toMatch(/from\s+["']@mui\/material\/Drawer["']/);
    expect(dialog).toMatch(/candidate-lab-test-sbar-drawer/);
    expect(dialog).toMatch(/LeoSbarHost/);
    expect(dialog).toMatch(/View SBAR/);
    expect(dialog).toMatch(/loadSbarAssessmentId/);
  });

  test("TC-005: gold scoring summary is reported back to the lifecycle hook", () => {
    const dialog = read("CandidateLabTestDialog.tsx");
    const helpers = read("candidateLabTestHelpers.ts");
    const hook = read("useBitmapLifecycle.ts");
    expect(helpers).toMatch(/scoreSheetItems/);
    expect(dialog).toMatch(/scoreSheetItems/);
    expect(dialog).toMatch(/onComplete\(summary\)/);
    expect(hook).toMatch(/handleLabTestComplete/);
    expect(hook).toMatch(/setCandidateTestSummary/);
  });
});
