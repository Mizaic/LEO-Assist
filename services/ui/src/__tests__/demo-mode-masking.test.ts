/**
 * VT-FA40F4D3 -- Demo mode UI masking wiring.
 *
 * Static-source verification:
 *   - settings exposes the browser-local toggle
 *   - high-risk clinical surfaces import demo-mode state and masking helpers
 *   - encounter narrative render paths call maskEncounterText
 *
 * Design Controls: DI-6FD9D8D1, DO-ACCEEF0C, VT-FA40F4D3.
 */

import fs from "fs";
import path from "path";

const SRC = path.resolve(__dirname, "..");

function read(relPath: string): string {
  return fs.readFileSync(path.join(SRC, relPath), "utf8");
}

describe("VT-FA40F4D3 demo mode UI masking wiring", () => {
  test("TC-001: preferences page exposes a browser-local demo mode toggle", () => {
    const src = read("app/settings/preferences/page.tsx");

    expect(src).toContain("useDemoMode");
    expect(src).toContain("Demo mode");
    expect(src).toContain("saved only in");
    expect(src).toContain('aria-label": "Enable demo mode"');
  });

  test("TC-002: patient finder masks NHS number, DOB, GP, and local patient id", () => {
    const src = read("components/sbar-playground/PatientFinder.tsx");

    expect(src).toContain("maskNhsNumber");
    expect(src).toContain("maskBirthDate");
    expect(src).toContain("maskGpName");
    expect(src).toContain("maskPatientId");
  });

  test("TC-003: care encounter review masks patient id, DOB-derived context, and encounter text", () => {
    const src = read("components/EncounterList.tsx");

    expect(src).toContain("maskPatientId");
    expect(src).toContain("maskBirthDate");
    expect(src).toContain("maskAge");
    expect(src).toContain("maskEncounterText(sidebarData.encounter.text)");
  });

  test("TC-004: mission control masks row, drawer, preview, and encounter-card displays", () => {
    const row = read("components/mission-control/PatientCaseRow.tsx");
    const drawer = read("components/mission-control/PatientDetailDrawer.tsx");
    const preview = read("components/mission-control/EncounterPreviewDialog.tsx");
    const card = read("components/mission-control/EncounterCard.tsx");
    const results = read("components/mission-control/EncounterResultsTable.tsx");

    expect(row).toContain("maskPatientId");
    expect(row).toContain("maskAge");
    expect(drawer).toContain("maskGpName");
    expect(preview).toContain("maskEncounterText(item.text)");
    expect(card).toContain("maskEncounterText(enc.text)");
    expect(results).toContain("maskEncounterText(row.text)");
  });

  test("TC-005: safety netting and episode views mask patient IDs, DOBs, and popover text", () => {
    const worklist = read("components/safety-netting/PatientPathwayWorklist.tsx");
    const detail = read("components/safety-netting/PathwayDetailPanel.tsx");
    const timeline = read("components/episodes/EpisodeTimelineView.tsx");

    expect(worklist).toContain("maskBirthDate(row.birth_date)");
    expect(detail).toContain("maskBirthDate(row.birth_date)");
    expect(timeline).toContain("maskPatientId(episode.patient_id)");
    expect(timeline).toContain("maskEncounterText(encounter.text)");
  });

  test("TC-006: organisation chrome masks session organisation labels", () => {
    const appShell = read("components/AppShell.tsx");
    const portal = read("app/portal/page.tsx");

    expect(appShell).toContain("maskOrgName(org.shortName || org.name)");
    expect(portal).toContain("maskOrgName(orgs[0].name)");
    expect(portal).toContain("maskPostcode(orgs[0].odsCode)");
  });
});
