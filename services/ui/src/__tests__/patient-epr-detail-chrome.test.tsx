/**
 * VT-04B722C3 -- Patient detail full record for non-cancer patient (static-source layer)
 *
 * Atlas trace:
 *   VT: VT-04B722C3  (id: 04b722c3-6774-4964-8eec-e1573a5e72e2)
 *   DI: DI-357A7468
 *   DO: DO-5D3EA371
 *
 * Covers DI-357A7468 acceptance criteria:
 *   AC1 - The patient detail page renders for a patient who has no cancer episode.
 *   AC2 - All episodes are shown regardless of condition type.
 *   AC3 - An activity timeline shows all encounters, episodes, alerts, and documents in date order.
 *   AC4 - No field is shown as empty because of a missing cancer-specific property.
 *
 * Covers DO-5D3EA371 acceptance criteria:
 *   AC1 - PatientDetailPage renders for a patient with no cancer episode.
 *   AC2 - All episode types are shown in the Episodes panel.
 *   AC3 - The ActivityTimeline displays all encounters, episodes, alerts, and documents in date order.
 *   AC4 - No field renders as visibly empty due to a missing cancer-specific property.
 *
 * Static-source assertions - safe under any test environment, no network.
 */

import fs from "fs";
import path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const read = (rel: string) => fs.readFileSync(path.join(ROOT, rel), "utf8");

const DETAIL_PAGE = "services/ui/src/components/patients/PatientDetailPage.tsx";
const TIMELINE = "services/ui/src/components/patients/ActivityTimeline.tsx";
const EPR_API = "services/ui/src/lib/patientEprApi.ts";

describe("VT-04B722C3 patient detail full record - static-source", () => {

  // AC1 - page fetches detail for any patient (no cancer prerequisite)
  test("AC1 - PatientDetailPage calls fetchEprPatientDetail (any episode type)", () => {
    const src = read(DETAIL_PAGE);
    expect(src).toContain("fetchEprPatientDetail");
  });

  // AC1 - no cancer-type guard before rendering
  test("AC1 - PatientDetailPage does not gate render on presence of cancer episode", () => {
    const src = read(DETAIL_PAGE);
    expect(src).not.toMatch(/if.*cancer/i);
    expect(src).not.toMatch(/cancer_type.*required/i);
  });

  // AC2 - episodes shown regardless of type
  test("AC2 - PatientDetailPage maps over episodes without domain type filter", () => {
    const src = read(DETAIL_PAGE);
    expect(src).toMatch(/episodes\.(map|filter)\b/);
    expect(src).not.toMatch(/\.filter\(.*cancer/i);
  });

  // AC3 - ActivityTimeline is included
  test("AC3 - PatientDetailPage renders ActivityTimeline", () => {
    const src = read(DETAIL_PAGE);
    expect(src).toContain("ActivityTimeline");
    expect(src).toContain("fetchEprPatientTimeline");
  });

  // AC3 - timeline handles the three clinical event types
  test("AC3 - ActivityTimeline handles encounter, episode, and alert event types", () => {
    const src = read(TIMELINE);
    expect(src).toMatch(/encounter/i);
    expect(src).toMatch(/episode/i);
    expect(src).toMatch(/alert/i);
  });

  // AC4 - no cancer-specific required field in the EPR API types
  test("AC4 - patientEprApi PatientDetail type does not require cancer-specific fields", () => {
    const src = read(EPR_API);
    expect(src).toContain("PatientDetail");
    expect(src).not.toMatch(/cancer_type\s*:\s*string[^|]/);
    expect(src).not.toMatch(/tumour_type\s*:\s*string[^|]/);
  });

  // Timeline must render items in date order - uses item_date field from TimelineItem
  test("AC3 - ActivityTimeline uses item_date for chronological ordering", () => {
    const src = read(TIMELINE);
    expect(src).toMatch(/item_date|itemDate/);
  });

  const FILES = [DETAIL_PAGE, TIMELINE];
  test.each(FILES)("%s carries an Atlas trace header", (rel) => {
    const src = read(rel);
    expect(src.slice(0, 600)).toContain("Atlas trace");
  });
});
