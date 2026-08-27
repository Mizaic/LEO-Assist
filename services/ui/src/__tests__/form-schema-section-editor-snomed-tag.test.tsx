/**
 * Static-source VT: FormSchemaSectionEditor SNOMED tag chip.
 *
 * Verifies:
 *   - SECTION_TYPE_SNOMED_TAG is exported with the correct defaults
 *   - The Chip with data-testid="snomed-tag-chip" is present in the source
 *   - The chip label references SECTION_TYPE_SNOMED_TAG
 *   - The chip has an aria-label for accessibility
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

describe("FormSchemaSectionEditor - SNOMED tag chip", () => {
  let src: string;

  beforeAll(() => {
    src = readFile(SECTION_EDITOR_PATH);
  });

  test("TC-001: SECTION_TYPE_SNOMED_TAG is exported", () => {
    expect(src).toMatch(/export\s+const\s+SECTION_TYPE_SNOMED_TAG/);
  });

  test("TC-002: snomed-tag-chip data-testid is present in source", () => {
    expect(src).toMatch(/data-testid="snomed-tag-chip"/);
  });

  test("TC-003: chip label references SECTION_TYPE_SNOMED_TAG", () => {
    expect(src).toMatch(/SECTION_TYPE_SNOMED_TAG\[section\.section_type\]/);
  });

  test("TC-004: chip has an aria-label for accessibility", () => {
    expect(src).toMatch(/aria-label=\{`SNOMED tag:/);
  });

  test("TC-005: admin maps to None in SECTION_TYPE_SNOMED_TAG", () => {
    const match = src.match(
      /SECTION_TYPE_SNOMED_TAG[\s\S]*?admin:\s*["']([^"']+)["']/
    );
    expect(match?.[1]).toBe("None");
  });

  test("TC-006: checkbox_single maps to Situation", () => {
    const match = src.match(
      /SECTION_TYPE_SNOMED_TAG[\s\S]*?checkbox_single:\s*["']([^"']+)["']/
    );
    expect(match?.[1]).toBe("Situation");
  });

  test("TC-007: scale maps to Observable", () => {
    const match = src.match(
      /SECTION_TYPE_SNOMED_TAG[\s\S]*?scale:\s*["']([^"']+)["']/
    );
    expect(match?.[1]).toBe("Observable");
  });

  test("TC-008: ordered_tests maps to Procedure", () => {
    const match = src.match(
      /SECTION_TYPE_SNOMED_TAG[\s\S]*?ordered_tests:\s*["']([^"']+)["']/
    );
    expect(match?.[1]).toBe("Procedure");
  });
});
