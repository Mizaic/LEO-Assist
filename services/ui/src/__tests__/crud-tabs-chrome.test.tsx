/**
 * VT-LEO-AI-145 -- Wave E Phase 3
 *
 * Verifies that the four CRUD Knowledge tabs (Context Rules, Surface
 * Forms, Domains, Terminology) have been redesigned onto the shared
 * @leo/design-system primitives. Each page is a standalone Next.js
 * route with its own data-loading lifecycle, so the test does a
 * static-source scan rather than a full render -- consistent with the
 * VT-LEO-AI-142 chrome verification approach for Phase 2a.
 *
 * Acceptance criteria (per DI-LEO-AI-147):
 *   - All four pages import the canonical chrome primitives from
 *     @leo/design-system rather than building bespoke chrome on @mui.
 *   - The legacy page-owned chrome (Breadcrumbs, top-level h5 page
 *     title, Box maxWidth wrapper) has been removed -- KnowledgePageLayout
 *     supplies that upstream.
 *   - The redesigned page bodies still wire to the same data clients
 *     and handlers (no behaviour regression).
 */
import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "..", "app", "settings");

const PAGES = {
  contextRules: path.join(ROOT, "context-rules", "page.tsx"),
  surfaceForms: path.join(ROOT, "surface-forms", "page.tsx"),
  domains: path.join(ROOT, "domains", "page.tsx"),
  terminology: path.join(ROOT, "terminology", "page.tsx"),
};

function read(p: string): string {
  return fs.readFileSync(p, "utf8");
}

function importBlock(src: string): string {
  const match = src.match(/import\s*\{[^}]*\}\s*from\s*"@leo\/design-system"/);
  return match ? match[0] : "";
}

describe("VT-LEO-AI-145 CRUD tabs chrome on design-system primitives", () => {
  let contextRules: string;
  let surfaceForms: string;
  let domains: string;
  let terminology: string;

  beforeAll(() => {
    contextRules = read(PAGES.contextRules);
    surfaceForms = read(PAGES.surfaceForms);
    domains = read(PAGES.domains);
    terminology = read(PAGES.terminology);
  });

  // -- TC-001 Imports ------------------------------------------------------

  it("TC-001a Context Rules imports the right primitives", () => {
    const block = importBlock(contextRules);
    expect(block).toMatch(/\bStatHero\b/);
    expect(block).toMatch(/\bSegmentedTabs\b/);
    expect(block).toMatch(/\bToolbarActions\b/);
    expect(block).toMatch(/\bReviewListCard\b/);
    expect(block).toMatch(/\bProgressiveReveal\b/);
  });

  it("TC-001b Surface Forms imports the right primitives", () => {
    const block = importBlock(surfaceForms);
    expect(block).toMatch(/\bStatHero\b/);
    expect(block).toMatch(/\bSegmentedTabs\b/);
    expect(block).toMatch(/\bToolbarActions\b/);
    expect(block).toMatch(/\bEmptyState\b/);
  });

  it("TC-001c Domains imports the right primitives", () => {
    const block = importBlock(domains);
    expect(block).toMatch(/\bStatHero\b/);
    expect(block).toMatch(/\bSegmentedTabs\b/);
    expect(block).toMatch(/\bToolbarActions\b/);
  });

  it("TC-001d Terminology imports the right primitives", () => {
    const block = importBlock(terminology);
    expect(block).toMatch(/\bStatHero\b/);
    expect(block).toMatch(/\bToolbarActions\b/);
  });

  // -- TC-002 Legacy chrome removed ---------------------------------------

  it("TC-002a Context Rules removes the legacy Breadcrumbs + h5 page title", () => {
    expect(contextRules).not.toMatch(/<Breadcrumbs\b/);
    expect(contextRules).not.toMatch(/variant="h5"[\s\S]{0,80}Context rules/);
  });

  it("TC-002b Surface Forms removes the legacy Breadcrumbs + h5 page title", () => {
    expect(surfaceForms).not.toMatch(/<Breadcrumbs\b/);
    expect(surfaceForms).not.toMatch(/variant="h5"[\s\S]{0,80}Surface Forms/);
  });

  it("TC-002c Domains removes the legacy back-button + h5 page title", () => {
    expect(domains).not.toMatch(/Domain Configuration/);
    expect(domains).not.toMatch(
      /IconButton[^>]*Back to settings[\s\S]{0,200}variant="h5"/,
    );
  });

  it("TC-002d Terminology removes the legacy Breadcrumbs + h5 page title", () => {
    expect(terminology).not.toMatch(/<Breadcrumbs\b/);
    expect(terminology).not.toMatch(/variant="h5"[\s\S]{0,80}Terminology/);
  });

  // -- TC-003 Behaviour preserved -----------------------------------------

  it("TC-003a Context Rules still wires loadRules + handleAdd + handleDeactivate", () => {
    expect(contextRules).toMatch(/const\s+loadRules\s*=\s*useCallback/);
    expect(contextRules).toMatch(/const\s+handleAdd\s*=\s*useCallback/);
    expect(contextRules).toMatch(/const\s+handleDeactivate\s*=\s*useCallback/);
    expect(contextRules).toMatch(/exportContextRulesPdf/);
  });

  it("TC-003b Surface Forms still wires phrase mapping handlers", () => {
    expect(surfaceForms).toMatch(/handleSave/);
    expect(surfaceForms).toMatch(/handlePublish/);
    expect(surfaceForms).toMatch(/Create local concept/);
    const hook = read(path.join(ROOT, "surface-forms", "usePhraseMappings.ts"));
    expect(hook).toMatch(/savePhraseDraft/);
    expect(hook).toMatch(/publishPhrase/);
  });

  it("TC-003c Domains still wires loadDomains + createDomain", () => {
    expect(domains).toMatch(/loadDomains\s*\(/);
    expect(domains).toMatch(/createDomain\s*\(/);
  });

  it("TC-003d Terminology still wires fetchStatus + startSync + cancelSync", () => {
    expect(terminology).toMatch(/const\s+fetchStatus\s*=\s*useCallback/);
    expect(terminology).toMatch(/const\s+startSync\s*=\s*useCallback/);
    expect(terminology).toMatch(/const\s+cancelSync\s*=/);
    expect(terminology).toMatch(/EventSource\(/);
  });

  // -- TC-004 Single primary action per page -----------------------------

  it("TC-004a Context Rules ToolbarActions exposes Export PDF + Add rule", () => {
    expect(contextRules).toMatch(/id:\s*"export-pdf"/);
    expect(contextRules).toMatch(/id:\s*"add-rule"/);
  });

  it("TC-004b Surface Forms ToolbarActions exposes Change log + Create local concept", () => {
    expect(surfaceForms).toMatch(/id:\s*"audit-log"/);
    expect(surfaceForms).toMatch(/id:\s*"create-local-concept"/);
  });

  it("TC-004c Domains ToolbarActions exposes Create area for platform admins", () => {
    expect(domains).toMatch(/id:\s*"create-area"/);
    expect(domains).toMatch(/showCreateButton/);
  });

  it("TC-004d Terminology ToolbarActions exposes Refresh", () => {
    expect(terminology).toMatch(/id:\s*"refresh-status"/);
  });

  // -- TC-005 Body primitive per page ------------------------------------

  it("TC-005a Context Rules renders ReviewListCard for the rules body", () => {
    expect(contextRules).toMatch(/<ReviewListCard\b/);
    expect(contextRules).toMatch(/<ProgressiveReveal\b/);
  });

  it("TC-005b Surface Forms uses a live dictionary FilterBar", () => {
    const live = read(path.join(ROOT, "surface-forms", "LiveDictionaryPane.tsx"));
    expect(live).toMatch(/<FilterBar\b/);
  });

  it("TC-005c Domains uses framer-motion card grid (DomainCard)", () => {
    expect(domains).toMatch(/function DomainCard/);
    expect(domains).toMatch(/from\s+"framer-motion"/);
    expect(domains).toMatch(/data-testid="domains-grid"/);
  });

  it("TC-005d Terminology renders tone-accented PackageCards + LogPanel", () => {
    expect(terminology).toMatch(/function PackageCard/);
    expect(terminology).toMatch(/function LogPanel/);
    expect(terminology).toMatch(/data-testid="terminology-log-panel"/);
  });
});
