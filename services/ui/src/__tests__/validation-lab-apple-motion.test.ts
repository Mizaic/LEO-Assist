/**
 * Validation Lab home -- Apple fluid-interface invariants.
 *
 * Cosmetic motion/material polish plus the three-path order.
 * No new clinical behaviour. Pins raised cards, press, brand
 * tokens, and investigation / baseline / build order.
 *
 * Design Controls: DI-238DA59A, DI-C5A523A7, DI-613A48DA.
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "admin", "validation-lab");

function read(name: string): string {
  return fs.readFileSync(path.join(ROOT, name), "utf8");
}

describe("Validation Lab Apple motion and materials", () => {
  const home = read("AccuracyLoopHome.tsx");
  const parts = read("AccuracyLoopHomeParts.tsx");
  const doors = read("accuracyLoopDoors.ts");

  it("cards press and use raised tokens, not hardcoded hex", () => {
    expect(parts).toMatch(/whileTap=\{tapScale\(reducedMotion\)\}/);
    expect(parts).toMatch(/springs\.ui/);
    expect(parts).toMatch(/elevation\.card/);
    expect(parts).toMatch(/color\.surface\.raised/);
    expect(parts).toMatch(/color\.brand\.primary/);
    expect(parts).not.toMatch(/#002178/);
    expect(parts).not.toMatch(/#9D174D/);
    expect(parts).not.toMatch(/#1D4ED8/i);
    expect(parts).not.toMatch(/easeOut/);
  });

  it("offers investigation, baseline, then build as the three paths", () => {
    expect(home).toMatch(/HOME_DOORS\.map/);
    expect(home).toMatch(/validation-lab-home-doors/);
    expect(doors).toMatch(/Investigate a non-conformance/);
    expect(doors).toMatch(/Run baseline tests/);
    expect(doors).toMatch(/Build new tests/);
    const clinical = doors.indexOf('id: "clinical"');
    const saved = doors.indexOf('id: "saved"');
    const rule = doors.indexOf('id: "rule"');
    expect(clinical).toBeGreaterThan(-1);
    expect(saved).toBeGreaterThan(clinical);
    expect(rule).toBeGreaterThan(saved);
  });
});
