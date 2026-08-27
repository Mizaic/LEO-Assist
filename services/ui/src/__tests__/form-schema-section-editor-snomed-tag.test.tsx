/**
 * Static-source VT: FormSchemaSectionEditor SNOMED tag multi-select.
 *
 * Verifies:
 *   - SECTION_TYPE_SNOMED_TAG is exported with array defaults
 *   - The Autocomplete (multiple) multi-select is used instead of a plain Chip
 *   - The label "SNOMED tags" is present
 *   - data-testid="snomed-tag-chip" is retained for accessibility tooling
 *   - The section carries semantic_tags (plural) not semantic_tag (singular)
 *   - The TypeScript interface uses semantic_tags: string[]
 *
 * Atlas trace: DI-5C9CA57B
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const SECTION_EDITOR_PATH =
  "services/ui/src/components/operations/FormSchemaSectionEditor.tsx";
const DETECTOR_PATH =
  "services/ui/src/components/operations/formSchemaDetector.ts";

describe("FormSchemaSectionEditor - SNOMED multi-select tags", () => {
  let src: string;
  let detectorSrc: string;

  beforeAll(() => {
    src = readFile(SECTION_EDITOR_PATH);
    detectorSrc = readFile(DETECTOR_PATH);
  });

  test("TC-001: SECTION_TYPE_SNOMED_TAG is exported", () => {
    expect(src).toMatch(/export\s+const\s+SECTION_TYPE_SNOMED_TAG/);
  });

  test("TC-002: Autocomplete with multiple prop replaces read-only chip", () => {
    expect(src).toMatch(/Autocomplete/);
    expect(src).toMatch(/multiple/);
  });

  test("TC-003: SNOMED tags label is present", () => {
    expect(src).toMatch(/SNOMED tags/i);
  });

  test("TC-004: data-testid snomed-tag-chip is retained for tooling", () => {
    expect(src).toMatch(/data-testid="snomed-tag-chip"/);
  });

  test("TC-005: admin maps to array with none tag", () => {
    const block = src.match(/SECTION_TYPE_SNOMED_TAG[\s\S]*?admin:[\s\S]*?\]/);
    expect(block?.[0]).toMatch(/none/i);
  });

  test("TC-006: section model uses semantic_tags (plural) in onPatch call", () => {
    expect(src).toMatch(/semantic_tags/);
  });

  test("TC-007: FormSchemaSection interface declares semantic_tags as array", () => {
    expect(detectorSrc).toMatch(/semantic_tags\??:\s*string\[\]/);
  });

  test("TC-008: SECTION_TYPE_SNOMED_TAG values are arrays not plain strings", () => {
    const block = src.match(
      /SECTION_TYPE_SNOMED_TAG[\s\S]*?=\s*\{[\s\S]*?\}/
    );
    expect(block).not.toBeNull();
    const blockStr = block![0];
    expect(blockStr).toMatch(/\[/);
  });
});
