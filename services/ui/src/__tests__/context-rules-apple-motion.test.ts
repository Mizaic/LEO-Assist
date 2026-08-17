/**
 * Context Rules -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the existing context-rules
 * chrome. No new clinical behaviour. Pins sticky frost, spring
 * filter swap, press on category cards, and brand-token selection.
 *
 * Design Controls: DI-340279C1, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "context-rules");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Context Rules Apple motion and materials", () => {
  const page = read("page.tsx");
  const card = read("ContextCategoryCard.tsx");
  const dialog = read("ContextCategoryDialog.tsx");

  it("keeps search and filters in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="context-rules-chrome"/);
    expect(page).toMatch(/<FilterBar\b/);
    expect(page).not.toMatch(/<SegmentedTabs\b/);
  });

  it("swaps the category grid on a spring when filters change", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{page\.sourceFilter \+ ":" \+ page\.search\}/);
    expect(page).toMatch(/data-testid="context-rules-grid"/);
  });

  it("category cards press and use raised tokens, not MUI chrome", () => {
    expect(card).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(card).toMatch(/springs\.ui/);
    expect(card).toMatch(/elevation\.card/);
    expect(card).toMatch(/typography\.fontFamily\.heading/);
    expect(card).not.toMatch(/@mui\/material/);
    expect(card).not.toMatch(/easeOut/);
  });

  it("selected phrase uses a brand rail, not the banned blue wash", () => {
    const row = read("ContextPhraseRow.tsx");
    expect(row).toMatch(/color\.brand\.primary/);
    expect(row).not.toMatch(/rgba\(29,\s*78,\s*216/);
    expect(dialog).not.toMatch(/#1D4ED8/i);
  });

  it("modal uses frost paper, a spring example swap, and press on close", () => {
    const panel = read("ContextExamplePanel.tsx");
    expect(dialog).toMatch(/frostStyle\([^,]+,\s*"pane"\)/);
    expect(dialog).toMatch(/<SpringSwap\s+swapKey=\{selectedRule\?\.literal/);
    expect(read("ContextDialogTitleBar.tsx")).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(dialog).toMatch(/16 \/ 9/);
    expect(panel).toMatch(/elevation\.card/);
    expect(panel).toMatch(/Without this rule/);
    expect(panel).not.toMatch(/@mui\/material/);
  });
});
