/**
 * Static-source verification test for the Results/Labs knowledge tab.
 *
 * Verifies:
 *   - Tab registration and proxy wiring are intact.
 *   - LabResultsPanel uses @leo/design-system primitives (StatHero,
 *     FilterBar, DataGridCard, ToolbarActions).
 *   - Legacy raw-MUI chrome (Card/CardContent) has been removed.
 *   - All three detail sub-tabs (Unit conversions, Reference ranges,
 *     Interpretation SNOMED) are present in the component tree.
 *   - Delete capability is present and ConfirmDialog-gated.
 *   - Add observable flow is present (AddObservableDialog).
 *   - Select components replace free-text fields for sex and classification.
 */

import { readFileSync } from "fs";
import { resolve } from "path";

const ROOT = resolve(__dirname, "../../../..");

function read(relPath: string): string {
  return readFileSync(resolve(ROOT, relPath), "utf8");
}

describe("Results/Labs Knowledge tab -- design-system chrome", () => {
  it("TC-001: registers the tab and API proxy", () => {
    const knowledgePage = read("services/ui/src/app/admin/knowledge/page.tsx");
    const proxy = read("services/ui/src/proxy.ts");

    expect(knowledgePage).toMatch(/"results-labs"/);
    expect(knowledgePage).toMatch(/admin\/lab-results\/page/);
    expect(proxy).toMatch(/\/api\/lab-result-configs/);
  });

  it("TC-002: LabResultsPanel imports @leo/design-system primitives", () => {
    const src = read("services/ui/src/app/admin/lab-results/LabResultsPanel.tsx");

    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/StatHero/);
    expect(src).toMatch(/FilterBar/);
    expect(src).toMatch(/DataGridCard/);
    expect(src).toMatch(/ToolbarActions/);
  });

  it("TC-003: legacy card chrome removed from LabResultsPanel", () => {
    const src = read("services/ui/src/app/admin/lab-results/LabResultsPanel.tsx");

    expect(src).not.toMatch(/import\s+Card\s+from\s+["']@mui\/material\/Card["']/);
    expect(src).not.toMatch(/import\s+CardContent\s+from/);
    expect(src).not.toMatch(/<CardContent/);
  });

  it("TC-004: unit conversions tab is present", () => {
    const detail = read(
      "services/ui/src/app/admin/lab-results/ObservableDetailPanel.tsx",
    );
    const tab =
      read("services/ui/src/app/admin/lab-results/ConversionsTab.tsx") +
      read("services/ui/src/app/admin/lab-results/useConversionsTab.ts") +
      read("services/ui/src/app/admin/lab-results/labConfigForm.tsx");

    expect(detail).toMatch(/Unit conversions/);
    expect(tab).toMatch(/saveUnitConversion/);
    expect(tab).toMatch(/deleteUnitConversion/);
    expect(tab).toMatch(/gridTemplateColumns/);
    expect(tab).toMatch(/Add this conversion\?/);
    expect(tab).not.toMatch(/flexWrap="wrap"/);
  });

  it("TC-005: reference ranges tab is present with Select for sex", () => {
    const detail = read(
      "services/ui/src/app/admin/lab-results/ObservableDetailPanel.tsx",
    );
    const tab =
      read("services/ui/src/app/admin/lab-results/RangesTab.tsx") +
      read("services/ui/src/app/admin/lab-results/RangeFormCard.tsx") +
      read("services/ui/src/app/admin/lab-results/RangeOwnerField.tsx") +
      read("services/ui/src/app/admin/lab-results/useRangesTab.ts") +
      read("services/ui/src/app/admin/lab-results/rangeDraft.ts") +
      read("services/ui/src/app/admin/lab-results/labConfigForm.tsx");

    expect(detail).toMatch(/Reference ranges/);
    expect(tab).toMatch(/saveReferenceRange/);
    expect(tab).toMatch(/deleteReferenceRange/);
    expect(tab).toMatch(/Select/);
    expect(tab).toMatch(/male/);
    expect(tab).toMatch(/female/);
    expect(tab).toMatch(/gridTemplateColumns: "minmax\(0, 1fr\) minmax\(0, 1fr\)"/);
    expect(tab).toMatch(/Who it applies to/);
    expect(tab).toMatch(/Add this reference range\?/);
    expect(tab).toMatch(/Platform default/);
    expect(tab).toMatch(/listOrgs/);
    expect(tab).toMatch(/Owner/);
    expect(tab).toMatch(/Autocomplete/);
    expect(tab).toMatch(/Type a name or ODS code/);
    expect(tab).toMatch(/filterRangeOrgs/);
    expect(tab).toMatch(/This overlay applies only to the chosen organisation/);
    expect(tab).not.toMatch(/orgs\.map\(\(org\) =>/);
    expect(tab).not.toMatch(/flexWrap="wrap"/);
  });

  it("TC-006: interpretations tab uses Select for classification", () => {
    const detail = read(
      "services/ui/src/app/admin/lab-results/ObservableDetailPanel.tsx",
    );
    const tab = read("services/ui/src/app/admin/lab-results/InterpretationsTab.tsx");

    expect(detail).toMatch(/Interpretations/);
    expect(tab).toMatch(/saveInterpretation/);
    expect(tab).toMatch(/deleteInterpretation/);
    expect(tab).toMatch(/Select/);
    expect(tab).toMatch(/critically_high/);
    expect(tab).toMatch(/critically_low/);
    expect(tab).toMatch(/out_of_range/);
    expect(tab).toMatch(/value:\s*"normal"/);
    expect(tab).toMatch(/Within range/);
    expect(tab).toMatch(/finding_concept_id/);
    expect(tab).toMatch(/FindingSnomedPicker/);
    expect(tab).toMatch(/Ask LEO/);
    expect(tab).toMatch(/Search SNOMED/);
    expect(tab).toMatch(/SnomedPickConfirmDialog/);
    expect(tab).toMatch(/Save this interpretation\?/);
    expect(tab).not.toMatch(/id: "add-interpretation"/);
  });

  it("TC-011: interpretation and add-observable pickers search SNOMED or Ask LEO", () => {
    const picker = read(
      "services/ui/src/app/admin/lab-results/FindingSnomedPicker.tsx",
    );
    const hook = read(
      "services/ui/src/app/admin/lab-results/useLabSnomedSearch.ts",
    );
    const add = read(
      "services/ui/src/app/admin/lab-results/AddObservableDialog.tsx",
    );

    expect(picker).toMatch(/Ask LEO/);
    expect(picker).toMatch(/data-testid="lab-snomed-empty"/);
    expect(hook).toMatch(/askLeoSmart/);
    expect(hook).toMatch(/searchTerms/);
    expect(add).toMatch(/FindingSnomedPicker/);
    expect(add).toMatch(/SnomedPickConfirmDialog/);
    expect(add).toMatch(/Add this observable\?/);
    expect(add).not.toMatch(/Observable SNOMED code/);
  });

  it("TC-007: all delete operations are ConfirmDialog-gated", () => {
    const conversions = read(
      "services/ui/src/app/admin/lab-results/ConversionsTab.tsx",
    );
    const ranges = read("services/ui/src/app/admin/lab-results/RangesTab.tsx");
    const interpretations = read(
      "services/ui/src/app/admin/lab-results/InterpretationsTab.tsx",
    );

    expect(conversions).toMatch(/ConfirmDialog/);
    expect(ranges).toMatch(/ConfirmDialog/);
    expect(interpretations).toMatch(/ConfirmDialog/);
  });

  it("TC-008: Add observable dialog is present as a distinct component", () => {
    const panel = read("services/ui/src/app/admin/lab-results/LabResultsPanel.tsx");
    const dialog = read(
      "services/ui/src/app/admin/lab-results/AddObservableDialog.tsx",
    );

    expect(panel).toMatch(/AddObservableDialog/);
    expect(dialog).toMatch(/saveLabResultConfig/);
    expect(dialog).toMatch(/add-observable-title/);
  });

  it("TC-009: api.ts exposes delete endpoints for all three child types", () => {
    const api = read("services/ui/src/app/admin/lab-results/api.ts");

    expect(api).toMatch(/deleteUnitConversion/);
    expect(api).toMatch(/deleteReferenceRange/);
    expect(api).toMatch(/deleteInterpretation/);
    expect(api).toMatch(/method.*DELETE/);
  });

  it("TC-010: LabResultConfigSummary includes coverage count fields", () => {
    const types = read("services/ui/src/app/admin/lab-results/types.ts");

    expect(types).toMatch(/conversion_count/);
    expect(types).toMatch(/range_count/);
    expect(types).toMatch(/interpretation_count/);
  });
});
