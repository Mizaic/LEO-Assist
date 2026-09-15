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

  test("Overview always shows problem list and medicines in the reading column", () => {
    const src = readUi("components/patients/OverviewPanel.tsx");
    expect(src).toMatch(/epr-overview-context/);
    expect(src).toMatch(/epr-overview-medicines/);
    expect(src).toMatch(/Problem list/);
    expect(src).not.toMatch(/Guidelines will appear here/);
    expect(src).not.toMatch(/Known conditions/);
    expect(src).not.toMatch(/GP Practice/);
  });
});
