/**
 * Static-source verification that the footer Save button relabels to
 * "Approve and save" on the Save step, and only on the Save step --
 * per the Phase B 3-column Save review redesign (Approve/Back).
 *
 * Atlas: DI-LEO-AI-234 / DO-LEO-AI-234 / VT-LEO-AI-510
 */
import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../../../../../..");

function read(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const INDEX_SRC = read("services/ui/src/app/admin/guidance/EditRuleDialog/index.tsx");

describe("EditRuleDialog Save button label", () => {
  test("relabels to 'Approve and save' when currentStepId === 'save'", () => {
    expect(INDEX_SRC).toMatch(
      /currentStepId === ["']save["']\s*\?\s*["']Approve and save["']\s*:\s*["']Save changes["']/,
    );
  });

  test("the ternary sits inside the single footer Save button, not a second button", () => {
    const buttonStart = INDEX_SRC.indexOf('aria-label="Save your changes"');
    const buttonEnd = INDEX_SRC.indexOf("</Button>", buttonStart);
    const buttonMarkup = INDEX_SRC.slice(buttonStart, buttonEnd);
    expect(buttonMarkup).toMatch(/Approve and save/);
    expect(buttonMarkup).toMatch(/Save changes/);
    // Only one Save button in the footer -- this is the ternary, not two buttons.
    expect(INDEX_SRC.match(/aria-label="Save your changes"/g)).toHaveLength(1);
  });

  test("earlier steps still read 'Save changes', never 'Approve' prematurely", () => {
    // The ternary's false-branch (non-save steps) must be the plain label.
    const ternaryMatch = INDEX_SRC.match(
      /currentStepId === ["']save["']\s*\?\s*["']Approve and save["']\s*:\s*["'](Save changes)["']/,
    );
    expect(ternaryMatch?.[1]).toBe("Save changes");
  });
});

describe("EditRuleDialog wires the NICE source text into the Save-step review", () => {
  test("recommendationText is passed to LivePreviewPane from rule.recommendation_text", () => {
    const callStart = INDEX_SRC.indexOf("<LivePreviewPane");
    const callEnd = INDEX_SRC.indexOf("/>", callStart);
    const callMarkup = INDEX_SRC.slice(callStart, callEnd);
    expect(callMarkup).toMatch(/recommendationText=\{rule\?\.recommendation_text\}/);
  });
});
