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
    expect(src).toMatch(/LoadedGuidelineAutocomplete/);
    expect(src).toMatch(/Guideline in knowledge graph/);
    const loadedAuto = readFile(
      "services/ui/src/app/admin/guidance/LoadedGuidelineAutocomplete.tsx",
    );
    expect(loadedAuto).toMatch(/\/api\/nice\/loaded/);
    expect(loadedAuto).toMatch(/Search loaded guidelines/);
    expect(src).not.toMatch(/Guideline code to attach/);
    const picker = readFile(
      "services/ui/src/app/admin/guidance/RecommendationPickerDialog.tsx",
    );
    expect(picker).toMatch(/Select recommendations to attach to this test scenario/);
    expect(picker).toMatch(/selectAllApproved/);
    expect(picker).toMatch(/selectAllCompiled/);
    const pickerApi = readFile(
      "services/ui/src/app/admin/guidance/recommendationPickerApi.ts",
    );
    expect(pickerApi).toMatch(/fetchCompiledRuleIds/);
    expect(pickerApi).toMatch(/bitmap\/status/);
    expect(pickerApi).toMatch(/rule_ids/);
    const toolbar = readFile(
      "services/ui/src/app/admin/guidance/RecommendationPickerToolbar.tsx",
    );
    expect(toolbar).toMatch(/Select all approved/);
    expect(toolbar).toMatch(/Select all compiled/);
    const rows = readFile(
      "services/ui/src/app/admin/guidance/RecommendationPickerRows.tsx",
    );
    expect(rows).toMatch(/Existing rule can score whether the test case should fire/);
    expect(rows).toMatch(/sel\.checked && !attachMode/);
    expect(rows).toMatch(/Has existing rule - will add another/);
    expect(rows).toMatch(/pickAttachRule/);
    const selection = readFile(
      "services/ui/src/app/admin/guidance/recommendationPickerSelection.ts",
    );
    expect(selection).toMatch(/attachMode/);
    expect(selection).toMatch(/checked: false/);
    expect(selection).toMatch(/export function pickLatestRule/);
    expect(selection).toMatch(/export function pickAttachRule/);
    expect(selection).toMatch(/approved \+ compiled/);
    expect(selection).toMatch(/not yet in the live bitmap/);
    expect(selection).toMatch(/export function recHasApprovedRule/);
    expect(selection).toMatch(/export function recHasCompiledRule/);
    expect(src).toMatch(/MAX_BRAINSTORM_RECOMMENDATIONS\s*=\s*5/);
    expect(src).toMatch(/Brainstorm can use at most/);
    expect(src).toMatch(/Kept \$\{MAX_BRAINSTORM_RECOMMENDATIONS\} of/);
    expect(src).toMatch(/approved rules preferred/);
    expect(src).toMatch(/>\s*Back\s*</);
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
    expect(variantsStep).toMatch(/Rule not compiled yet/);
    expect(variantsStep).toMatch(/Could not check rule/);
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
