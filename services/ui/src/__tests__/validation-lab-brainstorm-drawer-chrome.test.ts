/**
 * VT-C6B93AF0 -- Validation Lab brainstorm drawer chrome.
 *
 * Atlas: DI-EB716E68 / DO-A0ADDB38
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("VT-C6B93AF0 - Validation Lab brainstorm drawer chrome", () => {
  test("drawer stepper, attach, clarify, variants, create N", () => {
    const src = readFile(
      "services/ui/src/app/admin/validation-lab/ScenarioBrainstormDrawer.tsx",
    );
    expect(src).toMatch(/data-testid="scenario-brainstorm-drawer"/);
    expect(src).toMatch(/Stepper/);
    expect(src).toMatch(/Attach/);
    expect(src).toMatch(/Clarify/);
    expect(src).toMatch(/Variants/);
    expect(src).toMatch(/Review/);
    expect(src).toMatch(/RecommendationPickerDialog/);
    expect(src).toMatch(/mode="attach"/);
    expect(src).toMatch(/\/api\/nice\/loaded/);
    expect(src).toMatch(/Guideline in knowledge graph/);
    expect(src).not.toMatch(/Guideline code to attach/);
    const picker = readFile(
      "services/ui/src/app/admin/guidance/RecommendationPickerDialog.tsx",
    );
    expect(picker).toMatch(/Select recommendations to attach to this test scenario/);
    expect(picker).toMatch(/Existing rule can score whether the test case should fire/);
    expect(picker).toMatch(/sel\.checked && !attachMode/);
    expect(picker).toMatch(/Has existing rule - will add another/);
    expect(picker).toMatch(/pickLatestRule/);
    expect(picker).toMatch(/attachMode && latestRule/);
    expect(picker).toMatch(/ATTACH_STATUS_LABEL/);
    expect(picker).toMatch(/active:\s*"approved"/);
    expect(picker).toMatch(/not the same as being in the live bitmap/);
    const selection = readFile(
      "services/ui/src/app/admin/guidance/recommendationPickerSelection.ts",
    );
    expect(selection).toMatch(/attachMode/);
    expect(selection).toMatch(/checked: false/);
    expect(selection).toMatch(/export function pickLatestRule/);
    expect(selection).toMatch(/export function pickAttachRule/);
    expect(src).toMatch(/allowMultiple|allow_multiple|maxSelections/);
    expect(src).toMatch(/createCasesFromVariants/);
    expect(src).not.toMatch(/createCase\(/);
    expect(src).toMatch(
      /setSelectedIds\(\s*new Set\(\s*next\.map\(\s*\(v\)\s*=>\s*v\.variantId\s*\)\s*\)\s*\)/,
    );
    expect(src).not.toMatch(/recommendedIds/);
    const variantsStep = readFile(
      "services/ui/src/app/admin/validation-lab/ScenarioBrainstormVariantsStep.tsx",
    );
    expect(variantsStep).toMatch(/brainstorm-empty-variants/);
    expect(variantsStep).toMatch(/brainstorm-variant-summary-/);
    expect(variantsStep).toMatch(/v\.tags/);
    expect(variantsStep).toMatch(/isControl/);
    expect(variantsStep).toMatch(/expectedTrigger/);
    expect(variantsStep).toMatch(/Create \d+|Create N|Create \$\{/);
  });

  test("wizard opens brainstorm drawer", () => {
    const wizard = readFile(
      "services/ui/src/app/admin/validation-lab/CreatePatientWizard.tsx",
    );
    expect(wizard).toMatch(/ScenarioBrainstormDrawer/);
    expect(wizard).toMatch(/Brainstorm scenario/);
  });
});
