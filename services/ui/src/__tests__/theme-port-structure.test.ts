/**
 * VT-LEO-AI-140 -- TC-002 and TC-003.
 *
 * Pins the structural invariants of the theme-factory port:
 *   - ThemeRegistry imports createLeoTheme from @leo/design-system/theme
 *     and does NOT reach into @/theme.
 *   - services/ui/src/theme.ts is deleted and MUST NOT be recreated
 *     (the factory lives in the design-system workspace package).
 */

import fs from "fs";
import path from "path";

const UI_SRC = path.resolve(__dirname, "..");

describe("VT-140 TC-002 ThemeRegistry imports createLeoTheme from design-system", () => {
  const source = fs.readFileSync(
    path.join(UI_SRC, "components", "ThemeRegistry.tsx"),
    "utf-8",
  );

  it("imports createLeoTheme from @leo/design-system/theme", () => {
    expect(source).toMatch(
      /from\s+["']@leo\/design-system\/theme["']/,
    );
    expect(source).toMatch(/createLeoTheme/);
  });

  it("does not import from @/theme or a relative theme file", () => {
    expect(source).not.toMatch(/from\s+["']@\/theme["']/);
    expect(source).not.toMatch(/from\s+["']\.\.\/theme["']/);
    expect(source).not.toMatch(/from\s+["']\.\/theme["']/);
  });
});

describe("VT-140 TC-003 services/ui/src/theme.ts is removed", () => {
  it("theme.ts does not exist on disk", () => {
    const legacyPath = path.join(UI_SRC, "theme.ts");
    expect(fs.existsSync(legacyPath)).toBe(false);
  });
});
