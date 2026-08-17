/**
 * Training Data page -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish on the existing training-data
 * chrome. No new clinical behaviour. Pins springs, press feedback,
 * frosted chrome, and reduced-motion fallbacks.
 *
 * Design Controls: DI-C5A523A7, DI-613A48DA, DO-BCA9B190, DO-124AC2C4.
 */
import fs from "fs";
import path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

describe("Training Data Apple motion and materials", () => {
  const page = readFile("services/ui/src/app/admin/knowledge/page.tsx");
  const panel = readFile("services/ui/src/components/gold-dataset/GoldDatasetPanel.tsx");
  const sidebar = readFile("services/ui/src/components/ui/KnowledgeSidebar.tsx");
  const tabs = readFile("services/design-system/src/primitives/SegmentedTabs.tsx");
  const springs = readFile("services/design-system/src/motion/springs.ts");
  const colors = readFile("services/design-system/src/tokens/color.ts");

  it("page canvas is a blue-grey ground, not near-white", () => {
    expect(colors).toMatch(/canvas:\s*"#D8E0EE"/);
    expect(page).toMatch(/color\.surface\.canvas/);
  });

  it("uses critically damped springs (bounce 0) for default chrome", () => {
    expect(springs).toMatch(/bounce:\s*0/);
    expect(springs).toMatch(/duration:\s*0\.35/);
  });

  it("knowledge tab swap honours useMotion and springs.ui", () => {
    expect(page).toMatch(/useMotion\(\)/);
    expect(page).toMatch(/springOrInstant\(reducedMotion,\s*springs\.ui\)/);
    expect(page).toMatch(/color\.surface\.canvas/);
  });

  it("training-data chrome is sticky frost with a spring tab swap", () => {
    expect(panel).toMatch(/<StickyChrome\b/);
    expect(panel).toMatch(/<SpringSwap\s+swapKey=\{tab\}/);
  });

  it("sidebar uses a white glass pane and press-scale on pointer-down", () => {
    expect(sidebar).toMatch(/frostStyle\([^,]+,\s*"pane"\)/);
    expect(sidebar).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(sidebar).toMatch(/useReducedTransparency/);
    expect(sidebar).toMatch(/inset 0 1px 2px/);
  });

  it("segmented tabs animate a pill from the live button box", () => {
    expect(tabs).toMatch(/useSegmentedPill/);
    expect(tabs).toMatch(/data-testid="segmented-tabs-pill"/);
    expect(tabs).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(tabs).toMatch(/border: "1px solid " \+ color\.text\.secondary/);
    expect(tabs).toMatch(/cursor: "pointer"/);
  });

  it("reduced motion collapses springs to duration 0", () => {
    expect(springs).toMatch(/reducedMotion \? \{ duration: 0 \}/);
  });
});
