/**
 * Static VT: EPR overview layout keeps SBAR primary and avoids redundant rails.
 *
 * Atlas: DI-357A7468 / DO-5D3EA371
 */
import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../../..");

function readUi(rel: string): string {
  return readFileSync(join(REPO_ROOT, "services/ui/src", rel), "utf8");
}

describe("EPR overview layout chrome", () => {
  test("OverviewPanel keeps LeoSbarHost and full-width Latest SBAR pane", () => {
    const src = readUi("components/patients/OverviewPanel.tsx");
    expect(src).toMatch(/LeoSbarHost/);
    expect(src).toMatch(/epr-latest-sbar/);
    expect(src).toMatch(/Latest SBAR/);
    expect(src).not.toMatch(/SbarFinalView/);
    // Demographics belong in PatientHeader -- not duplicated here.
    expect(src).not.toMatch(/Patient details/);
    expect(src).not.toMatch(/NHS number/);
  });

  test("PatientShell uses clinical-context rail instead of empty guidance placeholder", () => {
    const shell = readUi("components/patients/PatientShell.tsx");
    const rails = readUi("components/patients/PatientContextRails.tsx");
    expect(shell).toMatch(/ClinicalContextRail/);
    expect(shell).toMatch(/ContextRail/);
    expect(rails).toMatch(/epr-clinical-context-rail/);
    expect(rails).toMatch(/Problem list/);
    expect(rails).toMatch(/Alerts/);
    expect(rails).not.toMatch(/Guidelines will appear here/);
    expect(rails).not.toMatch(/Known conditions/);
    expect(rails).not.toMatch(/GP Practice/);
  });

  test("Overview shows problem/alerts fallback below xl breakpoint", () => {
    const src = readUi("components/patients/OverviewPanel.tsx");
    expect(src).toMatch(/epr-overview-context-fallback/);
    expect(src).toMatch(/display:\s*\{\s*xs:\s*"flex",\s*xl:\s*"none"\s*\}/);
  });
});
