/**
 * VT-LEO-AI-131 - Phase 2 IA merge of /admin/clinical into /admin/knowledge.
 *
 * Verifies the three structural invariants of DI-LEO-AI-135 that do not
 * require rendering a full React tree:
 *
 *   TC-001: KnowledgePage exposes the canonical 8 tab keys in order.
 *   TC-002: next.config.mjs permanently redirects every legacy URL to
 *           the matching /admin/knowledge?tab=<k>.
 *   TC-003: AppShell ADMIN_NAV_ITEMS no longer contains a Clinical
 *           entry; Knowledge activePrefix covers the legacy paths.
 *
 * TC-004 (URL audit) is covered by the existing admin-url-audit.test.ts.
 */

import fs from "fs";
import path from "path";

const UI_ROOT = path.resolve(__dirname, "..", "..");

function readSource(rel: string): string {
  return fs.readFileSync(path.join(UI_ROOT, rel), "utf-8");
}

describe("VT-131 - Knowledge hub merge", () => {
  describe("TC-001 canonical tab order", () => {
    it("KnowledgePage TABS has all 8 keys in the documented order", () => {
      const src = readSource("src/app/admin/knowledge/page.tsx");
      const keys = [
        "training-data",
        "surface-forms",
        "context-rules",
        "ai-instructions",
        "clinical-guidelines",
        "pathways",
        "domains",
        "terminology",
      ];
      let cursor = 0;
      for (const key of keys) {
        const idx = src.indexOf(`key: "${key}"`, cursor);
        expect(idx).toBeGreaterThan(-1);
        cursor = idx + 1;
      }
    });

    it("KnowledgePage lazy-loads all eight sub-pages", () => {
      const src = readSource("src/app/admin/knowledge/page.tsx");
      const modules = [
        "gold-dataset",
        "surface-forms",
        "context-rules",
        "prompts",
        "guidance",
        "pathways",
        "domains",
        "terminology",
      ];
      for (const m of modules) {
        expect(src).toContain(`import("@/app/admin/${m}/page")`);
      }
    });
  });

  describe("TC-002 legacy URL redirects", () => {
    const config = readSource("next.config.mjs");

    const cases: Array<[string, string]> = [
      ["/admin/clinical", "/admin/knowledge"],
      ["/admin/pathways", "/admin/knowledge?tab=pathways"],
      ["/admin/domains", "/admin/knowledge?tab=domains"],
      ["/admin/terminology", "/admin/knowledge?tab=terminology"],
    ];

    it.each(cases)(
      "%s is redirected permanently to %s",
      (source, destination) => {
        const pattern = new RegExp(
          `source:\\s*"${source.replace(/[/?]/g, "\\$&")}"[^}]*destination:\\s*"${destination.replace(/[/?]/g, "\\$&")}"[^}]*permanent:\\s*true`,
          "s",
        );
        expect(config).toMatch(pattern);
      },
    );

    it("no redirect target still points at /admin/clinical", () => {
      expect(config).not.toMatch(/destination:\s*"\/admin\/clinical/);
    });
  });

  describe("TC-003 AppShell nav consolidation", () => {
    const src = readSource("src/components/AppShell.tsx");

    it("ADMIN_NAV_ITEMS no longer contains a Clinical entry", () => {
      expect(src).not.toMatch(/label:\s*"Clinical"/);
    });

    it("Knowledge activePrefix covers the legacy clinical routes", () => {
      const legacy = [
        "/admin/clinical",
        "/admin/pathways",
        "/admin/domains",
        "/admin/terminology",
      ];
      for (const p of legacy) {
        expect(src).toContain(`"${p}"`);
      }
    });

    it("LocalHospitalOutlinedIcon is no longer imported", () => {
      expect(src).not.toContain("LocalHospitalOutlinedIcon");
    });
  });
});
