/**
 * Phrase mappings -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the existing phrase-mappings
 * chrome. No new clinical behaviour. Pins sticky frost, spring
 * workspace swap, press feedback, and brand-token selection.
 *
 * Design Controls: DI-6BD7B681, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "settings", "surface-forms");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Phrase mappings Apple motion and materials", () => {
  const page = read("page.tsx");
  const queue = read("PhraseQueueList.tsx");
  const pane = read("PhraseDetailPane.tsx") + read("PhraseMappingEditor.tsx");
  const dock = read("PhraseDetailSaveDock.tsx");
  const header = read("PhraseDetailHeader.tsx");

  it("keeps workspace tabs in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="phrase-mappings-chrome"/);
    expect(page).toMatch(/<SegmentedTabs\b/);
  });

  it("swaps inbox, drafts, review, and live on a spring", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{state\.mode\}/);
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{state\.selected\.phrase_key\}/);
  });

  it("queue rows press and raise the selected phrase", () => {
    expect(queue).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(queue).toMatch(/layoutId=\{reducedMotion \? undefined : "phrase-queue-rail"\}/);
    expect(queue).toMatch(/color\.brand\.primary/);
    expect(queue).not.toMatch(/#1D4ED8/i);
    expect(queue).not.toMatch(/rgba\(29,\s*78,\s*216/);
  });

  it("detail pane is a raised card with display tracking", () => {
    expect(pane).toMatch(/elevation\.card/);
    expect(header).toMatch(/typography\.letterSpacing\.display/);
    expect(header).toMatch(/typography\.fontFamily\.heading/);
  });

  it("save dock uses frost and a press spring", () => {
    expect(dock).toMatch(/frostStyle\([^,]+,\s*"light"\)/);
    expect(dock).toMatch(/whileTap=/);
    expect(dock).toMatch(/springs\.press/);
  });

  it("search, exclude, and disabled save meet AA contrast", () => {
    const picker = read("PhraseSnomedPicker.tsx");
    expect(picker).toMatch(/htmlFor=\{search\.searchId\}/);
    expect(picker).toMatch(/<LeoLogo height=\{16\} variant="dark" spinning/);
    expect(picker).toMatch(/Search SNOMED/);
    expect(picker).toMatch(/border: "1px solid " \+ color\.text\.secondary/);
    expect(picker).not.toMatch(/#F2F2F7/);
    expect(pane).toMatch(/2px solid " \+ color\.text\.secondary/);
    expect(dock).not.toMatch(/opacity: disabled \? 0\.4/);
    expect(dock).toMatch(/color\.text\.secondary/);
    expect(dock).toMatch(/color\.surface\.divider/);
  });
});
