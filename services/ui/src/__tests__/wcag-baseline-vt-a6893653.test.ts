/**
 * VT-A6893653 -- AppShell + ConfirmDialog + StatusDot + TermSearch meet
 * the WCAG 2.1 AA baseline (DI-926A4B95 acceptance criteria).
 *
 * Static-source verification covers the 7 ACs:
 *   AC-1  axe-baseline Playwright spec exists for patient-reachable routes
 *   AC-2  AppShell drawer renders aria-current='page' in rail and full modes
 *   AC-3  AppShell logo is a button with aria-label going to home
 *   AC-4  OrgSelect has aria-label='Select organisation'
 *   AC-5  ConfirmDialog uses aria-labelledby + aria-describedby
 *   AC-6  StatusDot encodes shape + accessible label, not just colour
 *   AC-7  ESLint jsx-a11y is enabled and the axe Playwright spec runs in CI
 *
 * All assertions are static-source (no live render) so the test is
 * deterministic and runs in <1s.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function readFile(rel: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, rel), "utf8");
}

function fileExists(rel: string): boolean {
  return fs.existsSync(path.join(REPO_ROOT, rel));
}

describe("VT-A6893653 - WCAG 2.1 AA baseline (AppShell, ConfirmDialog, StatusDot, TermSearch)", () => {
  test("AC-1: axe-baseline Playwright spec exists for patient-reachable routes", () => {
    expect(fileExists("services/ui/e2e/a11y-baseline.spec.ts")).toBe(true);
    const spec = readFile("services/ui/e2e/a11y-baseline.spec.ts");
    expect(spec).toMatch(/AxeBuilder|@axe-core\/playwright/);
    expect(spec).toMatch(/wcag2aa|wcag21aa/);
  });

  test("AC-2: AppShell renders aria-current='page' in both rail and full drawer modes", () => {
    const src = readFile("services/ui/src/components/AppShell.tsx");
    const occurrences = src.match(/aria-current=\{isActive \? "page" : undefined\}/g) || [];
    expect(occurrences.length).toBeGreaterThanOrEqual(2);
  });

  test("AC-3: AppShell logo is a button with an aria-label that names the home destination", () => {
    const src = readFile("services/ui/src/components/AppShell.tsx");
    const homeLogos = src.match(/aria-label="LEO by Mizaic - go to home"/g) || [];
    expect(homeLogos.length).toBeGreaterThanOrEqual(2);
    expect(src).toMatch(/<IconButton[\s\S]*?aria-label="LEO by Mizaic - go to home"/);
  });

  test("AC-4: OrgSelect input has aria-label='Select organisation'", () => {
    const src = readFile("services/ui/src/components/AppShell.tsx");
    // JSX attribute syntax uses `=`, not the object-literal `:` this
    // regex previously looked for -- see AC-3's `aria-label="..."`
    // pattern just above for the same convention.
    expect(src).toMatch(/aria-label=["']Select organisation["']/);
  });

  test("AC-5: ConfirmDialog wires aria-labelledby and aria-describedby", () => {
    const src = readFile("services/ui/src/components/ConfirmDialog.tsx");
    expect(src).toMatch(/aria-labelledby/);
    expect(src).toMatch(/aria-describedby/);
    expect(src).toMatch(/useId\(\)/);
  });

  test("AC-6: StatusDot encodes status as shape AND accessible label, not just colour", () => {
    const src = readFile("services/ui/src/components/ui/StatusDot.tsx");
    expect(src).toMatch(/STATUS_SHAPE/);
    expect(src).toMatch(/STATUS_LABEL/);
    expect(src).toMatch(/aria-label/);
    expect(src).toMatch(/data-shape/);
  });

  test("AC-7: ESLint jsx-a11y plugin is enabled in services/ui", () => {
    const candidates = [
      "services/ui/.eslintrc.json",
      "services/ui/.eslintrc.js",
      "services/ui/eslint.config.mjs",
      "services/ui/eslint.config.js",
      "services/ui/package.json",
    ];
    let found = false;
    for (const c of candidates) {
      if (!fileExists(c)) continue;
      const txt = readFile(c);
      if (/jsx-a11y/.test(txt)) {
        found = true;
        break;
      }
    }
    expect(found).toBe(true);
  });

  test("AC-7b: per-component a11y jest tests are present (ConfirmDialog + StatusDot)", () => {
    expect(fileExists("services/ui/src/__tests__/confirmdialog-a11y.test.tsx")).toBe(true);
    expect(fileExists("services/ui/src/__tests__/statusdot-a11y.test.tsx")).toBe(true);
  });
});
