/**
 * VT -- extraction quality review card and letter editor.
 *
 * Atlas: DI-4A012A59 / VT-CE7006EE
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("extraction quality review chrome", () => {
  test("TC-001: Operations card asks the reviewer to check draft facts", () => {
    const src = readFile(
      "services/ui/src/components/operations/ReviewCard.tsx",
    );
    expect(src).toMatch(/extraction_quality_review/);
    expect(src).toMatch(/Check the draft facts/);
  });

  test("TC-002: card opens the letter editor instead of generic approve", () => {
    const card = readFile(
      "services/ui/src/components/operations/ReviewCard.tsx",
    );
    const actions = readFile(
      "services/ui/src/components/operations/HitlActions.tsx",
    );
    const section = readFile(
      "services/ui/src/components/operations/ReviewSection.tsx",
    );
    expect(card + actions).toMatch(/Open letter/);
    expect(actions).toMatch(/extraction_quality_review/);
    expect(section).toMatch(/ExtractionQualityReviewDialog/);
  });

  test("TC-003: letter editor reuses Validation Lab highlight and complete API", () => {
    const dialog = readFile(
      "services/ui/src/components/operations/ExtractionQualityReviewDialog.tsx",
    );
    expect(dialog).toMatch(/LetterMarkdownView/);
    expect(dialog).toMatch(/extraction-reviews\/complete/);
    expect(dialog).toMatch(/Unlock referral/);
  });
});
