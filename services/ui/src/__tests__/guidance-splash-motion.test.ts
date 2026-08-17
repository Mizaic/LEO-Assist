/**
 * Static-source verification for the Clinical Guidelines animated splash
 * screen and the shared motion presets it (and later builder motion work)
 * reuse. Cosmetic-only change -- see atlas-vt-enforcement.mdc Step 0.
 *
 * Test files:
 *   - services/ui/src/__tests__/guidance-splash-motion.test.ts
 */

import * as fs from "fs";
import * as path from "path";

const GUIDANCE_DIR = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance",
);

function read(file: string): string {
  return fs.readFileSync(path.join(GUIDANCE_DIR, file), "utf8");
}

describe("GuidelineBuilderSplash.tsx", () => {
  const src = read("GuidelineBuilderSplash.tsx");

  test("exports a default component and the session-key constant", () => {
    expect(src).toMatch(/export\s+const\s+GUIDANCE_SPLASH_SESSION_KEY/);
    expect(src).toMatch(/export default function GuidelineBuilderSplash/);
  });

  test("honours prefers-reduced-motion via useMotion()", () => {
    expect(src).toMatch(
      /import\s*\{[^}]*useMotion[^}]*\}\s*from\s*["']@leo\/design-system["']/,
    );
    expect(src).toMatch(/reducedMotion/);
  });

  test("always auto-dismisses via a timer, regardless of motion preference", () => {
    expect(src).toMatch(/setTimeout\(onDismiss/);
  });

  test("provides a skip control for accessibility and impatient users", () => {
    expect(src).toMatch(/Skip the guideline builder intro animation/);
  });

  test("provides a screen-reader status announcement", () => {
    expect(src).toMatch(/role="status"/);
    expect(src).toMatch(/Loading your guideline builder/);
  });

  test("decorative graphics are hidden from assistive tech", () => {
    expect(src).toMatch(/aria-hidden="true"/);
  });
});

describe("guidance/page.tsx -- splash wiring", () => {
  const src = read("page.tsx");
  const hook = read("useGuidancePage.ts");
  const card = read("GuidanceStepCard.tsx");

  test("imports and mounts GuidelineBuilderSplash", () => {
    expect(src).toMatch(/import GuidelineBuilderSplash/);
    expect(src).toMatch(/<GuidelineBuilderSplash/);
  });

  test("gates the splash with a sessionStorage flag", () => {
    expect(hook).toMatch(/sessionStorage\.getItem\(GUIDANCE_SPLASH_SESSION_KEY\)/);
    expect(hook).toMatch(/sessionStorage\.setItem\(GUIDANCE_SPLASH_SESSION_KEY/);
  });

  test("wraps the splash in AnimatePresence so exit animations can run", () => {
    expect(src).toMatch(/AnimatePresence/);
  });

  test("StepCard entrance now reads reducedMotion from useMotion()", () => {
    expect(hook).toMatch(/useMotion\(\)/);
    expect(card).toMatch(/reducedMotion:\s*boolean/);
  });

  test("StepCard uses critically damped springs for chrome", () => {
    expect(card).toMatch(/springs\.ui/);
    expect(card).toMatch(/springOrInstant\(reducedMotion/);
  });

  test("still preserves the VT-LEO-AI-150 chrome invariants", () => {
    expect(card).toMatch(/fm\.section/);
    expect(card).toMatch(/borderRadius:\s*12,/);
    expect(card).toMatch(/width:\s*3,/);
    expect(card).toMatch(/background:\s*accent,/);
  });
});

describe("motionPresets.ts", () => {
  const src = read("motionPresets.ts");

  test("exports the shared preset helpers", () => {
    for (const name of [
      "popSpring",
      "staggerDelay",
      "popVariants",
      "slidePanelVariants",
      "bounceInteraction",
      "celebrationPulse",
    ]) {
      expect(src).toMatch(new RegExp(`export function ${name}`));
    }
  });

  test("every preset collapses to a reduced-motion-safe form", () => {
    const matches = src.match(/reducedMotion/g) ?? [];
    expect(matches.length).toBeGreaterThanOrEqual(6);
  });
});
