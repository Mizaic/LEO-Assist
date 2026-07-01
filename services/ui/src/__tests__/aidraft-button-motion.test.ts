/**
 * Static-source verification for the AIDraftButton sparkle/pulse-while-
 * generating motion pass. Cosmetic-only change -- see
 * atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const SRC = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/EditRuleDialog/AIDraftButton.tsx",
);

function readFile(): string {
  return fs.readFileSync(SRC, "utf8");
}

describe("AIDraftButton motion pass", () => {
  test("imports framer-motion, useMotion, and the shared bounceInteraction preset", () => {
    const src = readFile();
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/from\s+["']\.\.\/motionPresets["']/);
    expect(src).toMatch(/bounceInteraction/);
  });

  test("spins the sparkle icon while a draft is generating", () => {
    const src = readFile();
    expect(src).toMatch(/function SparkleIcon/);
    expect(src).toMatch(/loading\s*\?\s*\{\s*rotate:\s*\[0,\s*360\]/);
  });

  test("twinkles the sparkle icon on idle to invite a click", () => {
    const src = readFile();
    expect(src).toMatch(/repeat: Infinity, repeatDelay: 1\.5/);
  });

  test("pulses a glow around the button while generating", () => {
    const src = readFile();
    expect(src).toMatch(/generatingGlow/);
    expect(src).toMatch(/boxShadow:\s*\[/);
  });

  test("falls back to a static icon under reduced motion", () => {
    const src = readFile();
    expect(src).toMatch(/if \(reducedMotion\) return icon;/);
  });

  test("preserves both CTA variants and their aria-labels", () => {
    const src = readFile();
    expect(src).toMatch(/aria-label=\{AI_DRAFT\.emptyCtaLabel\}/);
    expect(src).toMatch(/aria-label=\{AI_DRAFT\.regenerateAria\}/);
    expect(src).toMatch(/disabled=\{loading \|\| !ruleId\}/);
  });
});
