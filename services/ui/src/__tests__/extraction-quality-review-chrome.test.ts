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

  test("TC-004: My work opens the letter editor in a modal for paused extractions", () => {
    const workPage = readFile("services/ui/src/app/work/page.tsx");
    const dialog = readFile("services/ui/src/app/work/WorkTaskDialog.tsx");
    expect(workPage).toMatch(/WorkTaskDialog/);
    expect(dialog).toMatch(/extraction_quality_pause/);
    expect(dialog).toMatch(/ExtractionQualityReviewDialog/);
    expect(dialog).toMatch(/Approve and unlock|taskId/);
  });

  test("TC-003: letter editor reuses Validation Lab highlight and complete API", () => {
    const dialog = readFile(
      "services/ui/src/components/operations/ExtractionQualityReviewDialog.tsx",
    );
    expect(dialog).toMatch(/LetterMarkdownView/);
    expect(dialog).toMatch(/extraction-reviews\/complete/);
    expect(dialog).toMatch(/Approve and unlock/);
  });

  test("TC-005: pause reasons use plain English once, not raw tokens", () => {
    const copy = readFile(
      "services/ui/src/components/operations/extractionReviewCopy.ts",
    );
    const dialog = readFile(
      "services/ui/src/components/operations/ExtractionQualityReviewDialog.tsx",
    );
    const facts = readFile(
      "services/ui/src/components/operations/ExtractionReviewFacts.tsx",
    );
    expect(copy).toMatch(/This letter layout is unlike the training examples/);
    expect(copy).toMatch(/This form is not one we have seen before/);
    expect(copy).toMatch(/wrapper, not the clinical form/);
    expect(dialog).toMatch(/pauseReasonLabels/);
    expect(facts).not.toMatch(/Why this referral paused/);
  });

  test("TC-006: empty letter does not ask the reviewer to select text", () => {
    const dialog = readFile(
      "services/ui/src/components/operations/ExtractionQualityReviewDialog.tsx",
    );
    const copy = readFile(
      "services/ui/src/components/operations/extractionReviewCopy.ts",
    );
    expect(dialog).toMatch(/hasLetter/);
    expect(copy).toMatch(/We could not load the letter/);
    expect(dialog).not.toMatch(/No letter text available for this task/);
  });

  test("TC-007: selected fact is the only letter highlight and mentions are numbered", () => {
    const dialog = readFile(
      "services/ui/src/components/operations/ExtractionQualityReviewDialog.tsx",
    );
    const facts = readFile(
      "services/ui/src/components/operations/ExtractionReviewFacts.tsx",
    );
    const highlight = readFile(
      "services/ui/src/components/operations/extractionReviewHighlight.ts",
    );
    const marks = readFile(
      "services/ui/src/app/admin/validation-lab/LetterMarks.tsx",
    );
    expect(dialog).toMatch(/focusedReviewMarks/);
    expect(dialog).toMatch(/focusTerm/);
    expect(facts).toMatch(/mentionCopy/);
    expect(highlight).toMatch(/countMentions/);
    expect(marks).toMatch(/data-mention-index/);
  });

  test("TC-008: engineer debug does not dump the whole letter", () => {
    const panes = readFile("services/ui/src/app/work/EngineerPanes.tsx");
    expect(panes).toMatch(/See the letter on the left/);
    expect(panes).toMatch(/debugLetterSample/);
  });

  test("TC-009: selected fact can Ask LEO before a tag is applied", () => {
    const facts = readFile(
      "services/ui/src/components/operations/ExtractionReviewFacts.tsx",
    );
    const ask = readFile(
      "services/ui/src/components/operations/ExtractionReviewAskLeo.tsx",
    );
    expect(facts).toMatch(/ExtractionReviewAskLeo/);
    expect(ask).toMatch(/askLeoSmart/);
    expect(ask).toMatch(/Use this tag/);
    expect(ask).toMatch(/Ask LEO/);
  });
});
