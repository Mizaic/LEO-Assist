/**
 * AI Instructions list -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the existing prompts list.
 * No new clinical behaviour. Pins sticky frost, spring list swap,
 * and token category chips.
 *
 * Design Controls: DI-553F50A2, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "prompts");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("AI Instructions Apple motion and materials", () => {
  const page = read("page.tsx");
  const cats = read("promptCategories.ts");
  const rows = read("promptListRows.tsx");

  it("keeps search and category tabs in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="ai-instructions-chrome"/);
    expect(page).toMatch(/<FilterBar\b/);
    expect(page).toMatch(/<SegmentedTabs\b/);
  });

  it("swaps the list on a spring when category or search changes", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{[^}]+\}/);
    expect(page).toMatch(/activeCategory \+ ":" \+ list\.search/);
    expect(page).toMatch(/<ReviewListCard\b/);
  });

  it("category colours come from brand tokens, not hardcoded hex", () => {
    expect(cats).toMatch(/color\.brand\.primary/);
    expect(cats).toMatch(/SBAR_CONTEXT_GROUP_STYLE/);
    expect(cats).not.toMatch(/#1565c0/i);
    expect(cats).not.toMatch(/#1D4ED8/i);
    expect(rows).not.toMatch(/@mui\/material\/Chip/);
  });
});
