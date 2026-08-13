/**
 * Static-source verification for the LogicTreeEditor GroupBody + AddBar
 * motion pass (animated add/remove/reorder, collapse reveal, hover/tap
 * springs on the dashed add buttons). Cosmetic-only change -- see
 * atlas-vt-enforcement.mdc Step 0.
 */

import * as fs from "fs";
import * as path from "path";

const GROUP_BODY_SRC = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/EditRuleDialog/LogicTreeEditor/GroupBody.tsx",
);
const ADD_BAR_SRC = path.resolve(
  __dirname,
  "../../../../services/ui/src/app/admin/guidance/EditRuleDialog/LogicTreeEditor/AddBar.tsx",
);

function readGroupBody(): string {
  return fs.readFileSync(GROUP_BODY_SRC, "utf8");
}

function readAddBar(): string {
  return fs.readFileSync(ADD_BAR_SRC, "utf8");
}

describe("GroupBody motion pass", () => {
  test("imports framer-motion, useMotion, and the shared popVariants preset", () => {
    const src = readGroupBody();
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/AnimatePresence/);
    expect(src).toMatch(/motion as fm/);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/from\s+["']\.\.\/\.\.\/motionPresets["']/);
    expect(src).toMatch(/popVariants/);
  });

  test("reads reducedMotion from useMotion()", () => {
    const src = readGroupBody();
    expect(src).toMatch(/const\s*\{\s*reducedMotion\s*\}\s*=\s*useMotion\(\)/);
  });

  test("wraps child nodes in AnimatePresence with pop-in/pop-out variants", () => {
    const src = readGroupBody();
    expect(src).toMatch(/<AnimatePresence initial=\{false\}>/);
    expect(src).toMatch(/variants=\{popVariants\(reducedMotion\)\}/);
    expect(src).toMatch(/exit="exit"/);
  });

  test("animates the group reveal when expanding from a collapsed state", () => {
    const src = readGroupBody();
    expect(src).toMatch(/\{!collapsed && \(\s*<fm\.div/);
  });

  test("animates the collapse chevron rotation", () => {
    const src = readGroupBody();
    expect(src).toMatch(/animate=\{\{\s*rotate:\s*collapsed \? 0 : 90\s*\}\}/);
  });

  test("preserves the collapse/expand and remove affordances", () => {
    const src = readGroupBody();
    expect(src).toMatch(/aria-label=\{collapsed \? "Expand group" : "Collapse group"\}/);
    expect(src).toMatch(/aria-label="Remove this sub-group"/);
  });
});

describe("AddBar motion pass", () => {
  test("imports framer-motion, useMotion, and the shared bounceInteraction preset", () => {
    const src = readAddBar();
    expect(src).toMatch(/from\s+["']framer-motion["']/);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/from\s+["']\.\.\/\.\.\/motionPresets["']/);
    expect(src).toMatch(/bounceInteraction/);
  });

  test("applies springy hover/tap feedback to every dashed add button", () => {
    const src = readAddBar();
    const wrapCount = (src.match(/<fm\.div style=\{\{ display: "inline-flex" \}\} \{\.\.\.spring\}>/g) ?? [])
      .length;
    expect(wrapCount).toBeGreaterThanOrEqual(2);
  });

  test("preserves all four add actions and their aria-labels", () => {
    const src = readAddBar();
    expect(src).toMatch(/aria-label="Add a symptom, sign, procedure, or situation"/);
    expect(src).toMatch(/aria-label="Add a patient detail"/);
    expect(src).toMatch(/aria-label="Add a lab value or reading"/);
    expect(src).toMatch(/aria-label="Add a rule dependency"/);
    expect(src).toMatch(/aria-label="Add things the patient should not have"/);
  });
});
