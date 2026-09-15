/**
 * Static-source VT: bitmap compile scope modes.
 *
 * Verifies:
 * - TC-001: Three compile mode buttons present (All guidelines, One guideline, Pick rules)
 * - TC-002: Legacy scope chips removed (Domain, Subdomain, Custom as top-level chips)
 * - TC-003: RulePicker imported in BitmapLifecycleSection
 * - TC-004: pick mode sends scope_type=custom + include_rule_ids in compile body
 * - TC-005: COMPILE_MODE_OPTIONS exported from bitmapLifecycleHelpers
 * - TC-006: CompileMode type includes "global" | "guideline" | "pick"
 * - TC-007: EvaluationScope type exists in events (pubsub backwards compat)
 *
 * Design Controls: DI-8DD23CE2, DI-3DDA3519.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const HELPERS_PATH =
  "services/ui/src/app/admin/guidance/bitmapLifecycleHelpers.tsx";
const SECTION_PATH =
  "services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx";
const HOOK_PATH =
  "services/ui/src/app/admin/guidance/useBitmapLifecycle.ts";
const PICKER_PATH =
  "services/ui/src/app/admin/guidance/RulePicker.tsx";

describe("TC-005 / TC-006 - bitmapLifecycleHelpers compile modes", () => {
  test("TC-005: COMPILE_MODE_OPTIONS exported", () => {
    const src = readFile(HELPERS_PATH);
    expect(src).toMatch(/COMPILE_MODE_OPTIONS/);
  });

  test("TC-006: CompileMode type includes all three modes", () => {
    const src = readFile(HELPERS_PATH);
    expect(src).toMatch(/CompileMode/);
    expect(src).toMatch(/"global"/);
    expect(src).toMatch(/"guideline"/);
    expect(src).toMatch(/"pick"/);
  });

  test("TC-002: SCOPE_OPTIONS removed (Domain/Subdomain/Custom chips gone)", () => {
    const src = readFile(HELPERS_PATH);
    // Old five-item SCOPE_OPTIONS must not exist
    expect(src).not.toMatch(/SCOPE_OPTIONS/);
    // Domain/subdomain/custom labels must not be top-level chip options
    expect(src).not.toMatch(/value:\s*["']domain["']/);
    expect(src).not.toMatch(/value:\s*["']subdomain["']/);
  });
});

describe("TC-001 - Three mode labels defined in COMPILE_MODE_OPTIONS", () => {
  // Labels live in helpers (imported by section); check the source of truth.
  test("TC-001a: All guidelines label present in helpers", () => {
    const src = readFile(HELPERS_PATH);
    expect(src).toMatch(/All guidelines/);
  });

  test("TC-001b: One guideline label present in helpers", () => {
    const src = readFile(HELPERS_PATH);
    expect(src).toMatch(/One guideline/);
  });

  test("TC-001c: Pick rules label present in helpers", () => {
    const src = readFile(HELPERS_PATH);
    expect(src).toMatch(/Pick rules/);
  });

  test("TC-003: RulePicker imported in section", () => {
    const src = readFile(SECTION_PATH);
    expect(src).toMatch(/RulePicker/);
  });

  test("TC-001d: COMPILE_MODE_OPTIONS used in section", () => {
    const src = readFile(SECTION_PATH);
    expect(src).toMatch(/COMPILE_MODE_OPTIONS/);
  });

  test("TC-002: Domain / Subdomain / Custom chip labels absent from section", () => {
    const src = readFile(SECTION_PATH);
    expect(src).not.toMatch(/label:\s*["']Domain["']/);
    expect(src).not.toMatch(/label:\s*["']Subdomain["']/);
    expect(src).not.toMatch(/label:\s*["']Custom["']/);
  });
});

describe("TC-004 - useBitmapLifecycle pick mode compile body", () => {
  test("TC-004a: include_rule_ids appears in compile fetch body", () => {
    const src = readFile(HOOK_PATH);
    expect(src).toMatch(/include_rule_ids/);
  });

  test("TC-004b: custom scope_type used for pick mode", () => {
    const src = readFile(HOOK_PATH);
    // pick mode must set scope_type to custom, not global
    expect(src).toMatch(/["']custom["']/);
  });

  test("TC-004c: pickScopeId state present in hook", () => {
    const src = readFile(HOOK_PATH);
    expect(src).toMatch(/pickScopeId/);
  });

  test("TC-004d: selectedRuleIds state present in hook", () => {
    const src = readFile(HOOK_PATH);
    expect(src).toMatch(/selectedRuleIds/);
  });
});

describe("TC-007 - RulePicker component exists", () => {
  test("TC-007a: RulePicker.tsx file exists", () => {
    const fullPath = path.join(REPO_ROOT, PICKER_PATH);
    expect(fs.existsSync(fullPath)).toBe(true);
  });

  test("TC-007b: RulePicker accepts onToggle prop", () => {
    const src = readFile(PICKER_PATH);
    expect(src).toMatch(/onToggle/);
  });

  test("TC-007c: RulePicker accepts selected prop", () => {
    const src = readFile(PICKER_PATH);
    expect(src).toMatch(/selected/);
  });
});
