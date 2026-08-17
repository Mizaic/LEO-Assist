/**
 * VT-LEO-AI-146 -- Wave E Phase 4
 *
 * Verifies that the AI Instructions list page (admin/prompts/page.tsx)
 * has been redesigned onto the shared @leo/design-system primitives:
 * StatHero + FilterBar + SegmentedTabs + ToolbarActions + ReviewListCard.
 *
 * Acceptance criteria (per DI-LEO-AI-148):
 *   - The page imports the canonical chrome primitives from
 *     @leo/design-system rather than building bespoke chrome.
 *   - The legacy page-owned chrome (h4 page title + bespoke
 *     PromptCard grid + raw chip filter strip + raw TextField search)
 *     has been removed.
 *   - All pre-existing data and routing handlers continue to work
 *     (api.get('/api/prompts'), router.push to /admin/prompts/:id and
 *     /admin/prompts/new, grouped browse mode, search + category
 *     filter).
 *   - Loading, empty and no-match states stay reachable.
 *
 * The page hits /api/prompts on mount which makes a live render test
 * fragile in unit-test scope; this is a deterministic static-source
 * scan, consistent with the VT-LEO-AI-142 / VT-LEO-AI-145 chrome
 * verification approach.
 */
import fs from "fs";
import path from "path";

const PAGE_PATH = path.resolve(
  __dirname,
  "..",
  "app",
  "admin",
  "prompts",
  "page.tsx",
);

let source: string;

function importBlock(src: string): string {
  const match = src.match(/import\s*\{[^}]*\}\s*from\s*"@leo\/design-system"/);
  return match ? match[0] : "";
}

describe("VT-LEO-AI-146 AI Instructions list on design-system primitives", () => {
  beforeAll(() => {
    source = fs.readFileSync(PAGE_PATH, "utf8");
  });

  // -- TC-001 Imports ------------------------------------------------------

  it("TC-001: imports StatHero, FilterBar, SegmentedTabs, ToolbarActions, ReviewListCard from @leo/design-system", () => {
    const block = importBlock(source);
    expect(block).not.toBe("");
    expect(block).toMatch(/\bStatHero\b/);
    expect(block).toMatch(/\bFilterBar\b/);
    expect(block).toMatch(/\bSegmentedTabs\b/);
    expect(block).toMatch(/\bToolbarActions\b/);
    expect(block).toMatch(/\bReviewListCard\b/);
    expect(block).toMatch(/\btype ReviewListItem\b/);
    expect(block).toMatch(/\btype StatTile\b/);
    expect(block).toMatch(/\btype ToolbarAction\b/);
  });

  // -- TC-002 Legacy chrome removed ---------------------------------------

  it("TC-002: legacy bespoke chrome is removed (h4 page title, PromptCard grid, raw TextField search)", () => {
    expect(source).not.toMatch(/<Typography\s+variant="h4"/);
    expect(source).not.toMatch(/function\s+PromptCard\b/);
    expect(source).not.toMatch(/<CardActionArea\b/);
    expect(source).not.toMatch(/<TextField\b/);
  });

  // -- TC-003 Behaviour preserved -----------------------------------------

  it("TC-003: pre-existing data + routing handlers stay wired", () => {
    const hook = fs.readFileSync(
      path.resolve(__dirname, "..", "app", "admin", "prompts", "usePromptsList.ts"),
      "utf8",
    );
    const wired = source + hook;
    expect(wired).toMatch(
      /api[\s\S]*?\.get<\{\s*prompts:\s*PromptConfig\[\]\s*\}>\("\/api\/prompts"\)/,
    );
    expect(source).toMatch(/router\.push\(`\/admin\/prompts\/\$\{[^}]+\}`\)/);
    expect(source).toMatch(/router\.push\("\/admin\/prompts\/new"\)/);
    expect(hook).toMatch(/sortByIsoDateDesc/);
  });

  it("TC-004: grouped browse + flat filtered modes preserved", () => {
    expect(source).toMatch(/data-testid="prompts-grouped"/);
    expect(source).toMatch(/isFiltering\s*\?/);
  });

  // -- TC-004 Single primary action ---------------------------------------

  it("TC-005: ToolbarActions exposes a single primary 'New instructions' action", () => {
    expect(source).toMatch(/id:\s*"new-instructions"/);
    expect(source).toMatch(/variant:\s*"primary"/);
    const primaryMatches = source.match(/variant:\s*"primary"/g) ?? [];
    expect(primaryMatches.length).toBe(1);
  });

  // -- TC-006 Body primitive + states -------------------------------------

  it("TC-006: body uses ReviewListCard and preserves loading, empty and no-match states", () => {
    const states = fs.readFileSync(
      path.resolve(__dirname, "..", "app", "admin", "prompts", "promptListStates.tsx"),
      "utf8",
    );
    expect(source).toMatch(/<ReviewListCard\b/);
    expect(source).toMatch(/<SkeletonList\b/);
    expect(states).toMatch(/data-testid="prompts-skeleton-list"/);
    expect(states).toMatch(/data-testid="prompts-empty"/);
    expect(states).toMatch(/data-testid="prompts-no-match"/);
  });

  // -- TC-007 Stat tiles ---------------------------------------------------

  it("TC-007: the four canonical stat-tile labels are present", () => {
    const labels = [
      "Instruction sets",
      "Categories covered",
      "With double-check",
      "With examples",
    ];
    for (const label of labels) {
      expect(source).toContain(`label: "${label}"`);
    }
  });

  // -- TC-008 SegmentedTabs API correctness -------------------------------

  it("TC-008: SegmentedTabs is wired with tabs/value/onChange/aria-label (not items/activeId)", () => {
    const tagMatch = source.match(/<SegmentedTabs\b[\s\S]*?\/>/);
    expect(tagMatch).not.toBeNull();
    const tag = tagMatch![0];
    expect(tag).toMatch(/\btabs=\{/);
    expect(tag).toMatch(/\bvalue=\{activeCategory\}/);
    expect(tag).toMatch(/\baria-label=/);
    expect(tag).not.toMatch(/\bactiveId=/);
    expect(tag).not.toMatch(/\bitems=/);
  });
});
