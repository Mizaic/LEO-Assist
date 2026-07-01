/**
 * Static-source verification for the BitmapLifecycleSection celebratory
 * "go live" / compile-success motion pass. Cosmetic-only change -- see
 * atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const SRC = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx",
);

function readFile(): string {
  return fs.readFileSync(SRC, "utf8");
}

describe("BitmapLifecycleSection motion pass", () => {
  test("imports framer-motion and the shared celebration/pop presets", () => {
    const src = readFile();
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/from\s+["']\.\/motionPresets["']/);
    expect(src).toMatch(/celebrationPulse/);
    expect(src).toMatch(/popVariants/);
  });

  test("reads reducedMotion from useMotion()", () => {
    const src = readFile();
    expect(src).toMatch(/const\s*\{\s*reducedMotion\s*\}\s*=\s*useMotion\(\)/);
  });

  test("celebrates the version that was just made live", () => {
    const src = readFile();
    expect(src).toMatch(/justActivatedVersion/);
    expect(src).toMatch(/celebrationPulse\(reducedMotion\)/);
  });

  test("shows a Compiled! badge right after a successful compile", () => {
    const src = readFile();
    expect(src).toMatch(/justCompiled/);
    expect(src).toMatch(/label="Compiled!"/);
  });

  test("preserves the three-step compile workflow", () => {
    const src = readFile();
    expect(src).toMatch(/Rules approved.*Compile rules.*Go live/s);
    expect(src).toMatch(/aria-label=\{`Make version \$\{v\.version\} live`\}/);
  });
});
