/**
 * VT-5AAD89E2 -- Demographics evolution chrome (static-source VT).
 *
 * Atlas trace:
 *   DO: DO-4DADBA3F
 *   DI: DI-87D92943
 *   Risk: R-05B6DDA7, R-27CCE37C
 *   Look up via: get_design_control(dc_type="verification-test", dc_id="VT-5AAD89E2")
 *
 * Verifies the year-on-year demographics evolution view:
 *   AC1 -- the audit page renders <DemographicsEvolutionSection /> and
 *          <ComorbiditiesSection /> in place of the legacy
 *          <DemographicsSection />, and the TOC has an entry for the
 *          new comorbidities section.
 *   AC2 -- AuditDemographics in analyticsApi.ts exposes the
 *          age_band_by_sex array and ethnicity_by_snomed (SNOMED radar).
 *   AC3 -- DemographicsEvolutionSection.tsx fires three live calendar-
 *          year fetches via fetchAuditDemographics, anchors on
 *          BASELINE_YEAR = 2018, and is decoupled from the global
 *          AnalyticsDateFilter context (no SummaryStatsTable /
 *          ComparisonBarChart / CancerTypeBenchmarkGrid either).
 *   AC4 -- PopulationPyramidCard.tsx exposes an aria-label, an n-badge,
 *          a loading / empty / low-sample branch, an isBaseline branch
 *          with the marginal-only published-baseline caption, and the
 *          Atlas trace header (R-05B6DDA7 mitigations).
 *   AC5 -- EthnicityYearCard.tsx mirrors the cancer-stage card mitigations for
 *          the 2018 baseline column; EthnicitySnomedRadarCard.tsx handles live
 *          SNOMED years plus cohort coverage copy (R-27CCE37C legacy captions on bar card).
 *   AC6 -- ComorbiditiesSection.tsx exists, has id 'section-comorbidities'
 *          and the Atlas trace header.
 *   AC7 -- Atlas-linked component files carry the canonical Atlas trace header
 *          pointing at DO-4DADBA3F / DI-87D92943 (and comorbidity drill-down
 *          artefacts DO-D5B9FE5F where applicable).
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const AUDIT_PAGE_PATH = "services/ui/src/app/audit/page.tsx";
const ANALYTICS_API_PATH = "services/ui/src/lib/analyticsApi.ts";
const SECTION_PATH =
  "services/ui/src/components/audit/DemographicsEvolutionSection.tsx";
const PYRAMID_PATH =
  "services/ui/src/components/audit/PopulationPyramidCard.tsx";
const ETHNICITY_PATH =
  "services/ui/src/components/audit/EthnicityYearCard.tsx";
const ETHNICITY_SNOMED_RADAR_PATH =
  "services/ui/src/components/audit/EthnicitySnomedRadarCard.tsx";
const COMORB_RADAR_PATH =
  "services/ui/src/components/audit/ComorbidityRadarCard.tsx";
const COMORB_DRILL_PATH =
  "services/ui/src/components/audit/ComorbiditiesDrilldownDialog.tsx";
const COMORB_PATH =
  "services/ui/src/components/audit/ComorbiditiesSection.tsx";

const NEW_FILES = [
  SECTION_PATH,
  PYRAMID_PATH,
  ETHNICITY_PATH,
  ETHNICITY_SNOMED_RADAR_PATH,
  COMORB_RADAR_PATH,
  COMORB_DRILL_PATH,
  COMORB_PATH,
];

describe("VT-5AAD89E2 Demographics evolution chrome", () => {
  describe("AC1 -- audit page wires up the new sections", () => {
    let auditPage: string;
    beforeAll(() => {
      auditPage = read(AUDIT_PAGE_PATH);
    });

    test("imports DemographicsEvolutionSection", () => {
      expect(auditPage).toMatch(
        /import\s+DemographicsEvolutionSection\s+from\s+["']@\/components\/audit\/DemographicsEvolutionSection["']/,
      );
    });

    test("imports ComorbiditiesSection", () => {
      expect(auditPage).toMatch(
        /import\s+ComorbiditiesSection\s+from\s+["']@\/components\/audit\/ComorbiditiesSection["']/,
      );
    });

    test("does not import the legacy DemographicsSection", () => {
      expect(auditPage).not.toMatch(
        /import\s+DemographicsSection\s+from\s+["']@\/components\/audit\/DemographicsSection["']/,
      );
    });

    test("renders both new sections in the report tab", () => {
      expect(auditPage).toMatch(/<DemographicsEvolutionSection[\s\S]*?\/>/);
      expect(auditPage).toMatch(/<ComorbiditiesSection[\s\S]*?\/>/);
      expect(auditPage).not.toMatch(/<DemographicsSection[\s\S]*?\/>/);
    });

    test("registers section-comorbidities in TOC_SECTIONS", () => {
      expect(auditPage).toMatch(/id:\s*"section-comorbidities"/);
    });
  });

  describe("AC2 -- AuditDemographics interface exposes age_band_by_sex", () => {
    let api: string;
    beforeAll(() => {
      api = read(ANALYTICS_API_PATH);
    });

    test("AuditDemographics has age_band_by_sex array of {gender, age_band, n, pct}", () => {
      expect(api).toMatch(
        /age_band_by_sex:\s*Array<\{[\s\S]*?gender:\s*string;[\s\S]*?age_band:\s*string;[\s\S]*?n:\s*number;[\s\S]*?pct:\s*number;[\s\S]*?\}>/,
      );
    });

    test("AuditDemographics has ethnicity_by_snomed for SNOMED-radar ethnicity", () => {
      expect(api).toMatch(/ethnicity_by_snomed:\s*Array</);
      expect(api).toMatch(/benchmark_key:\s*string/);
      expect(api).toMatch(/preferred_term:\s*string/);
    });

    test("AuditDemographics surfaces cohort vs SNOMED ethnicity-coded counts", () => {
      expect(api).toMatch(/demographics_cohort_n:\s*number/);
      expect(api).toMatch(/patients_with_ethnicity_snomed_n:\s*number/);
      expect(api).toMatch(/ethnicity_snomed_coverage_pct:\s*number\s*\|\s*null/);
    });
  });

  describe("AC3 -- evolution section orchestrates the four-card view", () => {
    let section: string;
    beforeAll(() => {
      section = read(SECTION_PATH);
    });

    test("imports fetchAuditDemographics from the analytics API", () => {
      expect(section).toMatch(
        /import\s*\{[\s\S]*?fetchAuditDemographics[\s\S]*?\}\s*from\s+["']@\/lib\/analyticsApi["']/,
      );
    });

    test("does not consume the global AnalyticsDateFilter context", () => {
      expect(section).not.toMatch(/useAnalyticsDateFilter/);
    });

    test("does not render the legacy SummaryStatsTable / ComparisonBarChart / CancerTypeBenchmarkGrid", () => {
      expect(section).not.toMatch(/SummaryStatsTable/);
      expect(section).not.toMatch(/ComparisonBarChart/);
      expect(section).not.toMatch(/CancerTypeBenchmarkGrid/);
    });

    test("renders PopulationPyramidCard, EthnicitySnomedRadarCard for live years, EthnicityYearCard baseline", () => {
      expect(section).toMatch(
        /import\s+PopulationPyramidCard[\s\S]*?from\s+["']\.\/PopulationPyramidCard["']/,
      );
      expect(section).toMatch(/<PopulationPyramidCard[\s\S]*?\/>/);
      expect(section).toMatch(
        /import\s+EthnicitySnomedRadarCard\s+from\s+["']\.\/EthnicitySnomedRadarCard["']/,
      );
      expect(section).toMatch(/<EthnicitySnomedRadarCard[\s\S]*?\/>/);
      expect(section).toMatch(
        /import\s+EthnicityYearCard\s+from\s+["']\.\/EthnicityYearCard["']/,
      );
      expect(section).toMatch(/<EthnicityYearCard[\s\S]*?\/>/);
    });

    test("derives Jan-Dec calendar-year date windows", () => {
      expect(section).toMatch(/-01-01/);
      expect(section).toMatch(/-12-31/);
    });

    test("anchors on the 2018 NCDA baseline year", () => {
      expect(section).toMatch(/BASELINE_YEAR\s*=\s*2018/);
    });

    test("passes marginal age_band pct from practice age_bands for live years", () => {
      expect(section).toMatch(/ageBandPct=\{ageBandPctFromPractice\(state\.data\)\}/);
    });

    test("subsection title reflects sex and age distribution", () => {
      expect(section).toMatch(/Sex and age distribution by year/);
    });

    test("subsection title reflects SNOMED ethnicity row", () => {
      expect(section).toMatch(/Ethnicity \(SNOMED-coded\) by year/);
    });

    test("renders the Demographics SectionCard with id section-demographics", () => {
      expect(section).toMatch(/id="section-demographics"/);
    });
  });

  describe("AC4 -- demographics card surfaces R-05B6DDA7 mitigations", () => {
    let card: string;
    beforeAll(() => {
      card = read(PYRAMID_PATH);
    });

    test("exposes aria-labels on the outer card and on sex/age SVG charts", () => {
      expect(card).toMatch(
        /aria-label=\{`Demographics chart card for \$\{yearLabel\}`\}/,
      );
      expect(card).toMatch(
        /aria-label=\{`Sex distribution for \$\{yearLabel\}/,
      );
      expect(card).toMatch(
        /aria-label=\{`Age at diagnosis \(% of cases\) for \$\{yearLabel\}`\}/,
      );
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

    test("supports an isBaseline branch with the marginal-only published-baseline caption", () => {
      expect(card).toMatch(/isBaseline/);
      expect(card).toMatch(/2018 NCDA baseline publishes marginal age and sex only/);
    });

    test("publishes the canonical six age bands for the area chart x-axis", () => {
      expect(card).toMatch(/PYRAMID_AGE_BANDS/);
      expect(card).toMatch(/"85\+"/);
      expect(card).toMatch(/"0-24"/);
    });

    test("supports a loading branch", () => {
      expect(card).toMatch(/loading\s*\?\s*"Loading\.\.\."/);
    });
  });

  describe("AC5 -- ethnicity card mirrors stage-card mitigations and R-27CCE37C", () => {
    let card: string;
    beforeAll(() => {
      card = read(ETHNICITY_PATH);
    });

    test("exposes an aria-label naming the year", () => {
      expect(card).toMatch(/aria-label=\{`Ethnicity card for \$\{yearLabel\}`\}/);
    });

    test("renders an n-badge Chip with the sample size", () => {
      expect(card).toMatch(/<Chip[\s\S]*?label=\{`n\s*=\s*\$\{totalN\}`\}/);
    });

    test("renders empty-state and low-sample captions", () => {
      expect(card).toMatch(/No data yet for/);
      expect(card).toMatch(/Limited sample/);
    });

    test("supports an isBaseline branch with the white-only published-baseline caption", () => {
      expect(card).toMatch(/isBaseline/);
      expect(card).toMatch(/2018 NCDA baseline publishes white ethnicity % only/);
    });

    test("renders the dashed 2018 reference tick on live cards", () => {
      expect(card).toMatch(/baseline2018White/);
      expect(card).toMatch(/2px dashed/);
    });

    test("captions that non-white categories are aggregated (R-27CCE37C)", () => {
      expect(card).toMatch(/Non-white categories/);
      expect(card).toMatch(/Asian/);
      expect(card).toMatch(/Black/);
      expect(card).toMatch(/Mixed/);
      expect(card).toMatch(/Other/);
    });
  });

  describe("AC5b -- EthnicitySnomedRadarCard cohort coverage copy", () => {
    let radar: string;
    beforeAll(() => {
      radar = read(ETHNICITY_SNOMED_RADAR_PATH);
    });

    test("surfaces cohort vs SNOMED-coded patient counts in copy", () => {
      expect(radar).toMatch(/demographicsCohortN/);
      expect(radar).toMatch(/patientsWithEthnicitySnomedN/);
      expect(radar).toMatch(/with SNOMED ethnicity coded/);
    });

    test("renders a radar SVG role", () => {
      expect(radar).toMatch(/role="img"/);
    });
  });

  describe("AC6 -- comorbidities section is now standalone", () => {
    let section: string;
    beforeAll(() => {
      section = read(COMORB_PATH);
    });

    test("renders a SectionCard with id section-comorbidities", () => {
      expect(section).toMatch(/id="section-comorbidities"/);
    });

    test("titled 'Comorbidities at Diagnosis'", () => {
      expect(section).toMatch(/Comorbidities at Diagnosis/);
    });

    test("does not render the legacy comorbidity bar chart", () => {
      expect(section).not.toMatch(/import\s+ComparisonBarChart/);
      expect(section).not.toMatch(/<ComparisonBarChart[\s\S]*?\/>/);
      expect(section).not.toMatch(/Other health conditions \(comorbidities\)/);
    });

    test("includes multimorbidity radar and drill-down dialog entry points", () => {
      expect(section).toMatch(/ComorbidityRadarCard/);
      expect(section).toMatch(/ComorbiditiesDrilldownDialog/);
      expect(section).toMatch(/calendarYearWindow/);
      expect(section).toMatch(/BASELINE_YEAR\s*=\s*2018/);
    });
  });

  describe("AC7 -- new files carry the Atlas trace header", () => {
    test.each(NEW_FILES)(
      "%s contains the canonical Atlas trace header",
      (rel) => {
        const text = read(rel);
        const head = text.slice(0, 700);
        expect(head).toContain("Atlas trace:");
        expect(head).toContain("DO-4DADBA3F");
        expect(head).toContain("DI-87D92943");
      },
    );
  });
});
