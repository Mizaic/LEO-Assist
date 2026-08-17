/**
 * Pathways list -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the existing pathways catalogue.
 * No new clinical behaviour. Pins sticky frost, spring filter swap,
 * press on cards, and brand-token status chips.
 *
 * Design Controls: DI-CD931485, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "pathways");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Pathways Apple motion and materials", () => {
  const page = read("page.tsx");
  const card = read("PathwayCard.tsx");
  const parts = read("PathwayCardParts.tsx");

  it("keeps status tabs and New pathway in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="pathways-chrome"/);
    expect(page).toMatch(/<SegmentedTabs\b/);
    expect(page).toMatch(/<StatHero\b/);
    expect(page).toMatch(/<ToolbarActions\b/);
  });

  it("swaps the list on a spring when the status filter changes", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{page\.statusFilter\}/);
    expect(page).toMatch(/data-testid="pathways-list"/);
    expect(page).toMatch(/<EmptyState\b/);
  });

  it("cards press and use raised tokens, not hardcoded hex", () => {
    expect(card).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(card).toMatch(/springs\.ui/);
    expect(card).toMatch(/elevation\.card/);
    expect(card).not.toMatch(/easeOut/);
    expect(card + parts).toMatch(/color\.status\.success/);
    expect(card + parts).toMatch(/color\.status\.warning/);
    expect(card + parts).not.toMatch(/#16A34A/);
    expect(card + parts).not.toMatch(/#ECFDF5/);
    expect(card + parts).not.toMatch(/#1D4ED8/i);
    expect(page).not.toMatch(/#F8FAFC/);
  });
});
