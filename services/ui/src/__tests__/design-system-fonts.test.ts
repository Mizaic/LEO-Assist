/**
 * VT-LEO-AI-128: next/font typography + subtitle un-monospace.
 * Covers TC-001 (font config exported) and TC-002 (theme subtitles not mono).
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { FONT_CONFIG, FONT_VARIABLES } from "@leo/design-system/fonts";

describe("VT-128 - next/font wiring + subtitle un-monospace", () => {
  test("TC-001 design-system exposes font config", () => {
    expect(FONT_VARIABLES.body).toBe("--font-dm-sans");
    expect(FONT_VARIABLES.mono).toBe("--font-jetbrains-mono");
    expect(FONT_CONFIG.dmSans.subsets).toContain("latin");
    expect(FONT_CONFIG.dmSans.weights).toEqual(
      expect.arrayContaining(["400", "600"]),
    );
  });

  test("TC-002 theme.ts subtitles do not reference JetBrains Mono", () => {
    const source = readFileSync(
      join(__dirname, "..", "theme.ts"),
      "utf-8",
    );
    const subtitleBlock = source.match(
      /subtitle1:\s*\{[^}]*\}[\s\S]*?subtitle2:\s*\{[^}]*\}/,
    );
    expect(subtitleBlock).not.toBeNull();
    const block = subtitleBlock![0];
    expect(block).not.toMatch(/JetBrains Mono/);
    expect(block).not.toMatch(/FONT_MONO/);
    // And they DO reference the body font family (which resolves to DM Sans).
    expect(block).toMatch(/FONT_BODY|DM Sans|dm-sans/);
  });

  test("TC-002b layout.tsx applies dmSans variable to html", () => {
    const source = readFileSync(
      join(__dirname, "..", "app", "layout.tsx"),
      "utf-8",
    );
    expect(source).toMatch(/dmSans/);
    expect(source).toMatch(/dmSans\.variable/);
  });
});
