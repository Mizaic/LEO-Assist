/**
 * Static-source VT -- BorrowedFromBadge surfacing in FormSchemaSectionEditor.
 *
 * Asserts:
 *   - borrowed_from field is present in the FormSchemaSection type definition
 *   - badge renders confidence as a percentage
 *   - dismiss callback clears borrowed_from on the section
 *   - Mizaic violet colour is used
 *   - Tooltip carries full provenance text
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("form-schema-borrowed-badge", () => {
  test("TC-001: borrowed_from field exists in FormSchemaSection type", () => {
    const src = readFile(
      "services/ui/src/components/operations/formSchemaDetector.ts",
    );
    expect(src).toMatch(/borrowed_from\?/);
    expect(src).toMatch(/org:\s*string/);
    expect(src).toMatch(/service:\s*string/);
    expect(src).toMatch(/form_name:\s*string/);
    expect(src).toMatch(/confidence:\s*number/);
  });

  test("TC-002: badge computes confidence as percentage using Math.round", () => {
    const src = readFile(
      "services/ui/src/components/operations/BorrowedFromBadge.tsx",
    );
    expect(src).toMatch(/Math\.round[\s\S]*?confidence\s*\*\s*100/);
    expect(src).toMatch(/%/);
  });

  test("TC-003: dismiss callback clears borrowed_from on the section", () => {
    const badge = readFile(
      "services/ui/src/components/operations/BorrowedFromBadge.tsx",
    );
    expect(badge).toMatch(/onDismiss/);

    const editor = readFile(
      "services/ui/src/components/operations/FormSchemaSectionEditor.tsx",
    );
    expect(editor).toMatch(/borrowed_from:\s*undefined/);
    expect(editor).toMatch(/onDismiss/);
  });

  test("TC-004: badge uses Mizaic violet #9338ff background", () => {
    const src = readFile(
      "services/ui/src/components/operations/BorrowedFromBadge.tsx",
    );
    expect(src).toMatch(/#9338ff/i);
  });

  test("TC-005: badge wraps in MUI Tooltip with provenance copy", () => {
    const src = readFile(
      "services/ui/src/components/operations/BorrowedFromBadge.tsx",
    );
    expect(src).toMatch(/Tooltip/);
    expect(src).toMatch(/Pre-filled from/);
    expect(src).toMatch(/Review and save to confirm/);
  });

  test("TC-006: editor imports BorrowedFromBadge component", () => {
    const src = readFile(
      "services/ui/src/components/operations/FormSchemaSectionEditor.tsx",
    );
    expect(src).toMatch(/import[\s\S]*?BorrowedFromBadge[\s\S]*?from/);
  });

  test("TC-007: badge is rendered conditionally on section.borrowed_from", () => {
    const src = readFile(
      "services/ui/src/components/operations/FormSchemaSectionEditor.tsx",
    );
    expect(src).toMatch(/section\.borrowed_from/);
    expect(src).toMatch(/<BorrowedFromBadge/);
  });
});
