/**
 * VT-812B971C -- Validation Lab bitmap version on runs.
 *
 * Atlas:
 *   DI: DI-58CE9939
 *   DO: DO-158BE606, DO-3A70C3DD
 *   VT: VT-812B971C
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, rel), "utf8");
}

describe("VT-812B971C - Validation Lab bitmap version on runs", () => {
  test("TC-001: LabRun and case list carry ruleset_version fields", () => {
    const api = read("services/ui/src/app/admin/validation-lab/labApi.ts");
    expect(api).toMatch(/ruleset_version\?:/);
    expect(api).toMatch(/latest_run_ruleset_version\?:/);
  });

  test("TC-002: test-patient card shows bitmap chip from latest run", () => {
    const card = read(
      "services/ui/src/app/admin/validation-lab/TestPatientCard.tsx",
    );
    expect(card).toMatch(/latest_run_ruleset_version/);
    expect(card).toMatch(/validation-lab-bitmap-\$\{c\.id\}/);
    expect(card).toMatch(/bitmap \$\{c\.latest_run_ruleset_version\}/);
  });

  test("TC-003: case detail and run sheet show ruleset version", () => {
    const panel = read(
      "services/ui/src/app/admin/validation-lab/LabCasesPanel.tsx",
    );
    const sheet = read(
      "services/ui/src/app/admin/validation-lab/RunSheetDialog.tsx",
    );
    expect(panel).toMatch(/validation-lab-latest-bitmap/);
    expect(panel).toMatch(/rulesetVersion:\s*run\.ruleset_version/);
    expect(sheet).toMatch(/validation-lab-run-sheet-bitmap/);
    expect(sheet).toMatch(/rulesetVersion/);
  });
});
