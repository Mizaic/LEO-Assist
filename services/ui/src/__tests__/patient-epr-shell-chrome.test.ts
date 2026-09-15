/**
 * VT-04B722C3 companion -- PatientShell chrome after the single-column
 * record redesign.
 *
 * Static-source verification that /care/patients/{id} keeps the clinician
 * on the named patient, puts alerts on the next job, and does not hide
 * problems behind a wide-only rail.
 *
 * Atlas trace:
 *   VT: VT-04B722C3
 *   DI: DI-357A7468
 *   DO: DO-5D3EA371
 *   DI: DI-05A16092 (one h1)
 */

import { readFileSync } from "fs";
import { join } from "path";

const REPO_ROOT = join(__dirname, "../../../..");

function readUi(rel: string): string {
  return readFileSync(join(REPO_ROOT, "services/ui/src", rel), "utf8");
}

describe("Patient EPR shell chrome", () => {
  test("TC-001: PatientHeader renders the patient name as the page h1", () => {
    const src = readUi("components/patients/PatientHeader.tsx");
    expect(src).toMatch(/component=["']h1["']/);
    expect(src).toMatch(/display_name/);
    expect(src).toMatch(/displayName/);
  });

  test("TC-002: PatientHeader alert control opens the Alerts tab", () => {
    const src = readUi("components/patients/PatientHeader.tsx");
    expect(src).toMatch(/onOpenAlerts/);
    expect(src).toMatch(/Review/);
    expect(src).toMatch(/epr-review-alerts/);
  });

  test("TC-003: PatientShell uses SegmentedTabs with a section aria-label", () => {
    const src = readUi("components/patients/PatientShell.tsx");
    expect(src).toMatch(/from\s+["']@leo\/design-system["']/);
    expect(src).toMatch(/SegmentedTabs/);
    expect(src).toMatch(/aria-label=["']Patient record sections["']/);
    expect(src).not.toMatch(/from\s+["']@mui\/material\/Tabs["']/);
  });

  test("TC-004: PatientShell is a single reading column (no side rails)", () => {
    const src = readUi("components/patients/PatientShell.tsx");
    expect(src).not.toMatch(/ContextRail/);
    expect(src).not.toMatch(/ClinicalContextRail/);
    expect(src).not.toMatch(/100vh/);
  });

  test("TC-008: Documents tab fills the remaining column height", () => {
    const src = readUi("components/patients/PatientShell.tsx");
    expect(src).toMatch(/overflow:\s*wideTab\s*\?\s*["']hidden["']/);
    expect(src).toMatch(/WIDE_TABS/);
  });

  test("TC-009: selected record tab uses brand colour so it still reads without the pill", () => {
    const src = readFileSync(
      join(REPO_ROOT, "services/design-system/src/primitives/SegmentedTabs.tsx"),
      "utf8",
    );
    expect(src).toMatch(/color\.brand\.primary/);
    expect(src).toMatch(/selected/);
  });

  test("TC-005: PatientShell surfaces timeline and entity load failures", () => {
    const shell = readUi("components/patients/PatientShell.tsx");
    const load = readUi("components/patients/usePatientRecord.ts");
    expect(shell).toMatch(/timelineError/);
    expect(shell).toMatch(/entitiesError/);
    expect(load).not.toMatch(/\.catch\(\(\)\s*=>\s*\{\s*\}\)/);
  });

  test("TC-006: Overview always shows problems, alerts, and medicines", () => {
    const src = readUi("components/patients/OverviewPanel.tsx");
    expect(src).toMatch(/NudgeStrip/);
    expect(src).toMatch(/epr-next-job/);
    expect(src).toMatch(/epr-overview-context/);
    expect(src).toMatch(/epr-overview-medicines/);
    expect(src).not.toMatch(/epr-overview-context-fallback/);
    expect(src).not.toMatch(/xl:\s*["']none["']/);
  });

  test("TC-007: Overview keeps Latest SBAR as the primary clinical pane", () => {
    const src = readUi("components/patients/OverviewPanel.tsx");
    expect(src).toMatch(/LeoSbarHost/);
    expect(src).toMatch(/epr-latest-sbar/);
    expect(src).toMatch(/Latest SBAR/);
    expect(src).not.toMatch(/Patient details/);
    expect(src).not.toMatch(/NHS number/);
  });
});
