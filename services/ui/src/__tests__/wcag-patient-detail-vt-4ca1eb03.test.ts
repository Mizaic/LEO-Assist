/**
 * VT-4CA1EB03 -- Patient detail record view meets WCAG 2.1 AA (DI-05A16092).
 *
 * Static-source verification that the axe-core Playwright test for the patient
 * detail view exists, references the correct design control, and asserts the
 * acceptance criteria from DI-05A16092:
 *
 *   AC-1  axe-core reports zero critical or serious violations on the patient
 *         detail view.
 *   AC-2  The test checks exactly one h1 heading on the patient detail page.
 *   AC-3  The Playwright spec references DI-05A16092 in its test annotation.
 *   AC-4  The test navigates to the patient list first, then opens the first
 *         patient (navigation-through-UI pattern, not a hard-coded deep link).
 *   AC-5  The test uses @axe-core/playwright with wcag21aa tags.
 *
 * All assertions are static-source (no live render, no browser) so the test
 * is deterministic and runs in under 1 s.
 *
 * Atlas trace:
 *   VT: VT-4CA1EB03
 *   DO: DO-306D1FFB
 *   DI: DI-05A16092
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");
const A11Y_SPEC = "services/ui/e2e/a11y-baseline.spec.ts";

function readFile(rel: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, rel), "utf8");
}

function fileExists(rel: string): boolean {
  return fs.existsSync(path.join(REPO_ROOT, rel));
}

describe("VT-4CA1EB03 - Patient detail view WCAG 2.1 AA (DI-05A16092)", () => {
  let spec: string;

  beforeAll(() => {
    expect(fileExists(A11Y_SPEC)).toBe(true);
    spec = readFile(A11Y_SPEC);
  });

  test("AC-1: patient detail test asserts zero critical or serious axe violations", () => {
    expect(spec).toMatch(/patient detail view passes WCAG 2\.1 AA/i);
    expect(spec).toMatch(/impact === "critical"/);
    expect(spec).toMatch(/impact === "serious"/);
    expect(spec).toMatch(/toEqual\(\[\]\)/);
  });

  test("AC-2: patient detail test checks exactly one h1 on the page", () => {
    const detailBlock = spec.slice(
      spec.indexOf("patient detail view passes WCAG 2.1 AA"),
    );
    expect(detailBlock).toMatch(/h1/);
    expect(detailBlock).toMatch(/toBe\(1\)/);
  });

  test("AC-3: patient detail Playwright test references DI-05A16092 in its annotation", () => {
    expect(spec).toMatch(/DI-05A16092/);
  });

  test("AC-4: test navigates to patient list then opens first patient (no hard-coded ID)", () => {
    const detailBlock = spec.slice(
      spec.indexOf("patient detail view passes WCAG 2.1 AA"),
    );
    expect(detailBlock).toMatch(/\/care\/patients/);
    expect(detailBlock).toMatch(/a\[href\*=["']\/care\/patients\//);
    expect(detailBlock).not.toMatch(/\/care\/patients\/[a-f0-9-]{36}/);
  });

  test("AC-5: Playwright spec uses @axe-core/playwright with WCAG 2.1 AA tags", () => {
    expect(spec).toMatch(/@axe-core\/playwright|AxeBuilder/);
    expect(spec).toMatch(/wcag21aa/);
  });
});
