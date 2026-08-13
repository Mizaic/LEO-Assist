/**
 * Static-source verification for the BitmapLifecycleSection celebratory
 * "go live" / compile-success motion pass. Cosmetic-only change -- see
 * atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const SECTION = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx",
);
const HOOK = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/useBitmapLifecycle.ts",
);
const HELPERS = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/bitmapLifecycleHelpers.tsx",
);

function read(...paths: string[]): string {
  return paths.map((p) => fs.readFileSync(p, "utf8")).join("\n");
}

describe("BitmapLifecycleSection motion pass", () => {
  test("imports framer-motion and the shared celebration/pop presets", () => {
    const src = read(SECTION, HELPERS);
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/from\s+["']\.\/motionPresets["']/);
    expect(src).toMatch(/celebrationPulse/);
    expect(src).toMatch(/popVariants/);
  });

  test("reads reducedMotion from useMotion()", () => {
    const src = read(SECTION);
    expect(src).toMatch(/const\s*\{\s*reducedMotion\s*\}\s*=\s*useMotion\(\)/);
  });

  test("celebrates the version that was just made live", () => {
    const src = read(SECTION, HOOK);
    expect(src).toMatch(/justActivatedVersion/);
    expect(src).toMatch(/celebrationPulse\(reducedMotion\)/);
  });

  test("shows a Compiled! badge right after a successful compile", () => {
    const src = read(SECTION, HOOK);
    expect(src).toMatch(/justCompiled/);
    expect(src).toMatch(/label="Compiled!"/);
  });

  test("preserves the three-step candidate compile workflow", () => {
    const src = read(SECTION, HOOK, HELPERS);
    expect(src).toMatch(/Rules approved.*Compile candidate.*Test and go live/s);
    expect(src).toMatch(/activate:\s*false/);
    expect(src).toMatch(/Compile candidate/);
    expect(src).toMatch(/Test with Lab patients/);
    expect(src).toMatch(/Historic shadow/);
    expect(src).toMatch(/aria-label=\{`Make version \$\{v\.version\} live`\}/);
  });

  test("go-live confirm dialog shows busy feedback while activating", () => {
    const src = read(SECTION, HOOK);
    expect(src).toMatch(/busy=\{life\.activatingVersion === life\.confirmVersion\}/);
    expect(src).toMatch(/busyLabel="Going live\.\.\."/);
    expect(src).toMatch(/setActivatingVersion\(version\)/);
  });

  test("compile progress uses indeterminate ProgressStrip with phase + elapsed", () => {
    const src = read(SECTION, HOOK, HELPERS);
    expect(src).toMatch(/indeterminate/);
    expect(src).toMatch(/compilePhaseLabel/);
    expect(src).toMatch(/formatCompileElapsed/);
    expect(src).toMatch(/compileElapsedSec/);
    expect(src).toMatch(/data-testid="bitmap-compile-progress"/);
    expect(src).toMatch(/Building the candidate lookup index/);
    expect(src).not.toMatch(
      /label="Building the candidate lookup index\.\.\."[\s\S]{0,80}value=\{0\}/,
    );
  });
});

