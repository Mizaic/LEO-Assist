/**
 * Clinical Guidelines -- Apple fluid-interface + one-step workflow.
 *
 * Cosmetic motion/material polish. The jump strip is the only map.
 * One step shows at a time. No new clinical behaviour.
 *
 * Design Controls: DI-0C8FBAF7, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "guidance");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Clinical Guidelines Apple motion and one-step workflow", () => {
  const page = read("page.tsx");
  const card = read("GuidanceStepCard.tsx");

  it("keeps the jump strip in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="guidance-jump-strip"/);
    expect(page).toMatch(/<SegmentedTabs\b/);
    expect(page).toMatch(/<StatHero\b/);
    expect(page).toMatch(/Choose a step/);
    expect(page).toMatch(/guidance-next-step/);
  });

  it("numbers every step 1 to 4 so the bar matches the hint", () => {
    const hook = read("useGuidancePage.ts");
    expect(hook).toMatch(/label:\s*"1\. Load"/);
    expect(hook).toMatch(/label:\s*"2\. Inspect"/);
    expect(hook).toMatch(/label:\s*"3\. Review"/);
    expect(hook).toMatch(/label:\s*"4\. Compile"/);
  });

  it("shows one step at a time on a spring", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{page\.activeStep\}/);
    expect(page).toMatch(/activeStep === "load"/);
    expect(page).toMatch(/activeStep === "inspect"/);
    expect(page).toMatch(/activeStep === "review"/);
    expect(page).not.toMatch(/<Collapse\b/);
  });

  it("step cards use tokens and springs, not hardcoded hex", () => {
    expect(card).toMatch(/fm\.section/);
    expect(card).toMatch(/springs\.ui/);
    expect(card).toMatch(/elevation\.card/);
    expect(page).toMatch(/color\.brand\.primary/);
    expect(page + card).not.toMatch(/#0d46d6/);
    expect(page + card).not.toMatch(/#14B8A6/);
    expect(page + card).not.toMatch(/#1D4ED8/i);
  });
});
