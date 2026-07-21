/**
 * Static-source verification for the HorizontalStepper sliding active-step
 * indicator and the EditRuleDialog step-canvas slide/fade transition.
 * Cosmetic-only change -- see atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const EDIT_RULE_DIALOG_DIR = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/EditRuleDialog",
);

function read(file: string): string {
  return fs.readFileSync(path.join(EDIT_RULE_DIALOG_DIR, file), "utf8");
}

describe("HorizontalStepper.tsx sliding indicator", () => {
  const src = read("HorizontalStepper.tsx");

  test("imports framer-motion and useMotion", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(
      /import\s*\{[^}]*useMotion[^}]*\}\s*from\s*["']@leo\/design-system["']/,
    );
  });

  test("uses a shared layoutId for the active-step pill", () => {
    expect(src).toMatch(/layoutId="stepper-active-pill"/);
    expect(src).toMatch(/isCurrent && \(/);
  });

  test("preserves the step navigation aria contract", () => {
    expect(src).toMatch(/aria-current=\{isCurrent \? "step" : undefined\}/);
    expect(src).toMatch(/role="navigation"/);
    expect(src).toMatch(/Steps to change this rule/);
  });
});

describe("EditRuleDialog/index.tsx step-canvas transition", () => {
  const src = read("index.tsx");

  test("imports the shared slidePanelVariants preset", () => {
    expect(src).toMatch(/from\s+["']\.\.\/motionPresets["']/);
    expect(src).toMatch(/slidePanelVariants/);
  });

  test("animates the who/suggest/save canvas keyed by currentStepId", () => {
    expect(src).toMatch(/key=\{currentStepId\}/);
    expect(src).toMatch(/variants=\{slidePanelVariants\(reducedMotion, stepDirection\)\}/);
  });

  test("tracks step direction so the slide direction matches navigation", () => {
    expect(src).toMatch(/stepDirection/);
    expect(src).toMatch(/prevStepIndexRef/);
  });
});
