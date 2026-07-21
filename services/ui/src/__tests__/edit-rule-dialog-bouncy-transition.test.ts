/**
 * Static-source verification for EditRuleDialog's custom bouncy Dialog
 * open/close transition. Cosmetic-only change -- see
 * atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const SRC = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/EditRuleDialog/index.tsx",
);

function readFile(): string {
  return fs.readFileSync(SRC, "utf8");
}

describe("EditRuleDialog bouncy transition", () => {
  test("defines a forwardRef BouncyDialogTransition component", () => {
    const src = readFile();
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/const BouncyDialogTransition = forwardRef</);
  });

  test("wires the transition into MUI's Dialog via TransitionComponent", () => {
    const src = readFile();
    expect(src).toMatch(/TransitionComponent=\{BouncyDialogTransition\}/);
  });

  test("respects prefers-reduced-motion via useMotion()", () => {
    const src = readFile();
    expect(src).toMatch(
      /import\s*\{[^}]*useMotion[^}]*\}\s*from\s*["']@leo\/design-system["']/,
    );
    expect(src).toMatch(/const \{ reducedMotion \} = useMotion\(\)/);
  });

  test("drives Modal lifecycle callbacks deterministically (not framer's onAnimationComplete)", () => {
    const src = readFile();
    expect(src).toMatch(/onEnter\?\.\(/);
    expect(src).toMatch(/onEntered\?\.\(/);
    expect(src).toMatch(/onExit\?\.\(/);
    expect(src).toMatch(/onExited\?\.\(/);
  });

  test("still opens with fullWidth/maxWidth xl and the fullscreen toggle", () => {
    const src = readFile();
    expect(src).toMatch(/fullWidth/);
    expect(src).toMatch(/maxWidth="xl"/);
    expect(src).toMatch(/fullScreen=\{fullscreen\}/);
  });
});
