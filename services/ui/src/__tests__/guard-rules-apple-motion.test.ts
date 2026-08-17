/**
 * Pipeline Guards -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the existing guard-rules
 * chrome. No new clinical behaviour. Pins sticky frost, spring
 * filter swap, press on family cards, and a frosted 16:9 modal.
 *
 * Design Controls: DI-34712A9A, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "guard-rules");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Pipeline Guards Apple motion and materials", () => {
  const page = read("page.tsx");
  const card = read("GuardFamilyCard.tsx");
  const dialog = read("GuardFamilyDialog.tsx");
  const row = read("GuardPatternRow.tsx");
  const panel = read("GuardExamplePanel.tsx");

  it("keeps search and family chips in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="guard-rules-chrome"/);
    expect(page).toMatch(/<FilterBar\b/);
    expect(page).toMatch(/Search patterns/);
  });

  it("swaps the family grid on a spring when filters change", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{page\.familyFilter \+ ":" \+ page\.search\}/);
    expect(page).toMatch(/data-testid="guard-rules-grid"/);
  });

  it("family cards press and use raised tokens, not MUI chrome", () => {
    expect(card).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(card).toMatch(/springs\.ui/);
    expect(card).toMatch(/elevation\.card/);
    expect(card).toMatch(/typography\.fontFamily\.heading/);
    expect(card).not.toMatch(/@mui\/material/);
    expect(card).not.toMatch(/easeOut/);
  });

  it("modal uses frost paper and a spring example swap", () => {
    expect(dialog).toMatch(/frostStyle\([^,]+,\s*"pane"\)/);
    expect(dialog).toMatch(/<SpringSwap\s+swapKey=\{selectedRule\?\.rule_id/);
    expect(dialog).toMatch(/16 \/ 9/);
    expect(dialog).toMatch(/GuardExamplePanel/);
    expect(panel).toMatch(/elevation\.card/);
    expect(panel).not.toMatch(/@mui\/material/);
  });

  it("selected pattern uses a brand rail, not the banned blue wash", () => {
    expect(row).toMatch(/color\.brand\.primary/);
    expect(row).not.toMatch(/rgba\(29,\s*78,\s*216/);
    expect(row).not.toMatch(/#1D4ED8/i);
  });
});
