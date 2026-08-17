/**
 * AI Instructions editor -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the prompt tuner. No new
 * clinical behaviour. Pins sticky frost, spring tab swap, token
 * identity fields, and a solid disabled Save (not faded brand blue).
 *
 * Design Controls: DI-B954388C, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "prompts", "[id]");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

describe("AI Instructions editor Apple motion and materials", () => {
  const page = read("page.tsx");
  const identity = read("_components/IdentitySection.tsx");
  const instructions = read("_components/InstructionsTab.tsx");
  const hero = fs.readFileSync(
    path.resolve(
      __dirname,
      "../../../design-system/src/primitives/PageHero.tsx",
    ),
    "utf8",
  );

  it("keeps identity and tabs in sticky frost chrome", () => {
    expect(page).toMatch(/<StickyChrome\b/);
    expect(page).toMatch(/testId="prompt-tuner-chrome"/);
    expect(page).toMatch(/<IdentitySection\b/);
    expect(page).toMatch(/<SegmentedTabs\b/);
    expect(page).toMatch(/<PageHero\b/);
    expect(page).toMatch(/data-testid="prompt-tuner-hero"/);
  });

  it("swaps tab bodies on a spring", () => {
    expect(page).toMatch(/<SpringSwap\s+swapKey=\{ui\.tab\}/);
    expect(page).toMatch(/id:\s*"instructions"/);
    expect(page).toMatch(/id:\s*"output-format"/);
    expect(page).toMatch(/id:\s*"teaching-examples"/);
    expect(page).toMatch(/id:\s*"test-it"/);
  });

  it("identity fields use visible labels and 3:1 borders", () => {
    expect(identity).toContain("Name");
    expect(identity).toContain("What is this for?");
    expect(identity).toContain("Double-check results");
    expect(identity).toMatch(/color\.text\.secondary/);
    expect(identity).not.toMatch(/@mui\/material\/TextField/);
    expect(identity).not.toMatch(/#1D4ED8/i);
  });

  it("disabled Save is solid grey, not faded brand blue", () => {
    expect(hero).toMatch(/color\.surface\.divider/);
    expect(hero).toMatch(/color\.text\.secondary/);
    expect(hero).not.toMatch(/opacity:\s*cta\.disabled \? 0\.5/);
    expect(instructions).toMatch(/AI improve/);
    expect(instructions).toMatch(/color\.surface\.divider/);
  });
});
