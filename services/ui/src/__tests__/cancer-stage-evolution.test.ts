/**
 * VT-C5F1B4DE -- Cancer Stage evolution chrome (static-source VT).
 *
 * Atlas trace:
 *   DO: DO-EF5F7455
 *   DI: DI-38AE4EA1
 *   Risk: R-E00F9C3C
 *   Look up via: get_design_control(dc_type="verification-test", dc_id="VT-C5F1B4DE")
 *
 * Verifies the year-on-year cancer stage evolution view:
 *   AC1 -- the audit page renders <CancerStageEvolutionSection /> in
 *          place of the legacy <CancerStageSection /> and no longer
 *          imports the bullet chart or accordion.
 *   AC2 -- CancerStageEvolutionSection.tsx fires three live calendar-
 *          year fetches via fetchAuditCancerStage, opens the drill-down
 *          dialog, and is decoupled from the global AnalyticsDateFilter
 *          context (no SummaryStatsTable / CancerStageBulletChart /
 *          CancerStageAccordion either).
 *   AC3 -- CancerStageYearCard.tsx exposes an aria-label, an n-badge,
 *          empty-state and low-sample captions, a baseline-only branch
 *          and the published-baseline caption -- mitigating R-E00F9C3C.
 *   AC4 -- CancerStageEvolutionDialog.tsx uses MUI Dialog, iterates
 *          CANCER_TYPE_OPTIONS, exposes an accessible title and the
 *          Atlas trace header.
 *   AC5 -- CancerStagePerTypeRow.tsx renders 'No data' placeholders,
 *          calls cancerTypeLabel, references resolveBaseline2019 /
 *          FALLBACK_NATIONAL_2019 for the 2018 per-type baseline, and
 *          has a 'Stage convention N/A' branch.
 *   AC6 -- All four new files carry the canonical Atlas trace header
 *          pointing at DO-EF5F7455 / DI-38AE4EA1.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const AUDIT_PAGE_PATH = "services/ui/src/app/audit/page.tsx";
const SECTION_PATH =
  "services/ui/src/components/audit/CancerStageEvolutionSection.tsx";
const CARD_PATH = "services/ui/src/components/audit/CancerStageYearCard.tsx";
const DIALOG_PATH =
  "services/ui/src/components/audit/CancerStageEvolutionDialog.tsx";
const ROW_PATH = "services/ui/src/components/audit/CancerStagePerTypeRow.tsx";

const NEW_FILES = [SECTION_PATH, CARD_PATH, DIALOG_PATH, ROW_PATH];

describe("VT-C5F1B4DE Cancer Stage evolution chrome", () => {
  describe("AC1 -- audit page wires up the new evolution section", () => {
    let auditPage: string;
    beforeAll(() => {
      auditPage = read(AUDIT_PAGE_PATH);
    });

    test("imports CancerStageEvolutionSection", () => {
      expect(auditPage).toMatch(
        /import\s+CancerStageEvolutionSection\s+from\s+["']@\/components\/audit\/CancerStageEvolutionSection["']/,
      );
    });

    test("does not import the legacy CancerStageSection", () => {
      expect(auditPage).not.toMatch(
        /import\s+CancerStageSection\s+from\s+["']@\/components\/audit\/CancerStageSection["']/,
      );
    });

    test("renders <CancerStageEvolutionSection /> in the report tab", () => {
      expect(auditPage).toMatch(/<CancerStageEvolutionSection[\s\S]*?\/>/);
      expect(auditPage).not.toMatch(/<CancerStageSection[\s\S]*?\/>/);
    });

    test("does not import the legacy bullet chart or accordion", () => {
      expect(auditPage).not.toMatch(/CancerStageBulletChart/);
      expect(auditPage).not.toMatch(/CancerStageAccordion/);
    });
  });

  describe("AC2 -- evolution section orchestrates the four-card view", () => {
    let section: string;
    beforeAll(() => {
      section = read(SECTION_PATH);
    });

    test("imports fetchAuditCancerStage from the analytics API", () => {
      expect(section).toMatch(
        /import\s*\{[\s\S]*?fetchAuditCancerStage[\s\S]*?\}\s*from\s+["']@\/lib\/analyticsApi["']/,
      );
    });

    test("does not consume the global AnalyticsDateFilter context", () => {
      expect(section).not.toMatch(/useAnalyticsDateFilter/);
    });

    test("does not render the legacy CancerStageBulletChart, CancerStageAccordion or SummaryStatsTable", () => {
      expect(section).not.toMatch(/CancerStageBulletChart/);
      expect(section).not.toMatch(/CancerStageAccordion/);
      expect(section).not.toMatch(/SummaryStatsTable/);
    });

    test("renders CancerStageYearCard and opens CancerStageEvolutionDialog", () => {
      expect(section).toMatch(
        /import\s+CancerStageYearCard[\s\S]*?from\s+["']\.\/CancerStageYearCard["']/,
      );
      expect(section).toMatch(/<CancerStageYearCard[\s\S]*?\/>/);
      expect(section).toMatch(
        /import\s+CancerStageEvolutionDialog[\s\S]*?from\s+["']\.\/CancerStageEvolutionDialog["']/,
      );
      expect(section).toMatch(/<CancerStageEvolutionDialog[\s\S]*?\/>/);
    });

    test("derives Jan-Dec calendar-year date windows", () => {
      expect(section).toMatch(/-01-01/);
      expect(section).toMatch(/-12-31/);
    });

    test("anchors on the 2018 NCDA baseline year", () => {
      expect(section).toMatch(/BASELINE_YEAR\s*=\s*2018/);
    });
  });

  describe("AC3 -- year card surfaces R-E00F9C3C mitigations", () => {
    let card: string;
    beforeAll(() => {
      card = read(CARD_PATH);
    });

    test("exposes an aria-label naming the year", () => {
      expect(card).toMatch(/aria-label=\{`Cancer stage card for \$\{yearLabel\}`\}/);
    });

    test("renders an n-badge Chip with the sample size", () => {
      expect(card).toMatch(/<Chip[\s\S]*?label=\{`n\s*=\s*\$\{totalN\}`\}/);
    });

    test("renders an explicit empty-state caption", () => {
      expect(card).toMatch(/No data yet for/);
    });

    test("renders a low-sample caption", () => {
      expect(card).toMatch(/Limited sample/);
      expect(card).toMatch(/LOW_SAMPLE_THRESHOLD\s*=\s*\d+/);
    });

    test("renders a low-coverage caption", () => {
      expect(card).toMatch(/Stage recorded for/);
      expect(card).toMatch(/LOW_COVERAGE_THRESHOLD\s*=\s*\d+/);
    });

    test("supports an isBaseline branch with the published-baseline caption", () => {
      expect(card).toMatch(/isBaseline/);
      expect(card).toMatch(/2018 NCDA baseline/);
      expect(card).toMatch(/Late and unstaged are not published/);
    });
  });

  describe("AC4 -- evolution dialog drills down per cancer type", () => {
    let dialog: string;
    beforeAll(() => {
      dialog = read(DIALOG_PATH);
    });

    test("imports MUI Dialog and DialogTitle", () => {
      expect(dialog).toMatch(
        /import\s+Dialog\s+from\s+["']@mui\/material\/Dialog["']/,
      );
      expect(dialog).toMatch(
        /import\s+DialogTitle\s+from\s+["']@mui\/material\/DialogTitle["']/,
      );
    });

    test("iterates the canonical NCDA cancer-type list", () => {
      expect(dialog).toMatch(
        /import\s*\{[\s\S]*?CANCER_TYPE_OPTIONS[\s\S]*?\}\s*from\s+["']@\/lib\/cancerTypes["']/,
      );
      expect(dialog).toMatch(/CANCER_TYPE_OPTIONS\.filter/);
    });

    test("excludes the catch-all sentinels from the rendered list", () => {
      expect(dialog).toMatch(/CANCER_TYPE_NO_INFORMATION/);
      expect(dialog).toMatch(/CANCER_TYPE_UNKNOWN_PRIMARY/);
      expect(dialog).toMatch(/CANCER_TYPE_OTHER/);
    });

    test("renders CancerStagePerTypeRow per entry", () => {
      expect(dialog).toMatch(
        /import\s+CancerStagePerTypeRow[\s\S]*?from\s+["']\.\/CancerStagePerTypeRow["']/,
      );
      expect(dialog).toMatch(/<CancerStagePerTypeRow[\s\S]*?\/>/);
    });

    test("exposes an accessible dialog title via aria-labelledby", () => {
      expect(dialog).toMatch(/aria-labelledby="cancer-stage-evolution-dialog-title"/);
      expect(dialog).toMatch(/id="cancer-stage-evolution-dialog-title"/);
    });
  });

  describe("AC5 -- per-type row handles sparse data and null baselines", () => {
    let row: string;
    beforeAll(() => {
      row = read(ROW_PATH);
    });

    test("imports cancerTypeLabel + resolveBaseline2019 + FALLBACK_NATIONAL_2019", () => {
      expect(row).toMatch(
        /import\s*\{[\s\S]*?cancerTypeLabel[\s\S]*?\}\s*from\s+["']@\/lib\/cancerTypeKeys["']/,
      );
      expect(row).toMatch(/resolveBaseline2019/);
      expect(row).toMatch(/FALLBACK_NATIONAL_2019/);
    });

    test("renders an explicit 'No data' placeholder when a cell has no live data", () => {
      expect(row).toMatch(/No data/);
    });

    test("has a 'Stage convention N/A' branch for null-baseline cancer types", () => {
      expect(row).toMatch(/Stage convention N\/A/);
    });

    test("computes a vs-2018 delta chip", () => {
      expect(row).toMatch(/vs 2018/);
      expect(row).toMatch(/pp/);
    });
  });

  describe("AC6 -- new files carry the Atlas trace header", () => {
    test.each(NEW_FILES)(
      "%s contains the canonical Atlas trace header",
      (rel) => {
        const text = read(rel);
        const head = text.slice(0, 700);
        expect(head).toContain("Atlas trace:");
        expect(head).toContain("DO-EF5F7455");
        expect(head).toContain("DI-38AE4EA1");
      },
    );
  });
});
