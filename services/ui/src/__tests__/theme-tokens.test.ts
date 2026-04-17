/**
 * VT-LEO-AI-113 - Inclusive design token tests.
 *
 * Cases:
 *  - TC-001 tokens.ts exports the six token groups.
 *  - TC-002 every CONTRAST_PAIR meets WCAG AA.
 *  - TC-003 FOCUS_RING meets size and contrast.
 *  - TC-004 theme typography overrides present with readable sizes.
 *  - TC-005 tokens.css emits custom properties under :root and
 *           prefers-reduced-motion.
 */

import { readFileSync } from "fs";
import { resolve } from "path";
import theme from "@/theme";
import {
  CONTRAST_PAIRS,
  DENSITY_MAP,
  FOCUS_RING,
  MOTION,
  RADIUS,
  SPACING,
  TYPE_SCALE,
  computeContrastRatio,
} from "@/theme/tokens";

function remToPx(value: string): number {
  if (value.endsWith("rem")) return parseFloat(value) * 16;
  if (value.endsWith("px")) return parseFloat(value);
  return Number.NaN;
}

describe("VT-LEO-AI-113 tokens", () => {
  test("TC-001 exports the six required token groups", () => {
    expect(TYPE_SCALE).toBeTruthy();
    expect(SPACING).toBeTruthy();
    expect(RADIUS).toBeTruthy();
    expect(MOTION).toBeTruthy();
    expect(FOCUS_RING).toBeTruthy();
    expect(CONTRAST_PAIRS).toBeTruthy();
    expect(DENSITY_MAP).toBeTruthy();
  });

  test("TC-002 every CONTRAST_PAIR meets its WCAG AA target", () => {
    const failures = CONTRAST_PAIRS.filter((pair) => {
      const ratio = computeContrastRatio(pair.fg, pair.bg);
      const threshold = pair.role === "normal" ? 4.5 : 3;
      return ratio < threshold;
    });
    expect(failures).toEqual([]);
  });

  test("TC-003 FOCUS_RING meets size and contrast requirements", () => {
    expect(FOCUS_RING.widthPx).toBeGreaterThanOrEqual(3);
    const ratio = computeContrastRatio(FOCUS_RING.color, "#F8FAFC");
    expect(ratio).toBeGreaterThanOrEqual(3);
  });

  test("TC-004 theme typography overrides are present with readable sizes", () => {
    expect(theme.typography.body1.fontSize).toBeDefined();
    expect(remToPx(String(theme.typography.body1.fontSize))).toBeGreaterThanOrEqual(
      16,
    );
    expect(remToPx(String(theme.typography.caption.fontSize))).toBeGreaterThanOrEqual(
      13,
    );
    expect(remToPx(String(theme.typography.h1.fontSize))).toBeGreaterThanOrEqual(
      32,
    );
    expect(remToPx(String(theme.typography.h2.fontSize))).toBeGreaterThanOrEqual(
      24,
    );
  });

  test("TC-005 tokens.css emits :root custom properties and reduced-motion block", () => {
    const cssPath = resolve(__dirname, "..", "theme", "tokens.css");
    const content = readFileSync(cssPath, "utf8");
    expect(content).toMatch(/:root\s*{/);
    expect(content).toMatch(/--leo-radius-md:/);
    expect(content).toMatch(/--leo-focus-ring-width:/);
    expect(content).toMatch(/@media \(prefers-reduced-motion: reduce\)/);
    expect(content).toMatch(/@media \(prefers-color-scheme: dark\)/);
  });
});
