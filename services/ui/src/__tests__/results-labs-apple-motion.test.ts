/**
 * Results/Labs -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish plus the shared SNOMED search /
 * Ask LEO picker. No new clinical behaviour. Pins sticky frost,
 * spring swaps, press on hits, and brand-token accents.
 *
 * Design Controls: DI-3F771AFB, DI-C5A523A7, DI-613A48DA, DI-6BD7B681.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "lab-results");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Results/Labs Apple motion and materials", () => {
  const panel = read("LabResultsPanel.tsx");
  const detail = read("ObservableDetailPanel.tsx");
  const picker = read("FindingSnomedPicker.tsx");
  const tab = read("InterpretationsTab.tsx");
  const ranges = read("RangeFormCard.tsx") + read("labConfigForm.tsx");

  it("keeps search and add in sticky frost chrome", () => {
    expect(panel).toMatch(/<StickyChrome\b/);
    expect(panel).toMatch(/testId="results-labs-chrome"/);
    expect(panel).toMatch(/<FilterBar\b/);
    expect(panel).toMatch(/<StatHero\b/);
  });

  it("swaps the grid on search and the detail pane on tab", () => {
    expect(panel).toMatch(/<SpringSwap\s+swapKey=\{page\.query \|\| "all"\}/);
    expect(detail).toMatch(/<SpringSwap\s+swapKey=\{activeTab\}/);
  });

  it("detail pane is a raised card with a 3:1 edge", () => {
    expect(detail).toMatch(/elevation\.card/);
    expect(detail).toMatch(/color\.surface\.raised/);
    expect(detail).toMatch(/color\.text\.secondary/);
    expect(detail).not.toMatch(/borderColor:\s*"divider"/);
  });

  it("finding picker uses search, Ask LEO, and press on hits", () => {
    expect(picker).toMatch(/Ask LEO/);
    expect(picker).toMatch(/<LeoLogo height=\{16\} variant="dark" spinning/);
    expect(picker).toMatch(/htmlFor=\{search\.searchId\}/);
    expect(picker).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(picker).toMatch(/border: "1px solid " \+ color\.text\.secondary/);
    expect(picker).toMatch(/color\.brand\.primary/);
    expect(tab).toMatch(/FindingSnomedPicker/);
    expect(tab).toMatch(/SnomedPickConfirmDialog/);
    expect(tab).not.toMatch(/Finding SNOMED code/);
    expect(picker).not.toMatch(/#1D4ED8/i);
    expect(picker).not.toMatch(/#EA580C/);
  });

  it("range add form uses a two-column grid and brand edges", () => {
    expect(ranges).toMatch(/gridTemplateColumns: "minmax\(0, 1fr\) minmax\(0, 1fr\)"/);
    expect(ranges).toMatch(/color\.text\.secondary/);
    expect(ranges).toMatch(/color\.surface\.raised/);
    expect(ranges).toMatch(/Who it applies to/);
    expect(ranges).not.toMatch(/flexWrap/);
    expect(ranges).not.toMatch(/#E2E8F0/);
  });
});
