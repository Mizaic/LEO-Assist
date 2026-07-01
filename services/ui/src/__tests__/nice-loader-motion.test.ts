/**
 * Static-source verification for the NiceLoaderSection motion pass
 * (ingest-log stagger, springy load button, bouncing empty-state icon).
 * Cosmetic-only change -- see atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const SRC = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/NiceLoaderSection.tsx",
);

function readFile(): string {
  return fs.readFileSync(SRC, "utf8");
}

describe("NiceLoaderSection motion pass", () => {
  test("imports framer-motion and the shared motion presets", () => {
    const src = readFile();
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/from\s+["']\.\/motionPresets["']/);
  });

  test("reads reducedMotion from useMotion()", () => {
    const src = readFile();
    expect(src).toMatch(
      /import\s*\{[^}]*useMotion[^}]*\}\s*from\s*["']@leo\/design-system["']/,
    );
    expect(src).toMatch(/const\s*\{\s*reducedMotion\s*\}\s*=\s*useMotion\(\)/);
  });

  test("ingest log lines animate in/out via AnimatePresence", () => {
    const src = readFile();
    expect(src).toMatch(/AnimatePresence/);
    expect(src).toMatch(/ingestLog\.map/);
    expect(src).toMatch(/popVariants\(reducedMotion\)/);
  });

  test("load button gets a springy hover/tap via bounceInteraction", () => {
    const src = readFile();
    expect(src).toMatch(/bounceInteraction\(reducedMotion/);
  });

  test("empty-state icon has a looping float animation", () => {
    const src = readFile();
    expect(src).toMatch(/icon=\{[\s\S]*?fm\.div[\s\S]*?HistoryOutlinedIcon/);
    expect(src).toMatch(/repeat:\s*Infinity/);
  });

  test("preserves the guideline search and load workflow", () => {
    const src = readFile();
    expect(src).toMatch(/aria-label="Search for a NICE guideline"/);
    expect(src).toMatch(/Load this guideline/);
    expect(src).toMatch(/data-testid="jobs-empty"/);
  });
});
