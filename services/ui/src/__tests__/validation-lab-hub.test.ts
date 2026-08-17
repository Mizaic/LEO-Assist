/**
 * Validation Lab home -- three paths, one job, 11-year-old copy.
 */
import * as fs from "fs";
import * as path from "path";

const HOME = path.join(
  __dirname,
  "../app/admin/validation-lab/AccuracyLoopHome.tsx",
);
const DOORS = path.join(
  __dirname,
  "../app/admin/validation-lab/accuracyLoopDoors.ts",
);
const PANEL = path.join(
  __dirname,
  "../app/admin/validation-lab/LabCasesPanel.tsx",
);
const PLAIN = path.join(
  __dirname,
  "../app/admin/validation-lab/plainStageCopy.ts",
);

describe("Validation Lab home", () => {
  let home: string;
  let panel: string;
  let plain: string;

  beforeAll(() => {
    home =
      fs.readFileSync(HOME, "utf-8") + fs.readFileSync(DOORS, "utf-8");
    panel = fs.readFileSync(PANEL, "utf-8");
    plain = fs.readFileSync(PLAIN, "utf-8");
  });

  it("offers three paths in investigation, baseline, then build order", () => {
    expect(home).toMatch(/Investigate a non-conformance/);
    expect(home).toMatch(/Run baseline tests/);
    expect(home).toMatch(/Build new tests/);
    expect(home).toMatch(/validation-lab-mode-clinical/);
    expect(home).toMatch(/validation-lab-mode-saved/);
    expect(home).toMatch(/validation-lab-mode-rule/);
    const clinical = home.indexOf("Investigate a non-conformance");
    const baseline = home.indexOf("Run baseline tests");
    const build = home.indexOf("Build new tests");
    expect(clinical).toBeGreaterThan(-1);
    expect(baseline).toBeGreaterThan(clinical);
    expect(build).toBeGreaterThan(baseline);
  });

  it("keeps platform admin intro in plain English", () => {
    const copy = fs.readFileSync(
      path.join(__dirname, "../lib/knowledgeCopy.ts"),
      "utf-8",
    );
    expect(copy).not.toMatch(/:ValidationCase/);
    expect(copy).toMatch(/Start with a product non-conformance/);
  });

  it("does not use Technical or ConText jargon on the home cards", () => {
    expect(home).not.toMatch(/Technical/);
    expect(home).not.toMatch(/ConText/);
    expect(home).not.toMatch(/synthetic/);
  });

  it("shows only the wizard or only the list, not both", () => {
    expect(panel).toMatch(/makingNew/);
    expect(panel).toMatch(/\{!makingNew && \(/);
  });

  it("maps stages to plain names a child can read", () => {
    expect(plain).toMatch(/Reading the letter/);
    expect(plain).toMatch(/Cleaning the facts/);
    expect(plain).toMatch(/Adding medical codes/);
    expect(plain).toMatch(/Checking the guideline/);
    expect(plain).toMatch(/Draft assessment/);
  });
});
