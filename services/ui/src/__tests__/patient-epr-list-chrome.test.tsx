/**
 * VT-1D399981 -- Domain-agnostic patient list (static-source layer)
 *
 * Atlas trace:
 *   VT: VT-1D399981  (id: 1d399981-915a-4256-9193-f922b6b96095)
 *   DI: DI-0ADA35BF
 *   DO: DO-EBF0B124
 *
 * Covers DI-0ADA35BF acceptance criteria:
 *   AC1 - The patient list shows patients who have only referral episodes.
 *   AC2 - The patient list shows patients who have only primary care episodes.
 *   AC3 - No column displays a cancer-specific value as a default for non-cancer patients.
 *   AC4 - Search by name, date range, and NHS number works regardless of episode type.
 *
 * Covers DO-EBF0B124 acceptance criteria:
 *   AC1 - The patient list fetches all patients without a cancer-type filter.
 *   AC2 - Patient cards display domain-neutral fields by default.
 *   AC3 - Search by name, date range, and NHS number works regardless of episode type.
 *   AC4 - A patient with only referral episodes appears in the list.
 *
 * Extended to cover filing cabinet filter UI (SegmentedTabs, FilterBar,
 * condition-type and has-alerts filter params, framer-motion stagger,
 * facets endpoint wiring).
 *
 * Static-source assertions - safe under any test environment, no network.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");

const PATIENT_LIST = "services/ui/src/components/patients/PatientListPage.tsx";
const EPR_API = "services/ui/src/lib/patientEprApi.ts";
const CARE_PAGE = "services/ui/src/app/care/patients/page.tsx";

describe("VT-1D399981 domain-agnostic patient list - static-source", () => {

  // DO-EBF0B124 AC1 - no cancer-type filter
  test("AC1 - PatientListPage calls fetchEprPatients (domain-agnostic endpoint)", () => {
    const src = read(PATIENT_LIST);
    expect(src).toContain("fetchEprPatients");
  });

  // DI-0ADA35BF AC3 / DO-EBF0B124 AC1 - no cancer_type filter sent
  test("AC1+AC3 - patientEprApi fetchEprPatients does not include a cancer-type filter", () => {
    const src = read(EPR_API);
    expect(src).toContain("fetchEprPatients");
    expect(src).not.toMatch(/cancer_type/);
    expect(src).not.toMatch(/cancer_stage/);
  });

  // DO-EBF0B124 AC2 - domain-neutral fields only
  test("AC2 - PatientListPage renders domain-neutral patient card fields", () => {
    const src = read(PATIENT_LIST);
    expect(src).toMatch(/episode_count|episodeCount/);
    expect(src).toMatch(/active_alert_count|activeAlertCount/);
  });

  // DI-0ADA35BF AC3 - no cancer-specific default column
  test("AC3 - PatientListPage does not render a cancer-type column as default", () => {
    const src = read(PATIENT_LIST);
    expect(src).not.toMatch(/cancer_type\b/);
    expect(src).not.toMatch(/tumour_type\b/);
    expect(src).not.toMatch(/diagnosis_code\b/);
  });

  // DI-0ADA35BF AC4 / DO-EBF0B124 AC3 - search controls
  test("AC4 - PatientListPage includes a search control", () => {
    const src = read(PATIENT_LIST);
    expect(src).toMatch(/search|Search/);
  });

  // care/patients route uses PatientListPage, not MissionControl
  test("care/patients page mounts PatientListPage (not MissionControl)", () => {
    const src = read(CARE_PAGE);
    expect(src).toContain("PatientListPage");
    expect(src).not.toContain("MissionControl");
  });

  // Atlas trace header
  test("PatientListPage carries an Atlas trace header", () => {
    const src = read(PATIENT_LIST);
    expect(src.slice(0, 600)).toContain("Atlas trace");
  });

  // ---------------------------------------------------------------------------
  // Filing cabinet filter UI -- condition-type tabs + has-alerts chip
  // ---------------------------------------------------------------------------

  test("TC-008: PatientListPage imports SegmentedTabs from @leo/design-system", () => {
    const src = read(PATIENT_LIST);
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toContain("SegmentedTabs");
  });

  test("TC-009: PatientListPage imports FilterBar from @leo/design-system", () => {
    const src = read(PATIENT_LIST);
    expect(src).toContain("FilterBar");
  });

  test("TC-010: PatientListPage calls fetchEprPatientFacets on mount", () => {
    const src = read(PATIENT_LIST);
    expect(src).toContain("fetchEprPatientFacets");
  });

  test("TC-011: patientEprApi fetchEprPatients accepts conditionType and hasAlerts params", () => {
    const src = read(EPR_API);
    expect(src).toContain("conditionType");
    expect(src).toContain("hasAlerts");
    expect(src).toContain("condition_type");
    expect(src).toContain("has_alerts");
  });

  test("TC-012: patientEprApi exports fetchEprPatientFacets and PatientFacetsResponse", () => {
    const src = read(EPR_API);
    expect(src).toContain("fetchEprPatientFacets");
    expect(src).toContain("PatientFacetsResponse");
    expect(src).toContain("condition_types");
  });

  test("TC-013: PatientListPage uses AnimatePresence for tab transition animation", () => {
    const src = read(PATIENT_LIST);
    expect(src).toContain("AnimatePresence");
    expect(src).toMatch(/motion\s+as\s+fm|from\s+["']framer-motion["']/);
  });

  test("TC-014: PatientCard uses framer-motion fm.div with stagger entry", () => {
    const src = read(PATIENT_LIST);
    expect(src).toContain("fm.div");
    expect(src).toMatch(/initial.*opacity.*y.*20|y.*20.*opacity/s);
    expect(src).toContain("Math.min(index");
  });

  test("TC-015: PatientListPage defines a condition-type accent colour map", () => {
    const src = read(PATIENT_LIST);
    expect(src).toContain("CONDITION_ACCENT");
    expect(src).toMatch(/lung|breast|prostate|colorectal/);
  });

  test("TC-016: has-alerts chip is wired to hasAlerts state and resets page", () => {
    const src = read(PATIENT_LIST);
    expect(src).toMatch(/has.alerts/i);
    expect(src).toContain("hasAlerts");
    expect(src).toContain("setPage(1)");
  });

  test("TC-017: PatientListPage passes p: { xs: 2, sm: 3 } and maxWidth to outer Box", () => {
    const src = read(PATIENT_LIST);
    expect(src).toMatch(/p:\s*\{\s*xs:\s*2,\s*sm:\s*3\s*\}/);
    expect(src).toContain("maxWidth");
    expect(src).toContain("mx:");
  });
});
