/**
 * Static-source VT: FormSchemaCompletenessEditor SNOMED wiring.
 *
 * Verifies:
 *   - SnomedLookupField is imported for concept search
 *   - hasNoCodes is exported and used
 *   - warning Alert is shown when a group has no codes
 *   - member list replaces comma-separated option text
 *   - if-then arms each have a SNOMED lookup
 *
 * Atlas trace: UN-3B25A20E, DI-A0E69E38
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const EDITOR_PATH =
  "services/ui/src/components/operations/FormSchemaCompletenessEditor.tsx";
const SEED_PATH =
  "services/ui/src/components/operations/formSchemaCompletenessSeed.ts";

describe("FormSchemaCompletenessEditor - SNOMED concept picker", () => {
  let src: string;
  let seedSrc: string;

  beforeAll(() => {
    src = readFile(EDITOR_PATH);
    seedSrc = readFile(SEED_PATH);
  });

  test("TC-001: imports SnomedLookupField", () => {
    expect(src).toMatch(/SnomedLookupField/);
    expect(src).toMatch(/from\s+["']@\/components\/SnomedLookupField["']/);
  });

  test("TC-002: exports hasNoCodes", () => {
    expect(src).toMatch(/export\s+function\s+hasNoCodes/);
  });

  test("TC-003: warning Alert is present when a group has no codes", () => {
    expect(src).toMatch(/hasNoCodes\(group\)/);
    expect(src).toMatch(/severity="warning"/);
    expect(src).toMatch(/data-testid="completeness-no-codes"/);
    expect(src).toMatch(/cannot match extracted facts/);
  });

  test("TC-004: member list uses named options not comma-separated text", () => {
    expect(src).toMatch(/completeness-member-list/);
    expect(src).toMatch(/Add option/);
    expect(src).not.toMatch(/comma separated/i);
  });

  test("TC-005: if-then arms each have a SNOMED lookup", () => {
    expect(src).toMatch(/if-arm-snomed/);
    expect(src).toMatch(/then-arm-snomed/);
  });

  test("TC-006: seed does not hardcode cervix or section B concept ids", () => {
    expect(seedSrc).not.toMatch(/363354003/);
    expect(seedSrc).not.toMatch(/b1:\s*\[/);
    expect(seedSrc).toMatch(/75367002/);
    expect(seedSrc).toMatch(/364075005/);
  });
});
