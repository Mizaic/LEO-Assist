/**
 * Static-source VT -- form schemas settings page.
 *
 * Verifies structural invariants without mounting the component:
 *   - imports StatHero from @leo/design-system
 *   - fetches from /api/form-schemas
 *   - reuses FormSchemaAnnotator for editing
 *   - settings page card links to /settings/form-schemas
 *   - supports fingerprint query param deep link
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */

import * as fs from "fs";
import * as path from "path";

const REPO = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO, rel), "utf8");
}

const PAGE = "services/ui/src/app/settings/form-schemas/page.tsx";
const DIALOG = "services/ui/src/app/settings/form-schemas/FormSchemaTeachDialog.tsx";
const SETTINGS = "services/ui/src/app/settings/page.tsx";

describe("form-schemas settings page chrome", () => {
  test("TC-001: imports StatHero from @leo/design-system", () => {
    const src = read(PAGE);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/StatHero/);
  });

  test("TC-002: reuses FormSchemaAnnotator", () => {
    const dialog = read(DIALOG);
    expect(dialog).toMatch(/FormSchemaAnnotator/);
  });

  test("TC-003: fetches from /api/form-schemas", () => {
    const src = read(PAGE);
    expect(src).toMatch(/\/api\/form-schemas/);
  });

  test("TC-004: dialog accepts fingerprint and sourceText props", () => {
    const dialog = read(DIALOG);
    expect(dialog).toMatch(/fingerprint/);
    expect(dialog).toMatch(/sourceText/);
  });

  test("TC-005: renders loading state", () => {
    const src = read(PAGE);
    expect(src).toMatch(/Loading form schemas/);
  });

  test("TC-006: renders empty state when no schemas", () => {
    const src = read(PAGE);
    expect(src).toMatch(/No taught form schemas yet/);
  });

  test("TC-007: renders no-match state when search returns nothing", () => {
    const src = read(PAGE);
    expect(src).toMatch(/No schemas match this search/);
  });

  test("TC-008: has exactly one h1", () => {
    const src = read(PAGE);
    const h1 = src.match(/component=["']h1["']/g) ?? [];
    expect(h1.length).toBe(1);
  });

  test("TC-009: search input has aria-label", () => {
    const src = read(PAGE);
    expect(src).toMatch(/aria-label.*[Ss]earch form schemas/);
  });

  test("TC-010: reads fingerprint from URL search params", () => {
    const src = read(PAGE);
    expect(src).toMatch(/useSearchParams/);
    expect(src).toMatch(/fingerprint/);
  });
});

describe("settings page includes form-schemas card", () => {
  test("TC-011: settings page links to /settings/form-schemas", () => {
    const src = read(SETTINGS);
    expect(src).toMatch(/\/settings\/form-schemas/);
  });

  test("TC-012: form-schemas card is not admin-only", () => {
    const src = read(SETTINGS);
    expect(src).not.toMatch(/adminOnly.*form-schemas/);
  });
});
