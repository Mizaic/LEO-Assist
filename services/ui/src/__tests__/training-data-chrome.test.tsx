/**
 * VT-LEO-AI-142 -- Wave E Phase 2a
 *
 * Verifies that the chrome region of GoldDatasetPanel.tsx has been
 * rewritten to consume the shared @leo/design-system primitives
 * (StatHero, ProgressStrip, SegmentedTabs, ToolbarActions) and that
 * the legacy MUI Tabs element has been removed from the chrome.
 *
 * The GoldDatasetPanel body is a 4,781 LOC monolith with many
 * runtime dependencies (API clients, annotation guidelines, dedupe
 * engine, etc.). A full render test is deferred to Phase 2b when
 * the body is decomposed into sub-modules. This test therefore does
 * a static-source scan of the single file that was changed, which
 * is deterministic and fast.
 */
import fs from "fs";
import path from "path";

const PANEL_PATH = path.resolve(
  __dirname,
  "..",
  "components",
  "gold-dataset",
  "GoldDatasetPanel.tsx"
);

describe("VT-LEO-AI-142 Training Data chrome on design-system primitives", () => {
  let source: string;

  beforeAll(() => {
    source = fs.readFileSync(PANEL_PATH, "utf8");
  });

  it("TC-001: imports StatHero, ProgressStrip, SegmentedTabs, ToolbarActions from @leo/design-system", () => {
    const importBlock = source.match(
      /import\s*\{[^}]*\}\s*from\s*"@leo\/design-system"/
    );
    expect(importBlock).not.toBeNull();
    const block = importBlock![0];
    expect(block).toMatch(/\bStatHero\b/);
    expect(block).toMatch(/\bProgressStrip\b/);
    expect(block).toMatch(/\bSegmentedTabs\b/);
    expect(block).toMatch(/\bToolbarActions\b/);
    expect(block).toMatch(/StatTile\s+as\s+DsStatTile/);
  });

  it("TC-002: legacy MUI <Tabs> element is removed from the chrome", () => {
    expect(source).not.toMatch(/<Tabs\b/);
    expect(source).not.toMatch(/<Tab\s+label=/);
  });

  it("TC-003: handleExport still invokes exportMedSpaCyTraining", () => {
    expect(source).toMatch(/exportMedSpaCyTraining\s*\(/);
    const handleExportMatch = source.match(
      /(?:async\s+function\s+handleExport|const\s+handleExport\s*=)[\s\S]{0,800}?exportMedSpaCyTraining/
    );
    expect(handleExportMatch).not.toBeNull();
  });

  it("TC-004: the six canonical stat-hero tile labels are present", () => {
    const labels = [
      "Received",
      "Ready for training",
      "Failed",
      "Verified gold",
      "Synthetic gold",
      "Avg quality",
    ];
    for (const label of labels) {
      expect(source).toContain(`label: "${label}"`);
    }
  });

  it("TC-005: SegmentedTabs renders the three training-data views", () => {
    const segmentedTabsMatch = source.match(
      /<SegmentedTabs[\s\S]{0,1500}?\/>/
    );
    expect(segmentedTabsMatch).not.toBeNull();
    const tag = segmentedTabsMatch![0];
    expect(tag).toMatch(/id:\s*"candidates"/);
    expect(tag).toMatch(/id:\s*"gold"/);
    expect(tag).toMatch(/id:\s*"synthetic"/);
  });

  it("TC-006: ProgressStrip is rendered only on the candidates tab", () => {
    expect(source).toMatch(
      /tab\s*===\s*"candidates"[\s\S]{0,600}?<ProgressStrip\b/
    );
  });

  it("TC-007: ToolbarActions is used for Deduplicate and Export actions", () => {
    const toolbarMatch = source.match(/<ToolbarActions[\s\S]{0,2000}?\/>/);
    expect(toolbarMatch).not.toBeNull();
    const tag = toolbarMatch![0];
    expect(tag).toMatch(/label:\s*"Deduplicate similar"/);
    expect(tag).toMatch(/label:\s*"Export training data"/);
  });

  it("TC-008: similar-candidate lookup is opt-in after accepting gold", () => {
    expect(source).toMatch(
      /const\s+\[\s*findSimilarAfterGold\s*,\s*setFindSimilarAfterGold\s*\]\s*=\s*useState\(\s*false\s*\)/
    );
    expect(source).toContain("Look for similar candidates after accepting");
    expect(source).toMatch(
      /const\s+similarOpened\s*=\s*findSimilarAfterGold\s*\?\s*await\s+findSimilarCandidates\(\s*candidateId\s*,\s*sourceEntitiesJson\s*\)\s*:\s*false/
    );
    expect(source).not.toMatch(/function\s+openNextCandidate/);
    expect(source).not.toMatch(/onNextCandidate=\{/);
  });

  it("TC-009: mark-gold refresh has a visible loading state", () => {
    expect(source).toMatch(/import\s+Snackbar\s+from\s+["']@mui\/material\/Snackbar["']/);
    expect(source).toContain("Saving gold label...");
    expect(source).toContain("Refreshing the review queue...");
    expect(source).toMatch(
      /<Snackbar[\s\S]{0,400}goldSaveInFlightCount\s*>\s*0\s*\|\|\s*goldRefreshInFlight[\s\S]{0,250}anchorOrigin=\{\{\s*vertical:\s*["']bottom["'],\s*horizontal:\s*["']center["']\s*\}\}/
    );
    expect(source).toMatch(
      /<CircularProgress[\s\S]{0,120}aria-label=["']Saving gold label["']/
    );
  });

  it("TC-010: mark-gold uses optimistic local update before background refresh", () => {
    const markGoldMatch = source.match(
      /async\s+function\s+markCandidateAsGold[\s\S]*?\n  \}/
    );
    expect(markGoldMatch).not.toBeNull();
    const markGoldSource = markGoldMatch![0];
    expect(source).toMatch(/function\s+optimisticallyAcceptCandidate\(\s*candidateId:\s*string\s*\)/);
    expect(source).toMatch(/function\s+refreshGoldReviewDataInBackground\(\)/);
    expect(markGoldSource).toMatch(
      /optimisticallyAcceptCandidate\(candidateId\);[\s\S]{0,80}setMarkingGoldCandidateId\(null\);[\s\S]{0,220}await\s+jsonFetch/
    );
    expect(markGoldSource).toMatch(
      /setActionMsg\(["']Saved as gold data\. Candidate status updated to completed\.["']\);[\s\S]{0,120}refreshGoldReviewDataInBackground\(\);/
    );
    expect(markGoldSource).not.toMatch(
      /await\s+Promise\.all\(\[\s*loadList\(\),\s*loadStats\(\)\s*\]\);/
    );
    expect(markGoldSource).not.toMatch(/\|\|\s*markingGoldCandidateId/);
  });
});
