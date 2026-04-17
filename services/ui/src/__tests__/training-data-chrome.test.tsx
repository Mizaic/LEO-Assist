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
});
