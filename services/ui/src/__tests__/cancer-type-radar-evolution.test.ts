/**
 * VT-AFEDEB85 -- Cancer Type radar evolution chrome (static-source VT).
 *
 * Atlas trace:
 *   DO: DO-BFF68D36
 *   DI: DI-077C8810
 *   Risk: R-C700EACC
 *   Look up via: get_design_control(dc_type="verification-test", dc_id="VT-AFEDEB85")
 *
 * Verifies the year-on-year cancer type evolution view:
 *   AC1 -- the audit page renders <CancerTypeEvolutionSection /> in place
 *          of the legacy <CancerTypeSection />.
 *   AC2 -- the audit page filter bar no longer ships the From/To date
 *          pickers, the Financial Year (TAX_YEAR_PRESETS) chips, the
 *          benchmark-set selector, or the AuditExternalBenchmarkToggles
 *          comparator checkboxes.
 *   AC3 -- CancerTypeEvolutionSection.tsx fires three live calendar-year
 *          fetches and is decoupled from the global AnalyticsDateFilter
 *          context, with no SummaryStatsTable present.
 *   AC4 -- CancerTypeRadarCard.tsx exposes an SVG aria-label, an
 *          n-badge, an empty-state caption and a low-sample caption to
 *          mitigate R-C700EACC (sparse current-year card misread).
 *   AC5 -- both new files carry the canonical Atlas trace header
 *          pointing at DO-BFF68D36 / DI-077C8810.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const AUDIT_PAGE_PATH = "services/ui/src/app/audit/page.tsx";
const SECTION_PATH =
  "services/ui/src/components/audit/CancerTypeEvolutionSection.tsx";
const CARD_PATH = "services/ui/src/components/audit/CancerTypeRadarCard.tsx";

describe("VT-AFEDEB85 Cancer Type radar evolution chrome", () => {
  describe("AC1 -- audit page wires up the new evolution section", () => {
    let auditPage: string;
    beforeAll(() => {
      auditPage = read(AUDIT_PAGE_PATH);
    });

    test("imports CancerTypeEvolutionSection", () => {
      expect(auditPage).toMatch(
        /import\s+CancerTypeEvolutionSection\s+from\s+["']@\/components\/audit\/CancerTypeEvolutionSection["']/,
      );
    });

    test("does not import the legacy CancerTypeSection", () => {
      expect(auditPage).not.toMatch(
        /import\s+CancerTypeSection\s+from\s+["']@\/components\/audit\/CancerTypeSection["']/,
      );
    });

    test("renders <CancerTypeEvolutionSection /> in the report tab", () => {
      expect(auditPage).toMatch(/<CancerTypeEvolutionSection[\s\S]*?\/>/);
      expect(auditPage).not.toMatch(/<CancerTypeSection[\s\S]*?\/>/);
    });
  });

  describe("AC2 -- audit page filter bar is stripped", () => {
    let auditPage: string;
    beforeAll(() => {
      auditPage = read(AUDIT_PAGE_PATH);
    });

    test("no longer references TAX_YEAR_PRESETS", () => {
      expect(auditPage).not.toMatch(/TAX_YEAR_PRESETS/);
    });

    test("no longer renders the AuditExternalBenchmarkToggles comparator", () => {
      expect(auditPage).not.toMatch(/AuditExternalBenchmarkToggles/);
    });

    test("no longer renders the 'Audit period:' label", () => {
      expect(auditPage).not.toMatch(/Audit period:/);
    });

    test("no longer renders the 'Year:' chip group label", () => {
      expect(auditPage).not.toMatch(/>\s*Year:\s*</);
    });

    test("no longer imports the date-picker / benchmark-selector primitives", () => {
      expect(auditPage).not.toMatch(
        /import\s+TextField\s+from\s+"@mui\/material\/TextField"/,
      );
      expect(auditPage).not.toMatch(
        /import\s+CompareArrowsIcon\s+from\s+"@mui\/icons-material\/CompareArrows"/,
      );
      expect(auditPage).not.toMatch(
        /import\s+FormControlLabel\s+from\s+"@mui\/material\/FormControlLabel"/,
      );
    });
  });

  describe("AC3 -- evolution section fetches calendar years and drops the table", () => {
    let section: string;
    beforeAll(() => {
      section = read(SECTION_PATH);
    });

    test("imports fetchAuditCancerType from the analytics API", () => {
      expect(section).toMatch(
        /import\s*\{[\s\S]*?fetchAuditCancerType[\s\S]*?\}\s*from\s+["']@\/lib\/analyticsApi["']/,
      );
    });

    test("does not consume the global AnalyticsDateFilter context", () => {
      expect(section).not.toMatch(/useAnalyticsDateFilter/);
    });

    test("does not render a SummaryStatsTable", () => {
      expect(section).not.toMatch(/SummaryStatsTable/);
    });

    test("does not import the legacy CancerTypeDumbbellChart", () => {
      expect(section).not.toMatch(/CancerTypeDumbbellChart/);
    });

    test("renders the CancerTypeRadarCard primitive", () => {
      expect(section).toMatch(
        /import\s+CancerTypeRadarCard[\s\S]*?from\s+["']\.\/CancerTypeRadarCard["']/,
      );
      expect(section).toMatch(/<CancerTypeRadarCard[\s\S]*?\/>/);
    });

    test("derives calendar-year date windows ending Dec 31", () => {
      expect(section).toMatch(/-01-01/);
      expect(section).toMatch(/-12-31/);
    });

    test("anchors on the 2018 NCDA baseline year", () => {
      expect(section).toMatch(/BASELINE_YEAR\s*=\s*2018/);
    });
  });

  describe("AC4 -- radar card surfaces R-C700EACC mitigations", () => {
    let card: string;
    beforeAll(() => {
      card = read(CARD_PATH);
    });

    test("renders an SVG with an aria-label", () => {
      const svg = card.match(/<svg[\s\S]*?>/);
      expect(svg).not.toBeNull();
      expect(svg![0]).toMatch(/aria-label=/);
      expect(svg![0]).toMatch(/role="img"/);
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

    test("supports an isBaseline prop for the 2018 anchor card", () => {
      expect(card).toMatch(/isBaseline/);
    });

    test("draws a dashed ghost polygon for the baseline overlay", () => {
      expect(card).toMatch(/strokeDasharray/);
    });
  });

  describe("AC5 -- new files carry the Atlas trace header", () => {
    test.each([SECTION_PATH, CARD_PATH])(
      "%s contains the canonical Atlas trace header",
      (rel) => {
        const text = read(rel);
        const head = text.slice(0, 600);
        expect(head).toContain("Atlas trace:");
        expect(head).toContain("DO-BFF68D36");
        expect(head).toContain("DI-077C8810");
      },
    );
  });
});
