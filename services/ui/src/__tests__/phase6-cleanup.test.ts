/**
 * VT-LEO-AI-136 - Phase 6 zero-tech-debt cleanup verification.
 *
 * Source-level assertions that guard the rollout-flag removal, the
 * duplicate-primitive deletion, the Google-Fonts import removal, and
 * the presence of the sx colour-literal ESLint rule.
 */

import fs from "fs";
import path from "path";

const UI_ROOT = path.resolve(__dirname, "..", "..");
const SRC = path.join(UI_ROOT, "src");

function read(rel: string): string {
  return fs.readFileSync(path.join(UI_ROOT, rel), "utf8");
}

// Strip `//` and `/* */` comments so flag-absence assertions only
// look at executable code. We still want historical comments (like
// "the NEXT_PUBLIC_ROLE_FIRST rollout flag was removed in Phase 6")
// to document why the gate is unconditional.
function stripComments(src: string): string {
  const noBlock = src.replace(/\/\*[\s\S]*?\*\//g, "");
  return noBlock
    .split("\n")
    .map((line) => line.replace(/\/\/.*$/, ""))
    .join("\n");
}

describe("VT-LEO-AI-136 Phase 6 cleanup", () => {
  describe("TC-001 NEXT_PUBLIC_ROLE_FIRST flag removed", () => {
    test("next.config.mjs has no process.env.NEXT_PUBLIC_ROLE_FIRST read", () => {
      const src = stripComments(read("next.config.mjs"));
      expect(src).not.toMatch(/process\.env\.NEXT_PUBLIC_ROLE_FIRST/);
      expect(src).not.toMatch(/env:\s*\{[\s\S]*NEXT_PUBLIC_ROLE_FIRST/);
    });

    test("RoleShellProvider has no NEXT_PUBLIC_ROLE_FIRST branch", () => {
      const src = stripComments(read("src/components/RoleShellProvider.tsx"));
      expect(src).not.toMatch(/NEXT_PUBLIC_ROLE_FIRST/);
      expect(src).not.toMatch(/ROLE_FIRST_ENABLED/);
    });

    test("AppShell has no NEXT_PUBLIC_ROLE_FIRST branch", () => {
      const src = stripComments(read("src/components/AppShell.tsx"));
      expect(src).not.toMatch(/NEXT_PUBLIC_ROLE_FIRST/);
      expect(src).not.toMatch(/roleFirstEnabled/);
    });
  });

  describe("TC-002 Duplicate ProgressiveReveal deleted", () => {
    test("services/ui/src/components/ui/ProgressiveReveal.tsx is gone", () => {
      expect(
        fs.existsSync(
          path.join(SRC, "components", "ui", "ProgressiveReveal.tsx"),
        ),
      ).toBe(false);
    });

    test("explanation-patterns test imports from design system", () => {
      const src = read("src/__tests__/explanation-patterns.test.tsx");
      expect(src).not.toMatch(
        /from\s+['\"]@\/components\/ui\/ProgressiveReveal/,
      );
      expect(src).toMatch(/ProgressiveReveal[^]*from\s+['\"]@leo\/design-system/);
    });
  });

  describe("TC-003 Google Fonts @import removed from globals.css", () => {
    test("globals.css has no fonts.googleapis.com @import", () => {
      const src = read("src/app/globals.css");
      expect(src).not.toMatch(/@import\s+url\(['\"]https:\/\/fonts\.googleapis\.com/);
    });
  });

  describe("TC-004 sx colour-literal ESLint rule present", () => {
    const cfg = read("eslint.config.mjs");

    test("eslint.config.mjs restricts hex literals inside sx", () => {
      expect(cfg).toMatch(/no-restricted-syntax/);
      expect(cfg).toMatch(/JSXAttribute\[name\.name='sx'\]/);
      expect(cfg).toMatch(/#\[0-9a-fA-F\]/);
    });

    test("eslint.config.mjs restricts rgb/hsl literals inside sx", () => {
      expect(cfg).toMatch(/rgb|rgba|hsl|hsla/);
    });
  });
});
