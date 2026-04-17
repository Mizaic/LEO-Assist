/**
 * Fast-fail CI guard: ensures no source file under src/ contains a
 * hardcoded reference to a deprecated admin URL.
 *
 * The deprecated URLs have been replaced in the UI by consolidated sections:
 *   /admin/operations -> /admin/console
 *   /admin/gold-dataset -> /admin/knowledge?tab=training-data
 *   /admin/surface-forms -> /admin/knowledge?tab=surface-forms
 *   /admin/context-rules -> /admin/knowledge?tab=context-rules
 *   /admin/prompts (standalone nav) -> /admin/knowledge?tab=ai-instructions
 *   /admin/guidance -> /admin/knowledge?tab=clinical-guidelines
 *   /admin/clinical (merged into Knowledge) -> /admin/knowledge
 *   /admin/pathways (standalone nav) -> /admin/knowledge?tab=pathways
 *   /admin/domains -> /admin/knowledge?tab=domains
 *   /admin/terminology -> /admin/knowledge?tab=terminology
 *   /admin/billing -> /admin/platform?tab=billing
 *   /admin/models -> /admin/platform?tab=model-config
 *   /admin/data-quality -> /admin/platform?tab=data-quality
 *
 * If this test fails: update the offending file to use the new URL.
 * Do NOT add exceptions to the allowlist below without strong justification.
 */

import fs from "fs";
import path from "path";

// -- Configuration -----------------------------------------------------------

const SRC_ROOT = path.resolve(__dirname, "..");

const DEPRECATED_PATTERNS = [
  // Must not appear as a standalone navigation target
  '"/admin/operations"',
  '"/admin/gold-dataset"',
  '"/admin/surface-forms"',
  '"/admin/context-rules"',
  '"/admin/guidance"',
  '"/admin/clinical"',
  '"/admin/clinical?',
  '"/admin/pathways"',
  '"/admin/domains"',
  '"/admin/terminology"',
  '"/admin/billing"',
  '"/admin/models"',
  '"/admin/data-quality"',
];

// Files explicitly allowed to contain old URLs (e.g. next.config redirects,
// the redirect pages themselves, or this test file).
const ALLOWED_FILES = new Set([
  // The actual page files that still physically exist at the old paths
  // (they are either re-exports or empty shells with redirects)
  "app/admin/gold-dataset/page.tsx",
  "app/admin/surface-forms/page.tsx",
  "app/admin/context-rules/page.tsx",
  "app/admin/guidance/page.tsx",
  "app/admin/pathways/page.tsx",
  "app/admin/domains/page.tsx",
  "app/admin/terminology/page.tsx",
  "app/admin/billing/page.tsx",
  "app/admin/models/page.tsx",
  "app/admin/data-quality/page.tsx",
  "app/admin/operations/page.tsx",
  // The prompts standalone page still exists (deep-link to edit prompts)
  "app/admin/prompts/page.tsx",
  // AppShell.tsx uses old URLs only in activePrefix arrays for route-matching,
  // not as navigation targets. The nav items themselves point to new URLs.
  "components/AppShell.tsx",
  // This audit file itself
  "__tests__/admin-url-audit.test.ts",
  // Phase 2 IA merge verification test: asserts redirects for the legacy
  // /admin/clinical URLs, so references to those URLs are expected here.
  "__tests__/knowledge-hub-merge.test.ts",
]);

// -- Helpers -----------------------------------------------------------------

function* walkFiles(dir: string): Generator<string> {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === ".next") continue;
      yield* walkFiles(full);
    } else if (entry.isFile() && /\.(tsx?|jsx?|mjs)$/.test(entry.name)) {
      yield full;
    }
  }
}

function relPath(abs: string): string {
  return path.relative(SRC_ROOT, abs).replace(/\\/g, "/");
}

// -- Tests -------------------------------------------------------------------

describe("Admin URL audit — deprecated routes", () => {
  const violations: string[] = [];

  beforeAll(() => {
    for (const file of walkFiles(SRC_ROOT)) {
      const rel = relPath(file);
      if ([...ALLOWED_FILES].some((a) => rel.endsWith(a))) continue;

      const content = fs.readFileSync(file, "utf-8");
      for (const pattern of DEPRECATED_PATTERNS) {
        if (content.includes(pattern)) {
          violations.push(`${rel}: contains deprecated URL ${pattern}`);
        }
      }
    }
  });

  it("contains no hardcoded deprecated admin URLs in src/", () => {
    if (violations.length > 0) {
      const msg = [
        `Found ${violations.length} deprecated admin URL(s) in source files.`,
        "Update each file to use the new consolidated URL.",
        "",
        ...violations,
      ].join("\n");
      throw new Error(msg);
    }
  });
});
