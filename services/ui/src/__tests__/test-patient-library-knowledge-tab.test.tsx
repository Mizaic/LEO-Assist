/**
 * VT-5BDFE5F7 -- Knowledge tab Test Patients surface, Phase A.
 *
 * Static-source verification of:
 *   - The Knowledge page registers the Test Patients tab (tab key,
 *     label, panel binding).
 *   - The Knowledge tab copy carries plain-English "default" /
 *     "clinician" / "staff" intro blocks (UK reading age 11 audience
 *     standard from .cursor/rules/health-literacy.mdc).
 *   - The new /admin/knowledge/test-patients page renders the four
 *     count tiles, the aspect filter, and the table column headers
 *     called out in the DI acceptance criterion.
 *   - The legacy /admin/guidance/test-patients route file is deleted.
 *
 * Static-source rather than live-render: the page hits the network
 * on mount, and the design-controls rule mandates static-source VTs
 * for any page that fetches on mount.
 *
 * Atlas IDs: UN-50102672, DI-7625C251, R-8C0CC94B, VT-5BDFE5F7.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, rel), "utf8");
}

function exists(rel: string): boolean {
  return fs.existsSync(path.join(REPO_ROOT, rel));
}

describe("VT-5BDFE5F7 - Knowledge > Test Patients tab (Phase A)", () => {
  test("TC-001: Knowledge page registers the test-patients tab", () => {
    const src = read("services/ui/src/app/admin/knowledge/page.tsx");
    expect(src).toMatch(
      /\{\s*key:\s*"test-patients"\s*,\s*label:\s*"Test Patients"\s*\}/,
    );
    expect(src).toMatch(/"test-patients":\s*TestPatientsPage/);
    expect(src).toMatch(/"test-patients":\s*"wide"/);
    expect(src).toMatch(
      /import\("@\/app\/admin\/knowledge\/test-patients\/page"\)/,
    );
  });

  test("TC-002: Knowledge tab copy carries plain-English intro blocks", () => {
    const src = read("services/ui/src/lib/knowledgeCopy.ts");
    // The KnowledgeTabKey union includes the new key.
    expect(src).toMatch(/\|\s*"test-patients"/);
    // The copy block is present and uses sentence-case labels.
    expect(src).toMatch(/"test-patients":\s*\{/);
    expect(src).toMatch(/title:\s*"Test Patients"/);
    // Extract the block by slicing from the test-patients key to the
    // next sibling key (terminology) -- avoids brittle nested regexes.
    const startIdx = src.indexOf('"test-patients":');
    const endIdx = src.indexOf("terminology:", startIdx);
    expect(startIdx).toBeGreaterThan(0);
    expect(endIdx).toBeGreaterThan(startIdx);
    const text = src.slice(startIdx, endIdx);
    // Audience-grade blocks present (default + clinician + staff).
    expect(text).toMatch(/default:\s*\{/);
    expect(text).toMatch(/clinician:\s*\{/);
    expect(text).toMatch(/staff:\s*\{/);
    expect(text).toMatch(/qa_ra_lead:\s*\{/);
    // Plain-English markers: no IT jargon in the default block.
    const defaultStart = text.indexOf("default: {");
    const defaultEnd = text.indexOf("clinician:", defaultStart);
    expect(defaultStart).toBeGreaterThan(-1);
    expect(defaultEnd).toBeGreaterThan(defaultStart);
    const defaultText = text.slice(defaultStart, defaultEnd);
    expect(defaultText).not.toMatch(/regression/i);
    expect(defaultText).not.toMatch(/fixture/i);
    expect(defaultText).not.toMatch(/aspect/i);
  });

  test("TC-003: Test Patients page uses canonical design-system primitives", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/page.tsx",
    );
    // The page is a sibling of /admin/pathways and must use the same
    // Knowledge tab primitives so the visual rhythm of the tabs is
    // consistent. See DI-LEO-AI-150 for the canonical pattern.
    expect(src).toMatch(/from\s+"@leo\/design-system"/);
    expect(src).toMatch(/StatHero/);
    expect(src).toMatch(/SegmentedTabs/);
    expect(src).toMatch(/ToolbarActions/);
    expect(src).toMatch(/DataGridCard/);
    // Filter exposes one tab per aspect, driven by ASPECT_VALUES so
    // the source of truth stays in types.ts.
    expect(src).toMatch(/ASPECT_VALUES\.map/);
    expect(src).toMatch(
      /aria-label="Filter test patients by AI aspect"/,
    );
    // Copy-from-real and Build actions surface in the toolbar.
    expect(src).toMatch(/id:\s*"copy-from-real"/);
    expect(src).toMatch(/id:\s*"build-patient"/);
    expect(src).toMatch(/Copy from a real patient/);
    // The duplicate page-level title is gone -- KnowledgePageLayout
    // already renders the intro from KNOWLEDGE_TAB_COPY.
    expect(src).not.toMatch(/<Typography[^>]*variant="h6"[^>]*>\s*Test patients/);
  });

  test("TC-004: aspect type defines all four AI aspects + 'all'", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/types.ts",
    );
    expect(src).toMatch(
      /ASPECT_VALUES\s*=\s*\[\s*"all",\s*"nlp",\s*"episodes",\s*"guidelines",\s*"summarisation",?\s*\]/,
    );
    // Plain-English labels for the audience standard.
    expect(src).toMatch(/nlp:\s*"Reading notes"/);
    expect(src).toMatch(/episodes:\s*"Patient story"/);
    expect(src).toMatch(/guidelines:\s*"Rule checks"/);
    expect(src).toMatch(/summarisation:\s*"SBAR handover"/);
  });

  test("TC-005: api client points at the centralised endpoints", () => {
    const src = read(
      "services/ui/src/app/admin/knowledge/test-patients/api.ts",
    );
    expect(src).toMatch(/\/api\/guidance\/test-patients/);
    expect(src).toMatch(/\/aspect-counts/);
    expect(src).toMatch(/\/source-patients/);
    expect(src).toMatch(/\/clone/);
    // The list endpoint passes the aspect query param when set.
    expect(src).toMatch(/qs\.set\("aspect"/);
  });

  test("TC-006: legacy /admin/guidance/test-patients route file is removed", () => {
    expect(
      exists("services/ui/src/app/admin/guidance/test-patients/page.tsx"),
    ).toBe(false);
    // The supporting modules (dialogs, api, types) are still present
    // because the new Knowledge tab and the EditRuleDialog import
    // them; only the route page.tsx is deleted in Phase A.
    expect(
      exists("services/ui/src/app/admin/guidance/test-patients/api.ts"),
    ).toBe(true);
    expect(
      exists(
        "services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx",
      ),
    ).toBe(true);
    const lifecycle = read(
      "services/ui/src/app/admin/guidance/BitmapLifecycleSection.tsx",
    );
    // The "Open library" button now points at the Knowledge tab.
    expect(lifecycle).toMatch(
      /href="\/admin\/knowledge\?tab=test-patients"/,
    );
    expect(lifecycle).not.toMatch(/href="\/admin\/guidance\/test-patients"/);
  });
});
