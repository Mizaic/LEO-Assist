/**
 * VT-LEO-AI-521 -- Dry-run review-list highlighter + match
 * rationale chips (DI-LEO-AI-523).
 *
 * Static-source verification per ui-testing.mdc. Confirms the
 * /admin/training Candidates and Verified gold / Synthetic gold
 * sub-tabs route their search through the shared encounterRelevance
 * vocabulary (DI-LEO-AI-520, VT-LEO-AI-519), wrap each row title in
 * <HighlightedText>, render the same outlined "why this matched"
 * chip row used by the /care/encounters host and the /care/patients
 * drawer, and that GoldDatasetPanel forwards debouncedSearch to
 * both review lists.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const UI_SRC = path.join(ROOT, "services/ui/src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_SRC, rel), "utf-8");
}

describe("VT-LEO-AI-521 -- dry-run review-list shared search relevance", () => {
  const CANDIDATE_SRC = read(
    "components/gold-dataset/CandidateReviewList.tsx",
  );
  const GOLD_SRC = read("components/gold-dataset/GoldLabelReviewList.tsx");
  const PANEL_SRC = read("components/gold-dataset/GoldDatasetPanel.tsx");

  it("TC-001: CandidateReviewList wires the shared encounterRelevance utility", () => {
    expect(CANDIDATE_SRC).toMatch(
      /import\s+\{[\s\S]{0,200}computeMatchRationale[\s\S]{0,200}expandSearchTerms[\s\S]{0,200}\}\s+from\s+["']@\/components\/mission-control\/encounterRelevance["']/,
    );
    expect(CANDIDATE_SRC).toMatch(
      /type\s+MatchRationale[\s\S]{0,80}from\s+["']@\/components\/mission-control\/encounterRelevance["']/,
    );
    expect(CANDIDATE_SRC).toMatch(
      /import\s+\{[\s\S]{0,200}HighlightedText[\s\S]{0,80}collectHighlightTerms[\s\S]{0,80}\}\s+from\s+["']@\/components\/mission-control\/HighlightedText["']/,
    );
  });

  it("TC-002: CandidateReviewList exposes search prop and memoises expandedTerms", () => {
    expect(CANDIDATE_SRC).toMatch(/search\?:\s*string/);
    expect(CANDIDATE_SRC).toMatch(
      /const\s+expandedTerms\s*=\s*useMemo\(\s*[\s\S]{0,80}expandSearchTerms\(props\.search\)/,
    );
  });

  it("TC-003: CandidateReviewList wraps the row title in HighlightedText", () => {
    expect(CANDIDATE_SRC).toMatch(
      /matchRationale\s*=\s*computeMatchRationale\(candidate\.text,\s*expandedTerms\)/,
    );
    expect(CANDIDATE_SRC).toMatch(
      /highlightTerms\s*=\s*collectHighlightTerms\(\s*search,\s*matchRationale\.hitTerms,?\s*\)/,
    );
    expect(CANDIDATE_SRC).toMatch(
      /title:[\s\S]{0,200}highlightTerms\.length\s*>\s*0[\s\S]{0,200}<HighlightedText[\s\S]{0,200}testId="candidate-row-highlight"/,
    );
  });

  it("TC-004: CandidateReviewList renders the rationale chip row capped at 4", () => {
    expect(CANDIDATE_SRC).toMatch(
      /function\s+renderRationaleChips[\s\S]{0,400}expandedTerms\.length\s*===\s*0\s*\|\|\s*rationale\.hitTerms\.length\s*===\s*0[\s\S]{0,80}return\s+null/,
    );
    expect(CANDIDATE_SRC).toMatch(
      /data-testid="candidate-row-match-rationale"/,
    );
    expect(CANDIDATE_SRC).toMatch(
      /rationale\.hitTerms\.slice\(0,\s*4\)\.map/,
    );
    expect(CANDIDATE_SRC).toMatch(
      /data-testid="candidate-row-match-rationale-chip"/,
    );
  });

  it("TC-005: GoldLabelReviewList mirrors the wiring for verified / synthetic rows", () => {
    expect(GOLD_SRC).toMatch(
      /import\s+\{[\s\S]{0,200}computeMatchRationale[\s\S]{0,200}expandSearchTerms[\s\S]{0,200}\}\s+from\s+["']@\/components\/mission-control\/encounterRelevance["']/,
    );
    expect(GOLD_SRC).toMatch(
      /import\s+\{[\s\S]{0,200}HighlightedText[\s\S]{0,80}collectHighlightTerms[\s\S]{0,80}\}\s+from\s+["']@\/components\/mission-control\/HighlightedText["']/,
    );
    expect(GOLD_SRC).toMatch(/search\?:\s*string/);
    expect(GOLD_SRC).toMatch(
      /const\s+expandedTerms\s*=\s*useMemo\(\s*[\s\S]{0,80}expandSearchTerms\(props\.search\)/,
    );
    expect(GOLD_SRC).toMatch(
      /matchRationale\s*=\s*computeMatchRationale\(item\.text,\s*expandedTerms\)/,
    );
    expect(GOLD_SRC).toMatch(
      /<HighlightedText[\s\S]{0,200}testId="candidate-row-highlight"/,
    );
    expect(GOLD_SRC).toMatch(/data-testid="candidate-row-match-rationale"/);
    expect(GOLD_SRC).toMatch(
      /data-testid="candidate-row-match-rationale-chip"/,
    );
    expect(GOLD_SRC).toMatch(/rationale\.hitTerms\.slice\(0,\s*4\)\.map/);
  });

  it("TC-006: GoldDatasetPanel forwards debouncedSearch to both review lists", () => {
    expect(PANEL_SRC).toMatch(
      /<CandidateReviewList[\s\S]{0,800}search=\{debouncedSearch\}/,
    );
    expect(PANEL_SRC).toMatch(
      /<GoldLabelReviewList[\s\S]{0,800}search=\{debouncedSearch\}/,
    );
  });

  it("TC-007: rationale chip token matches the drawer (height 20, fontSize 0.65rem, outlined)", () => {
    // The chip element renders variant -> testid -> sx in that order in
    // both review lists. We anchor on the testid because it is unique
    // and assert that variant + sx tokens flank it within a small window
    // so a future drift to a different chip variant or visual token
    // breaks the test.
    const tokenPattern =
      /variant="outlined"[\s\S]{0,200}data-testid="candidate-row-match-rationale-chip"[\s\S]{0,200}height:\s*20[\s\S]{0,80}fontSize:\s*"0\.65rem"/;
    expect(CANDIDATE_SRC).toMatch(tokenPattern);
    expect(GOLD_SRC).toMatch(tokenPattern);
  });
});
