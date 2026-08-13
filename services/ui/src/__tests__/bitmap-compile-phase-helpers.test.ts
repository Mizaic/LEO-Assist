/**
 * Compile-phase copy helpers for the bitmap lifecycle progress strip.
 */

import {
  COMPILE_PHASES,
  compilePhaseLabel,
  formatCompileElapsed,
} from "../app/admin/guidance/bitmapLifecycleHelpers";

describe("bitmap compile phase helpers", () => {
  test("advances phase labels by elapsed seconds", () => {
    expect(compilePhaseLabel(0)).toBe(COMPILE_PHASES[0].label);
    expect(compilePhaseLabel(8)).toBe(COMPILE_PHASES[1].label);
    expect(compilePhaseLabel(25)).toBe(COMPILE_PHASES[2].label);
    expect(compilePhaseLabel(60)).toBe(COMPILE_PHASES[3].label);
    expect(compilePhaseLabel(200)).toBe(COMPILE_PHASES[4].label);
  });

  test("formats elapsed time for the progress subtitle", () => {
    expect(formatCompileElapsed(12)).toBe("12s");
    expect(formatCompileElapsed(75)).toBe("1m 15s");
  });
});
