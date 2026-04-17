/**
 * VT-LEO-AI-169 -- AI Instructions editor decomposition (Wave E Phase 4b)
 *
 * Static-source sweep that verifies services/ui/src/app/admin/prompts/[id]
 * has been decomposed into an orchestrator plus dedicated tab body
 * components, with no module exceeding the 500 LOC hard cap.
 */

import { existsSync, readFileSync } from "fs";
import { resolve } from "path";

const ROOT = resolve(__dirname, "../app/admin/prompts/[id]");
const COMPONENTS = resolve(ROOT, "_components");

const REQUIRED_MODULES = [
  "types.ts",
  "IdentitySection.tsx",
  "InstructionsTab.tsx",
  "OutputFormatTab.tsx",
  "TeachingExamplesTab.tsx",
  "SandboxTab.tsx",
  "SandboxCostTable.tsx",
  "ExampleCard.tsx",
  "InputDisplay.tsx",
  "OutputPreview.tsx",
] as const;

const SHARED_TYPE_EXPORTS = [
  "CATEGORY_OPTIONS",
  "SCOPE_OPTIONS",
  "TAG_COLORS",
  "ASSERTION_COLORS",
  "categoryLabel",
  "categoryColor",
  "FewShotExample",
  "PromptConfigData",
  "CostEstimate",
  "SandboxResult",
  "PresetItem",
] as const;

const TAB_IMPORT_NAMES = [
  "IdentitySection",
  "InstructionsTab",
  "OutputFormatTab",
  "TeachingExamplesTab",
  "SandboxTab",
] as const;

const HARD_LOC_CAP = 500;

function loc(file: string): number {
  return readFileSync(file, "utf8").split(/\r?\n/).length;
}

describe("VT-LEO-AI-169 prompts editor decomposition", () => {
  test("VT-169-TC-001 required _components modules exist", () => {
    for (const mod of REQUIRED_MODULES) {
      const path = resolve(COMPONENTS, mod);
      expect(existsSync(path)).toBe(true);
      expect(readFileSync(path, "utf8").trim().length).toBeGreaterThan(0);
    }
  });

  test("VT-169-TC-002 orchestrator + components stay under 500 LOC", () => {
    const orchestrator = resolve(ROOT, "page.tsx");
    expect(loc(orchestrator)).toBeLessThanOrEqual(HARD_LOC_CAP);
    for (const mod of REQUIRED_MODULES) {
      expect(loc(resolve(COMPONENTS, mod))).toBeLessThanOrEqual(HARD_LOC_CAP);
    }
  });

  test("VT-169-TC-003 orchestrator imports tab bodies from _components", () => {
    const src = readFileSync(resolve(ROOT, "page.tsx"), "utf8");
    for (const name of TAB_IMPORT_NAMES) {
      const importPattern = new RegExp(
        String.raw`import\s*\{[^}]*\b${name}\b[^}]*\}\s*from\s*"\./_components/`,
      );
      expect(src).toMatch(importPattern);
    }
  });

  test("VT-169-TC-004 shared types module exposes single source of truth", () => {
    const src = readFileSync(resolve(COMPONENTS, "types.ts"), "utf8");
    for (const exportName of SHARED_TYPE_EXPORTS) {
      expect(src).toMatch(new RegExp(String.raw`\b${exportName}\b`));
    }
  });
});
