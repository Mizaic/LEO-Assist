/**
 * VT-LEO-AI-233 -- GuidelinePicker primitive (static-source layer)
 *
 * Pins the contracts of the multi-select picker (DI-LEO-AI-233 /
 * DO-LEO-AI-233):
 *   - it is an MUI Autocomplete with multiple=true
 *   - the default loader URL is /api/nice/loaded
 *   - it exposes a "Use all loaded" toggle button
 */
import fs from "fs";
import path from "path";

const PRIMITIVE = path.resolve(
  __dirname,
  "..",
  "components",
  "sbar-playground",
  "GuidelinePicker.tsx",
);

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

describe("VT-LEO-AI-233 GuidelinePicker primitive", () => {
  it("uses MUI Autocomplete with multiple=true", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/<Autocomplete[\s\S]*multiple/);
  });

  it("default loader URL is /api/nice/loaded", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/fetch\("\/api\/nice\/loaded"\)/);
  });

  it("renders the 'Use all loaded' / 'Clear' toggle button", () => {
    const src = read(PRIMITIVE);
    expect(src).toContain("Use all loaded");
    expect(src).toContain("guideline-picker-toggle-all");
  });

  it("emits codes (string[]) on change", () => {
    const src = read(PRIMITIVE);
    expect(src).toMatch(/onChange\(next\.map\(\(g\) => g\.code\)\)/);
  });
});
