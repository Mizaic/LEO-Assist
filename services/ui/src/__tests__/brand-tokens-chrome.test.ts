/**
 * Brand tokens and chrome -- static-source verification.
 *
 * Confirms the Mizaic wordmark, fonts, and forbidden legacy hex
 * are not used on in-scope UI surfaces.
 *
 * Atlas trace:
 *   VT: VT-F50C8CFF
 *   DO: DO-47454249
 *   DI: DI-E5FEF0AE
 *   Look up via: get_design_control(dc_type="verification-test", dc_id="VT-F50C8CFF")
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const REPO_ROOT = join(__dirname, "../../../..");
const UI_SRC = join(REPO_ROOT, "services/ui/src");
const DS_SRC = join(REPO_ROOT, "services/design-system/src");

const SKIP_DIR = new Set(["sbar-final", "node_modules", "__tests__"]);
const SKIP_FILE = new Set([
  "nerAnnotation.tsx",
  "letterMarkStyle.ts",
  "exportSbarPdf.ts",
  "sbarPdfMarkup.ts",
]);

const FORBIDDEN_HEX = /#1F3A8A|#1E40AF|#1D4ED8|#0F766E/i;

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const name of readdirSync(dir)) {
    if (SKIP_DIR.has(name)) continue;
    const full = join(dir, name);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      out.push(...walk(full));
      continue;
    }
    if (SKIP_FILE.has(name)) continue;
    if (!/\.(ts|tsx|css)$/.test(name)) continue;
    out.push(full);
  }
  return out;
}

function readRel(relPath: string): string {
  return readFileSync(join(REPO_ROOT, relPath), "utf8");
}

describe("brand tokens and chrome", () => {
  test("TC-001: no file under services/ui/src references /leo-icon.svg", () => {
    const hits = walk(UI_SRC).filter((file) =>
      readFileSync(file, "utf8").includes("/leo-icon.svg"),
    );
    expect(hits.map((file) => relative(REPO_ROOT, file))).toEqual([]);
  });

  test("TC-002: AppShell.tsx imports LeoLogo and LeoO from @leo/design-system", () => {
    const src = readRel("services/ui/src/components/AppShell.tsx");
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/LeoLogo/);
    expect(src).toMatch(/LeoO/);
  });

  test("TC-003: sign-in/page.tsx imports LeoLogo or LeoSplash from @leo/design-system", () => {
    const src = readRel("services/ui/src/app/sign-in/page.tsx");
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/LeoLogo|LeoSplash/);
  });

  test("TC-004: lib/fonts.ts uses Albert_Sans and Overpass, not DM_Sans", () => {
    const src = readRel("services/ui/src/lib/fonts.ts");
    expect(src).toMatch(/Albert_Sans/);
    expect(src).toMatch(/Overpass/);
    expect(src).not.toMatch(/DM_Sans/);
  });

  test("TC-005: no forbidden legacy brand hex outside excluded files", () => {
    const files = [...walk(UI_SRC), ...walk(DS_SRC)];
    const hits = files.filter((file) => FORBIDDEN_HEX.test(readFileSync(file, "utf8")));
    expect(hits.map((file) => relative(REPO_ROOT, file))).toEqual([]);
  });
});
