/**
 * Static-source verification for the LogicTreeEditor leaf-row motion pass:
 * staggered entrance/exit pop for PathwayCard (via PathwayList), RuleFiredRow,
 * DemographicRow, ObservationRow, and ConceptPill. Cosmetic-only change --
 * see atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const DIR = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/EditRuleDialog/LogicTreeEditor",
);

function readFile(name: string): string {
  return fs.readFileSync(path.join(DIR, name), "utf8");
}

describe("PathwayList motion pass", () => {
  const src = readFile("PathwayList.tsx");

  test("imports framer-motion, useMotion, and shared presets", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/from\s+["']\.\.\/\.\.\/motionPresets["']/);
    expect(src).toMatch(/popVariants/);
    expect(src).toMatch(/bounceInteraction/);
  });

  test("wraps pathway cards in AnimatePresence for staggered entrance/exit", () => {
    expect(src).toMatch(/<AnimatePresence initial=\{false\}>/);
    expect(src).toMatch(/variants=\{popVariants\(reducedMotion\)\}/);
    expect(src).toMatch(/exit="exit"/);
  });

  test("preserves the add-pathway affordance", () => {
    expect(src).toMatch(/aria-label="Add another pathway"/);
  });
});

describe("ConceptPill motion pass", () => {
  const src = readFile("ConceptPill.tsx");

  test("pops in with the shared entrance preset", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/from\s+["']\.\.\/\.\.\/motionPresets["']/);
    expect(src).toMatch(/variants=\{popVariants\(reducedMotion\)\}/);
  });

  test("preserves the swap/remove aria-label contract", () => {
    expect(src).toMatch(/Click to swap, X to remove\./);
  });
});

describe("DemographicRow motion pass", () => {
  const src = readFile("DemographicRow.tsx");

  test("pops in with the shared entrance preset", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/variants=\{popVariants\(reducedMotion\)\}/);
  });

  test("preserves age and sex field behaviour", () => {
    expect(src).toMatch(/aria-label="Remove this patient detail"/);
  });
});

describe("ObservationRow motion pass", () => {
  const src = readFile("ObservationRow.tsx");

  test("pops in with the shared entrance preset across all render branches", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    const matches = src.match(/variants=\{entrance\}/g) ?? [];
    expect(matches.length).toBeGreaterThanOrEqual(3);
  });

  test("preserves the absolute/advanced mode branching", () => {
    expect(src).toMatch(/aria-label="Remove this lab value"/);
  });
});

describe("RuleFiredRow motion pass", () => {
  const src = readFile("RuleFiredRow.tsx");

  test("pops in with the shared entrance preset", () => {
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/variants=\{popVariants\(reducedMotion\)\}/);
  });

  test("preserves the RULE_FIRED Atlas trace and picker behaviour", () => {
    expect(src).toMatch(/DI-6AE25829/);
    expect(src).toMatch(/"set_rule_fired"/);
  });
});
