/**
 * VT-LEO-AI-171 -- Knowledge tabs ESLint + Playwright/axe guards (Wave E
 * Phase 7).
 *
 * Static-source sweep that confirms the ESLint guard for raw MUI
 * imports under admin/knowledge/** is present, and that the Playwright
 * spec at e2e/knowledge-tabs.spec.ts iterates the eight Knowledge tab
 * keys with axe-core WCAG 2.0/2.1 AA assertions.
 */

import { readFileSync } from "fs";
import { resolve } from "path";

const ROOT = resolve(__dirname, "../..");

const KNOWLEDGE_TABS = [
  "training-data",
  "surface-forms",
  "context-rules",
  "ai-instructions",
  "clinical-guidelines",
  "pathways",
  "domains",
  "terminology",
  "results-labs",
] as const;

describe("VT-LEO-AI-171 knowledge tabs guards", () => {
  test("VT-171-TC-001 ESLint flat config carries the admin/knowledge guard", () => {
    const cfg = readFileSync(
      resolve(ROOT, "eslint.config.mjs"),
      "utf8",
    );
    expect(cfg).toMatch(
      /files:\s*\[\s*"src\/app\/admin\/knowledge\/\*\*\/\*\.\{ts,tsx\}"\s*\]/,
    );
    expect(cfg).toMatch(/no-restricted-imports/);
    expect(cfg).toMatch(/group:\s*\[\s*"@mui\/\*"\s*\]/);
  });

  test("VT-171-TC-002 Playwright spec iterates the eight Knowledge tabs", () => {
    const spec = readFileSync(
      resolve(ROOT, "e2e/knowledge-tabs.spec.ts"),
      "utf8",
    );
    for (const tab of KNOWLEDGE_TABS) {
      expect(spec).toMatch(new RegExp(`"${tab}"`));
    }
    expect(spec).toMatch(/AxeBuilder/);
    expect(spec).toMatch(/wcag2aa/);
    expect(spec).toMatch(/wcag21aa/);
  });
});
