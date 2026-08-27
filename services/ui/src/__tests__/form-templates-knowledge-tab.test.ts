/**
 * Static-source VT -- Form templates on the Admin Knowledge tab.
 *
 * Verifies:
 *   - Knowledge sidebar and TABS list include a Form templates item
 *   - URL contract is /admin/knowledge?tab=form-templates
 *   - The tab reuses the settings form-schemas page (no CRUD copy)
 *   - /settings/form-schemas stays available
 *
 * Atlas trace: DI-5C9CA57B, DI-26546721
 */

import * as fs from "fs";
import * as path from "path";

const REPO = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO, rel), "utf8");
}

const KNOWLEDGE = "services/ui/src/app/admin/knowledge/page.tsx";
const SIDEBAR = "services/ui/src/components/ui/KnowledgeSidebar.tsx";
const COPY = "services/ui/src/lib/knowledgeCopy.ts";
const ADMIN_PAGE = "services/ui/src/app/admin/form-schemas/page.tsx";
const SETTINGS_PAGE = "services/ui/src/app/settings/form-schemas/page.tsx";
const SETTINGS_HUB = "services/ui/src/app/settings/page.tsx";

describe("Form templates on Admin Knowledge tab", () => {
  test("TC-001: Knowledge TABS lists Form templates with form-templates key", () => {
    const src = read(KNOWLEDGE);
    expect(src).toMatch(/key:\s*["']form-templates["']/);
    expect(src).toMatch(/label:\s*["']Form templates["']/);
  });

  test("TC-002: Knowledge URL contract is /admin/knowledge?tab=form-templates", () => {
    const src = read(KNOWLEDGE);
    expect(src).toMatch(/\/admin\/knowledge\?tab=\$\{/);
    expect(src).toMatch(/["']form-templates["']/);
  });

  test("TC-003: Knowledge sidebar shows Form templates", () => {
    const src = read(SIDEBAR);
    expect(src).toMatch(/key:\s*["']form-templates["']/);
    expect(src).toMatch(/label:\s*["']Form templates["']/);
  });

  test("TC-004: tab reuses settings form-schemas page without duplicating CRUD", () => {
    const knowledge = read(KNOWLEDGE);
    const admin = read(ADMIN_PAGE);
    expect(knowledge).toMatch(/admin\/form-schemas\/page/);
    expect(admin).toMatch(/from\s+["']@\/app\/settings\/form-schemas\/page["']/);
    expect(admin).not.toMatch(/fetchFormSchemas/);
    expect(admin).not.toMatch(/deleteFormSchema/);
  });

  test("TC-005: /settings/form-schemas remains a working settings card", () => {
    const hub = read(SETTINGS_HUB);
    const page = read(SETTINGS_PAGE);
    expect(hub).toMatch(/\/settings\/form-schemas/);
    expect(hub).toMatch(/Form templates/);
    expect(page).toMatch(/data-testid=["']form-schemas-page["']/);
  });

  test("TC-006: KnowledgeTabKey and copy include form-templates", () => {
    const src = read(COPY);
    expect(src).toMatch(/["']form-templates["']/);
    expect(src).toMatch(/"form-templates"\s*:/);
    expect(src).toMatch(/Form templates/);
  });
});
