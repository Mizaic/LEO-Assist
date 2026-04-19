/**
 * VT-LEO-AI-525 -- Similar-candidates batch dialog highlighter +
 * match rationale chips (DI-LEO-AI-527).
 *
 * Static-source verification per ui-testing.mdc. Confirms the
 * SimilarCandidatesBatch dialog (opened from the dry-run review queue
 * after a row is marked as gold) wraps each row's encounter text in
 * the shared <HighlightedText> primitive and renders the same outlined
 * "why this matched" chip row used by /care/encounters, the patient
 * drawer, and the dry-run review queue, and that GoldDatasetPanel
 * forwards debouncedSearch into the dialog.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-525 -- similar-candidates dialog shared search relevance", () => {
  const DIALOG_SRC = read(
    "components/gold-dataset/SimilarCandidatesBatch.tsx",
  );
  const PANEL_SRC = read("components/gold-dataset/GoldDatasetPanel.tsx");

  it("TC-001: imports the shared encounterRelevance + HighlightedText helpers", () => {
    expect(DIALOG_SRC).toMatch(
      /import\s+\{[\s\S]{0,200}computeMatchRationale[\s\S]{0,200}expandSearchTerms[\s\S]{0,200}\}\s+from\s+["']@\/components\/mission-control\/encounterRelevance["']/,
    );
    expect(DIALOG_SRC).toMatch(
      /import\s+\{[\s\S]{0,200}HighlightedText[\s\S]{0,80}collectHighlightTerms[\s\S]{0,80}\}\s+from\s+["']@\/components\/mission-control\/HighlightedText["']/,
    );
  });

  it("TC-002: declares an optional `search` prop and memoises the expanded terms", () => {
    expect(DIALOG_SRC).toMatch(/search\?\s*:\s*string/);
    expect(DIALOG_SRC).toMatch(
      /const\s+expandedTerms\s*=\s*useMemo\(\s*\(\)\s*=>\s*expandSearchTerms\(\s*search\s*\)\s*,\s*\[\s*search\s*\]\s*\)/,
    );
  });

  it("TC-003: computes per-row match rationale + highlight terms", () => {
    expect(DIALOG_SRC).toMatch(
      /const\s+matchRationale\s*=\s*computeMatchRationale\(\s*item\.text\s*,\s*expandedTerms\s*,?\s*\)/,
    );
    expect(DIALOG_SRC).toMatch(
      /const\s+highlightTerms\s*=\s*collectHighlightTerms\(\s*search\s*,\s*matchRationale\.hitTerms\s*,?\s*\)/,
    );
  });

  it("TC-004: wraps the row text in <HighlightedText> when terms hit", () => {
    expect(DIALOG_SRC).toMatch(
      /highlightTerms\.length\s*>\s*0\s*\?\s*\(\s*<HighlightedText[\s\S]{0,400}testId=["']similar-candidate-row-highlight["']/,
    );
  });

  it("TC-005: renders the rationale chip row when at least one expanded term hits", () => {
    expect(DIALOG_SRC).toMatch(
      /data-testid=["']similar-candidate-row-match-rationale["']/,
    );
    expect(DIALOG_SRC).toMatch(
      /matchRationale\.hitTerms\.slice\(\s*0\s*,\s*4\s*\)\.map/,
    );
    expect(DIALOG_SRC).toMatch(
      /data-testid=["']similar-candidate-row-match-rationale-chip["']/,
    );
    expect(DIALOG_SRC).toMatch(
      /variant=["']outlined["'][\s\S]{0,200}height:\s*20[\s\S]{0,80}fontSize:\s*["']0\.65rem["']/,
    );
  });

  it("TC-006: only shows the rationale block when both expanded terms and hits exist", () => {
    expect(DIALOG_SRC).toMatch(
      /const\s+showRationale\s*=\s*expandedTerms\.length\s*>\s*0\s*&&\s*matchRationale\.hitTerms\.length\s*>\s*0/,
    );
    expect(DIALOG_SRC).toMatch(
      /\{\s*showRationale\s*&&\s*\(/,
    );
  });

  it("TC-007: GoldDatasetPanel forwards debouncedSearch into the dialog", () => {
    expect(PANEL_SRC).toMatch(
      /<SimilarCandidatesBatch[\s\S]{0,800}search=\{\s*debouncedSearch\s*\}/,
    );
  });
});
