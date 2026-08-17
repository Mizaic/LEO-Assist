/**
 * Domains -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the clinical areas grid.
 * No new clinical behaviour. Pins sticky frost, spring filter swap,
 * press on cards, and brand-token chips.
 *
 * Design Controls: DI-340279C1, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "settings", "domains");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

describe("Domains Apple motion and materials", () => {
  const page = read("page.tsx");
  const card = read("_components/DomainCard.tsx");
  const dialogs =
    read("_components/DomainFormDialogs.tsx") +
    read("_components/domainFormFields.tsx");

  it("keeps source tabs and search in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="domains-chrome"/);
    expect(page).toMatch(/<SegmentedTabs\b/);
    expect(page).toMatch(/<FilterBar\b/);
    expect(page).toMatch(/<StatHero\b/);
  });

  it("swaps the card grid on a spring when source or search changes", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{page\.sourceFilter \+ ":" \+ page\.searchText\}/);
    expect(page).toMatch(/data-testid="domains-grid"/);
  });

  it("cards press and use raised tokens, not hardcoded hex", () => {
    expect(card).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(card).toMatch(/springs\.ui/);
    expect(card).toMatch(/elevation\.card/);
    expect(card).toMatch(/CoverageBar/);
    expect(card).not.toMatch(/#2563EB/);
    expect(card).not.toMatch(/#1D4ED8/i);
    expect(card).not.toMatch(/easeOut/);
  });

  it("create and rename dialogs use frost paper and 3:1 field borders", () => {
    expect(dialogs).toMatch(/frostStyle\([^,]+,\s*"pane"\)/);
    expect(dialogs).toContain("Create a new area");
    expect(dialogs).toContain("Rename area");
    expect(dialogs).toContain("Area name");
    expect(dialogs).toMatch(/color\.text\.secondary/);
  });
});
