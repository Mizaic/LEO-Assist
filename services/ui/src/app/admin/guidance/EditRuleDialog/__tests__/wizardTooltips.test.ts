/**
 * Static-source VT: Highlight Wizard buttons expose MUI Tooltip (T12a).
 *
 * Atlas trace: DI-42246DA7 / DO-F8C56339
 */
import fs from "fs";
import path from "path";

const WIZARD_DIR = path.join(__dirname, "..", "HighlightWizard");

const FILES_EXPECTING_TOOLTIP = [
  "StepPrerequisites.tsx",
  "StepPathwaySplit.tsx",
  "StepPathwayConditions.tsx",
  "PathwayDemographicsPanel.tsx",
  "PathwaySplitEmptyStates.tsx",
  "WizardHeader.tsx",
  "ProblemNodeRow.tsx",
  "RowMultiCodeHighlight.tsx",
] as const;

function readWizard(file: string): string {
  return fs.readFileSync(path.join(WIZARD_DIR, file), "utf8");
}

describe("Highlight Wizard tooltips (T12a)", () => {
  test.each(FILES_EXPECTING_TOOLTIP)("%s imports MUI Tooltip", (file) => {
    const src = readWizard(file);
    expect(src).toMatch(/from "@mui\/material\/Tooltip"/);
    expect(src).toMatch(/<Tooltip\b/);
  });

  test("copy.ts exports WIZARD_TOOLTIPS strings", () => {
    const src = readWizard("copy.ts");
    expect(src).toMatch(/export const WIZARD_TOOLTIPS/);
    expect(src).toMatch(/noMore:/);
    expect(src).toMatch(/copyAcross:/);
    expect(src).toMatch(/multiCodeHighlight:/);
  });
});
