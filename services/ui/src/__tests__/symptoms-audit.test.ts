/**
 * VT-D5B9FE5F -- Symptoms audit section chrome (static-source VT).
 *
 * Atlas trace:
 *   DO: DO-D5B9FE5F
 *   DI: DI-6E1B71A4
 *   Look up via: get_design_control(dc_type="verification-test", dc_id="VT-D5B9FE5F")
 *
 * Verifies the new Symptoms audit section:
 *   AC1 -- the audit page imports SymptomsSection and renders it between
 *          ComorbiditiesSection and PlaceOfPresentationSection, and the
 *          TOC carries a 'section-symptoms' entry.
 *   AC2 -- analyticsApi.ts exposes AuditSymptoms / AuditSymptomPpvRow /
 *          AuditPpvByCancerTypeRow types and fetchAuditSymptoms /
 *          fetchAuditSymptomsDrilldown helpers pointing at
 *          /analytics/audit/symptoms{,/drilldown}.
 *   AC3 -- SymptomsSection.tsx renders a SectionCard with id
 *          'section-symptoms', PPV hero cards, clinical PPV heatmaps grouped
 *          by cancer type, and a Breakdown button that opens
 *          SymptomsDrilldownDialog.
 *   AC4 -- SymptomsDrilldownDialog.tsx wires fetchAuditSymptomsDrilldown
 *          and surfaces tabs for suspected, diagnosed, age, and gender
 *          slices.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");

function read(rel: string): string {
  return fs.readFileSync(path.join(ROOT, rel), "utf8");
}

const AUDIT_PAGE_PATH = "services/ui/src/app/audit/page.tsx";
const ANALYTICS_API_PATH = "services/ui/src/lib/analyticsApi.ts";
const SECTION_PATH = "services/ui/src/components/audit/SymptomsSection.tsx";
const DIALOG_PATH =
  "services/ui/src/components/audit/SymptomsDrilldownDialog.tsx";

describe("VT-D5B9FE5F Symptoms audit section chrome", () => {
  describe("AC1 -- audit page wires up SymptomsSection", () => {
    let auditPage: string;
    beforeAll(() => {
      auditPage = read(AUDIT_PAGE_PATH);
    });

    test("imports SymptomsSection from the audit components folder", () => {
      expect(auditPage).toMatch(
        /import\s+SymptomsSection\s+from\s+["']@\/components\/audit\/SymptomsSection["']/,
      );
    });

    test("renders <SymptomsSection /> between Comorbidities and Place of Presentation", () => {
      const comorbIdx = auditPage.indexOf("<ComorbiditiesSection");
      const symptomsIdx = auditPage.indexOf("<SymptomsSection");
      const placeIdx = auditPage.indexOf("<PlaceOfPresentationSection");
      expect(comorbIdx).toBeGreaterThanOrEqual(0);
      expect(symptomsIdx).toBeGreaterThan(comorbIdx);
      expect(placeIdx).toBeGreaterThan(symptomsIdx);
    });

    test("TOC carries a section-symptoms entry between comorbidities and place-of-presentation", () => {
      const comorbToc = auditPage.indexOf('id: "section-comorbidities"');
      const sympToc = auditPage.indexOf('id: "section-symptoms"');
      const placeToc = auditPage.indexOf('id: "section-place-of-presentation"');
      expect(comorbToc).toBeGreaterThanOrEqual(0);
      expect(sympToc).toBeGreaterThan(comorbToc);
      expect(placeToc).toBeGreaterThan(sympToc);
      expect(auditPage).toMatch(/label:\s*"Symptoms at Referral"/);
    });
  });

  describe("AC2 -- analyticsApi exposes symptoms types and fetchers", () => {
    let api: string;
    beforeAll(() => {
      api = read(ANALYTICS_API_PATH);
    });

    test("AuditSymptoms surface includes total_referrals, rows, and ppv_by_suspected_cancer_type", () => {
      expect(api).toMatch(/export\s+interface\s+AuditSymptoms\s*\{/);
      expect(api).toMatch(/total_referrals:\s*number/);
      expect(api).toMatch(/rows:\s*AuditSymptomPpvRow\[\]/);
      expect(api).toMatch(
        /ppv_by_suspected_cancer_type:\s*AuditPpvByCancerTypeRow\[\]/,
      );
    });

    test("AuditSymptomPpvRow carries the clinical PPV fields", () => {
      expect(api).toMatch(/export\s+interface\s+AuditSymptomPpvRow\s*\{/);
      expect(api).toMatch(/cancer_type:\s*string/);
      expect(api).toMatch(/symptom:\s*string/);
      expect(api).toMatch(/patients_with_feature:\s*number/);
      expect(api).toMatch(/patients_with_cancer:\s*number/);
      expect(api).toMatch(/ppv_pct:\s*number/);
    });

    test("AuditPpvByCancerTypeRow tracks all five referral-cohort PPV buckets and provisional flag", () => {
      expect(api).toMatch(/export\s+interface\s+AuditPpvByCancerTypeRow\s*\{/);
      expect(api).toMatch(/referrals_n:\s*number/);
      expect(api).toMatch(/diagnosed_in_year_n:\s*number/);
      expect(api).toMatch(/no_cancer_in_year_n:\s*number/);
      expect(api).toMatch(/diagnosed_following_year_n:\s*number/);
      expect(api).toMatch(/unresolved_n:\s*number/);
      expect(api).toMatch(/ppv_pct:\s*number\s*\|\s*null/);
      expect(api).toMatch(/provisional:\s*boolean/);
    });

    test("AuditSymptomsDrilldown carries all four slice arrays", () => {
      expect(api).toMatch(/export\s+interface\s+AuditSymptomsDrilldown\s*\{/);
      expect(api).toMatch(/by_age_band:\s*AuditSymptomBreakdownSlice\[\]/);
      expect(api).toMatch(/by_gender:\s*AuditSymptomBreakdownSlice\[\]/);
      expect(api).toMatch(
        /by_suspected_cancer_type:\s*AuditSymptomBreakdownSlice\[\]/,
      );
      expect(api).toMatch(
        /by_diagnosed_cancer_type:\s*AuditSymptomBreakdownSlice\[\]/,
      );
    });

    test("fetch helpers point at the new endpoints", () => {
      expect(api).toMatch(
        /export\s+async\s+function\s+fetchAuditSymptoms\s*\(/,
      );
      expect(api).toMatch(/\/analytics\/audit\/symptoms\$\{_auditParams/);
      expect(api).toMatch(
        /export\s+async\s+function\s+fetchAuditSymptomsDrilldown\s*\(/,
      );
      expect(api).toMatch(
        /\/analytics\/audit\/symptoms\/drilldown\$\{_auditParams/,
      );
    });
  });

  describe("AC3 -- SymptomsSection renders PPV heatmaps and breakdown entry point", () => {
    let section: string;
    beforeAll(() => {
      section = read(SECTION_PATH);
    });

    test("renders a SectionCard with id section-symptoms", () => {
      expect(section).toMatch(/id="section-symptoms"/);
    });

    test("titled 'Symptoms at Referral'", () => {
      expect(section).toMatch(/Symptoms at Referral/);
    });

    test("imports fetchAuditSymptoms from the analytics API helper", () => {
      expect(section).toMatch(
        /import\s+\{[^}]*fetchAuditSymptoms[^}]*\}\s+from\s+["']@\/lib\/analyticsApi["']/,
      );
    });

    test("renders PPV hero cards for referral-cohort summary", () => {
      expect(section).toMatch(/PpvHeroCard/);
      expect(section).toMatch(/ppv_by_suspected_cancer_type/);
    });

    test("flags provisional cohorts with a Provisional chip", () => {
      expect(section).toMatch(/Provisional/i);
    });

    test("renders clinical PPV heatmap cards using rows field", () => {
      expect(section).toMatch(/TumourSiteHeatmapCard/);
      expect(section).toMatch(/Symptom PPV heatmaps by suspected cancer type/);
      expect(section).toMatch(/patients_with_feature/);
      expect(section).toMatch(/patients_with_cancer/);
      expect(section).toMatch(/ppv_pct/);
      expect(section).toMatch(/data\??\.rows/);
    });

    test("exposes min-patient denominator filter controls", () => {
      expect(section).toMatch(/Min patients/);
      expect(section).toMatch(/MIN_N_OPTIONS/);
      expect(section).toMatch(/minN/);
    });

    test("exposes show/hide zero PPV toggle", () => {
      expect(section).toMatch(/Show 0% PPV/);
      expect(section).toMatch(/showZero/);
    });

    test("sorts cards by signal strength (strongCount, moderateCount)", () => {
      expect(section).toMatch(/strongCount/);
      expect(section).toMatch(/moderateCount/);
    });

    test("dims low-confidence cells and shows hidden count footnote", () => {
      expect(section).toMatch(/hiddenCount/);
      expect(section).toMatch(/hidden by current filter/);
    });

    test("renders SymptomsDrilldownDialog and a Breakdown button", () => {
      expect(section).toMatch(/SymptomsDrilldownDialog/);
      expect(section).toMatch(/Breakdown/);
    });
  });

  describe("AC4 -- SymptomsDrilldownDialog: Symptom Pattern Explorer", () => {
    let dialog: string;
    beforeAll(() => {
      dialog = read(DIALOG_PATH);
    });

    test("imports fetchAuditSymptomsDrilldown from the analytics API helper", () => {
      expect(dialog).toMatch(
        /import\s+\{[^}]*fetchAuditSymptomsDrilldown[^}]*\}\s+from\s+["']@\/lib\/analyticsApi["']/,
      );
    });

    test("uses react-force-graph-2d ForceGraph2D via dynamic import (no SSR)", () => {
      expect(dialog).toMatch(/react-force-graph-2d/);
      expect(dialog).toMatch(/ForceGraph2D/);
      expect(dialog).toMatch(/ssr:\s*false/);
    });

    test("applies charge/link forces via callback ref; no manual forceX/Y injection", () => {
      // Uses library's own simulation — only charge + link distance tweaked
      expect(dialog).toMatch(/d3Force\("charge"\)/);
      expect(dialog).toMatch(/d3Force\("link"\)/);
      expect(dialog).toMatch(/handleRef/);
      // Deliberately NOT applying manual forceX/forceY — library spreads nodes natively
      expect(dialog).not.toMatch(/forceX\(/);
    });

    test("opens fullScreen dialog with app-native light audit chrome", () => {
      expect(dialog).toMatch(/fullScreen/);
      expect(dialog).toMatch(/#F8FAFC/);
      expect(dialog).toMatch(/#E2E8F0/);
    });

    test("exposes Referral / Diagnosis / Compare view toggle", () => {
      expect(dialog).toMatch(/ViewMode/);
      expect(dialog).toMatch(/At Referral/);
      expect(dialog).toMatch(/At Diagnosis/);
      expect(dialog).toMatch(/Compare/);
    });

    test("exposes Sankey / Flow (DAG) / Network layout toggle (Sankey default)", () => {
      expect(dialog).toMatch(/LayoutMode/);
      expect(dialog).toMatch(/dagMode/);
      expect(dialog).toMatch(/dagLevelDistance/);
      expect(dialog).toMatch(/"lr"/);
      expect(dialog).toMatch(/Sankey/);
      expect(dialog).toMatch(/Flow/);
      expect(dialog).toMatch(/Network/);
      expect(dialog).toMatch(/useState<LayoutMode>\("sankey"\)/);
    });

    test("Sankey view uses d3-sankey with horizontal link path", () => {
      expect(dialog).toMatch(/d3-sankey/);
      expect(dialog).toMatch(/d3sankey/);
      expect(dialog).toMatch(/sankeyLinkHorizontal/);
      expect(dialog).toMatch(/SankeyView/);
      expect(dialog).toMatch(/SankeyPanel/);
    });

    test("Sankey Compare mode stacks Referral and Diagnosis panels", () => {
      expect(dialog).toMatch(/Symptoms recorded around referral/);
      expect(dialog).toMatch(/Symptoms linked to eventual diagnosis/);
    });

    test("starts with selectable tumour-site cards before rendering analysis", () => {
      expect(dialog).toMatch(/CancerSelector/);
      expect(dialog).toMatch(/Choose tumour sites to analyse/);
      expect(dialog).toMatch(/Analyse/);
      expect(dialog).toMatch(/Change selection/);
      expect(dialog).toMatch(/analysisStarted/);
    });

    test("filters graph links to selected tumour sites and related overlays", () => {
      expect(dialog).toMatch(/filterGraphByCancerTargets/);
      expect(dialog).toMatch(/selectedCancerIds/);
      expect(dialog).toMatch(/selectedSymptomIds/);
    });

    test("buildGraph produces referral edges from by_suspected_cancer_type", () => {
      expect(dialog).toMatch(/buildGraph/);
      expect(dialog).toMatch(/by_suspected_cancer_type/);
      expect(dialog).toMatch(/type.*referral/);
    });

    test("buildGraph produces diagnosis edges from by_diagnosed_cancer_type", () => {
      expect(dialog).toMatch(/by_diagnosed_cancer_type/);
      expect(dialog).toMatch(/type.*diagnosis/);
    });

    test("moves age and gender cohort context into rich Sankey link tooltip", () => {
      expect(dialog).toMatch(/buildSymptomDemographics/);
      expect(dialog).toMatch(/SymptomDemographics/);
      expect(dialog).toMatch(/hoveredLink/);
      expect(dialog).toMatch(/Age context/);
      expect(dialog).toMatch(/breakdown of this ribbon/);
      expect(dialog).toMatch(/Gender/);
    });

    test("compare mode applies opposing link curvature to distinguish edges", () => {
      expect(dialog).toMatch(/linkCurvature/);
      expect(dialog).toMatch(/compare/);
      // referral curls one way, diagnosis the other
      expect(dialog).toMatch(/0\.25/);
      expect(dialog).toMatch(/-0\.25/);
    });

    test("renders directional particles on links", () => {
      expect(dialog).toMatch(/linkDirectionalParticles/);
      expect(dialog).toMatch(/linkDirectionalParticleSpeed/);
      expect(dialog).toMatch(/linkDirectionalParticleColor/);
    });

    test("nodeCanvasObject uses canvas shadowBlur for glow effect", () => {
      expect(dialog).toMatch(/nodeCanvasObject/);
      expect(dialog).toMatch(/shadowBlur/);
      expect(dialog).toMatch(/shadowColor/);
    });

    test("calls zoomToFit on engine stop", () => {
      expect(dialog).toMatch(/zoomToFit/);
      expect(dialog).toMatch(/onEngineStop/);
    });

    test("carries attribution credit to Dr Ben Noble and Gateway C", () => {
      expect(dialog).toMatch(/Dr Ben Noble/);
      expect(dialog).toMatch(/gatewayc\.org\.uk\/cancer-maps/);
      expect(dialog).toMatch(/Gateway C/);
    });
  });
});
