/**
 * Validation Lab home -- two doors, one job, 11-year-old copy.
 */
import * as fs from "fs";
import * as path from "path";

const HOME = path.join(
  __dirname,
  "../app/admin/validation-lab/AccuracyLoopHome.tsx",
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
    home = fs.readFileSync(HOME, "utf-8");
    panel = fs.readFileSync(PANEL, "utf-8");
    plain = fs.readFileSync(PLAIN, "utf-8");
  });

  it("offers two doors: test a guideline rule or investigate a complaint", () => {
    expect(home).toMatch(/Test a guideline rule/);
    expect(home).toMatch(/Investigate a clinical complaint/);
    expect(home).toMatch(/validation-lab-mode-rule/);
    expect(home).toMatch(/validation-lab-mode-clinical/);
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
