/**
 * Static-source VT for ordered_tests analyte editor in FormSchemaSectionEditor.
 *
 * Verifies:
 *   - ordered_tests section type renders analyte sub-list editor.
 *   - Other section types render the simple pattern / entity-text editor.
 *   - Procedure SNOMED uses async SNOMED lookup (not manual TextField).
 *   - Analyte SNOMED uses observable-filtered lookup.
 *   - searchTerms calls terminology API with semantic_tag filters.
 *   - Analyte row fields (label, display) are present.
 *   - Add analyte and Remove analyte controls are accessible.
 *
 * Atlas trace: DI-5C9CA57B
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readComponent(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const EDITOR_PATH =
  "services/ui/src/components/operations/FormSchemaSectionEditor.tsx";
const LOOKUP_PATH = "services/ui/src/components/SnomedLookupField.tsx";
const TYPES_PATH =
  "services/ui/src/components/operations/formSchemaDetector.ts";

describe("FormSchemaSectionEditor -- ordered_tests analyte editor", () => {
  const src = readComponent(EDITOR_PATH);
  const types = readComponent(TYPES_PATH);

  test("TC-001: ordered_tests is in the expanded item section types list", () => {
    expect(src).toMatch(/ITEM_SECTION_TYPES[\s\S]*?"ordered_tests"/);
  });

  test("TC-002: OrderedTestsItemEditor component is defined", () => {
    expect(src).toMatch(/function OrderedTestsItemEditor/);
  });

  test("TC-003: section_type ordered_tests branches to OrderedTestsItemEditor", () => {
    expect(src).toMatch(
      /section\.section_type\s*===\s*["']ordered_tests["'][\s\S]*?OrderedTestsItemEditor/,
    );
  });

  test("TC-004: other section types still use ItemRow", () => {
    expect(src).toMatch(/function ItemRow/);
  });

  test("TC-005: Procedure SNOMED uses SnomedLookupField with procedure filter", () => {
    expect(src).toMatch(/SnomedLookupField/);
    expect(src).toMatch(/semanticTags=\{\["procedure"\]\}/);
    expect(src).toMatch(/testId="procedure-snomed-lookup"/);
    expect(src).toMatch(/procedure_snomed/);
    expect(src).toMatch(/procedure_display/);
    expect(src).not.toMatch(/label="Procedure SNOMED code"/);
  });

  test("TC-005b: SnomedLookupField calls searchTerms on terminology API", () => {
    const lookup = readComponent(LOOKUP_PATH);
    expect(lookup).toMatch(/searchTerms/);
    expect(lookup).toMatch(/semanticTags/);
    expect(lookup).toMatch(/Autocomplete/);
    const legacy = readComponent("services/ui/src/lib/api/legacy.ts");
    expect(legacy).toMatch(/\/api\/terminology\/search/);
  });

  test("TC-005c: Analyte SNOMED uses observable-filtered SnomedLookupField", () => {
    expect(src).toMatch(/semanticTags=\{\["observable"\]\}/);
    expect(src).toMatch(/testId="analyte-snomed-lookup"/);
    expect(src).toMatch(/snomed_code/);
    expect(src).not.toMatch(/label="SNOMED code"/);
  });

  test("TC-006: analyte row data-testid is present for accessibility", () => {
    expect(src).toMatch(/data-testid="analyte-row"/);
  });

  test("TC-007: Add analyte button exists", () => {
    expect(src).toMatch(/Add analyte/);
  });

  test("TC-008: Remove analyte button has aria-label", () => {
    expect(src).toMatch(/aria-label="Remove analyte"/);
  });

  test("TC-009: AnalyteEntry type is exported from formSchemaDetector", () => {
    expect(types).toMatch(/export interface AnalyteEntry/);
    expect(types).toMatch(/label:\s*string/);
    expect(types).toMatch(/snomed_code:\s*string/);
    expect(types).toMatch(/display:\s*string/);
  });

  test("TC-010: FormSchemaItem has optional analyte enrichment fields", () => {
    expect(types).toMatch(/procedure_snomed\?:\s*string/);
    expect(types).toMatch(/procedure_display\?:\s*string/);
    expect(types).toMatch(/analytes\?:\s*AnalyteEntry\[\]/);
    expect(types).toMatch(/value_placeholder\?:\s*string/);
  });
});
