/**
 * Terminology -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the package-status grid and
 * TRUD sync chrome. No new clinical behaviour. Pins sticky frost,
 * spring load swap, press on cards, and brand-token accents.
 *
 * Design Controls: DI-340279C1, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "settings", "terminology");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Terminology Apple motion and materials", () => {
  const page = read("page.tsx");
  const card = read("PackageCard.tsx");
  const log = read("LogPanel.tsx");

  it("keeps package status and refresh in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="terminology-chrome"/);
    expect(page).toMatch(/<StatHero\b/);
    expect(page).toMatch(/id:\s*"refresh-status"/);
  });

  it("swaps the package grid on a spring when status loads", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{page\.loadingStatus \? "loading" : "ready"\}/);
  });

  it("cards press and use raised tokens, not hardcoded hex", () => {
    expect(card).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(card).toMatch(/springs\.ui/);
    expect(card).toMatch(/elevation\.card/);
    expect(card).toMatch(/color\.brand\.primary/);
    expect(card).toMatch(/color\.status\.success/);
    expect(card).not.toMatch(/#16A34A/);
    expect(card).not.toMatch(/#ECFDF5/);
    expect(card).not.toMatch(/#1D4ED8/i);
    expect(card).not.toMatch(/#1E40AF/i);
    expect(card).not.toMatch(/#002178/);
  });

  it("sync box uses a 3:1 edge and solid grey disabled Start sync", () => {
    expect(page).toMatch(/data-testid="terminology-sync-controls"/);
    expect(page).toMatch(/border: "1px solid " \+ color\.text\.secondary/);
    expect(page).toMatch(/color\.surface\.divider/);
    expect(page).toMatch(/"&\.Mui-disabled"/);
    expect(page).not.toMatch(/#F8FAFC/);
  });

  it("log panel is a raised card with token ink, not a hex terminal", () => {
    expect(log).toMatch(/data-testid="terminology-log-panel"/);
    expect(log).toMatch(/color\.surface\.raised/);
    expect(log).toMatch(/color\.status\.danger/);
    expect(log).toMatch(/color\.status\.warning/);
    expect(log).not.toMatch(/#0F172A/);
    expect(log).not.toMatch(/#FCA5A5/);
    expect(log).not.toMatch(/#FDE68A/);
  });
});
