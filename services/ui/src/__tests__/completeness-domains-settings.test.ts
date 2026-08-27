/**
 * Static-source VT -- completeness domains settings page.
 *
 * Verifies structural invariants without mounting the component:
 *   - imports StatHero from @leo/design-system
 *   - renders loading, empty, and no-match states
 *   - fetches from /api/completeness-domains/
 *   - saves to /api/completeness-domains/{domain_id} via PUT
 *   - reuses FormSchemaCompletenessEditor
 *   - settings page card links to /settings/completeness-domains
 *
 * Atlas trace: UN-3B25A20E, DI-26546721
 */

import * as fs from "fs";
import * as path from "path";

const REPO = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO, rel), "utf8");
}

const PAGE = "services/ui/src/app/settings/completeness-domains/page.tsx";
const SETTINGS = "services/ui/src/app/settings/page.tsx";

describe("completeness-domains settings page chrome", () => {
  test("TC-001: imports StatHero from @leo/design-system", () => {
    const src = read(PAGE);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/StatHero/);
  });

  test("TC-002: reuses FormSchemaCompletenessEditor", () => {
    const src = read(PAGE);
    expect(src).toMatch(/FormSchemaCompletenessEditor/);
    expect(src).toMatch(/formSchemaTeach/);
  });

  test("TC-003: fetches from /api/completeness-domains/", () => {
    const src = read(PAGE);
    expect(src).toMatch(/\/api\/completeness-domains\//);
  });

  test("TC-004: PUT save call targets domain_id endpoint", () => {
    const src = read(PAGE);
    expect(src).toMatch(/completeness-domains\//);
    expect(src).toMatch(/method:\s*["']PUT["']/);
  });

  test("TC-005: renders loading state", () => {
    const src = read(PAGE);
    expect(src).toMatch(/Loading domains/);
  });

  test("TC-006: renders empty state when no domains", () => {
    const src = read(PAGE);
    expect(src).toMatch(/No completeness domains yet/);
  });

  test("TC-007: renders no-match state when search returns nothing", () => {
    const src = read(PAGE);
    expect(src).toMatch(/No domains match this search/);
  });

  test("TC-008: has exactly one h1", () => {
    const src = read(PAGE);
    const h1 = src.match(/component=["']h1["']/g) ?? [];
    expect(h1.length).toBe(1);
  });

  test("TC-009: search input has aria-label", () => {
    const src = read(PAGE);
    expect(src).toMatch(/aria-label.*[Ss]earch completeness domains/);
  });

  test("TC-010: edit button has aria-label for accessibility", () => {
    const src = read(PAGE);
    expect(src).toMatch(/aria-label/);
  });
});

describe("settings page includes completeness-domains card", () => {
  test("TC-011: settings page links to /settings/completeness-domains", () => {
    const src = read(SETTINGS);
    expect(src).toMatch(/\/settings\/completeness-domains/);
  });

  test("TC-012: completeness-domains card is admin-only", () => {
    const src = read(SETTINGS);
    expect(src).toMatch(/adminOnly.*completeness-domains|completeness-domains.*adminOnly/s);
  });
});

describe("admin router source", () => {
  const ROUTER = "services/api/app/routers/completeness_domains.py";

  test("TC-013: router has GET list endpoint", () => {
    const src = read(ROUTER);
    expect(src).toMatch(/@router\.get\(["']["']\)/);
  });

  test("TC-014: router has GET detail endpoint", () => {
    const src = read(ROUTER);
    expect(src).toMatch(/@router\.get\(["']\/{domain_id}["']\)/);
  });

  test("TC-015: router has PUT endpoint", () => {
    const src = read(ROUTER);
    expect(src).toMatch(/@router\.put\(["']\/{domain_id}["']\)/);
  });

  test("TC-016: router requires admin role", () => {
    const src = read(ROUTER);
    expect(src).toMatch(/require_admin/);
  });

  test("TC-017: router calls ensure_service_completeness_domain", () => {
    const src = read(ROUTER);
    expect(src).toMatch(/ensure_service_completeness_domain/);
  });
});
