/**
 * Static-source VT - Patient detail drawer refreshes sibling tabs
 * when the inline encounter editor commits a coding change.
 *
 * Atlas trace:
 *   DO: DO-EE78E305 (Patient detail drawer)
 *   Also touches: DO-146D93D0 (CodedDataTab, AuditTrailTab),
 *                 DO-5312F884 (EncounterCard inline editor)
 *   DI: DI-6EA84931
 *   Look up via: get_design_control(dc_type="design-input", dc_id="DI-6EA84931")
 *
 * Bug fixed: opening /care/patients?lifecycle_bucket=confirmed_cancer,
 * editing codes inside the side drawer, and saving did not refresh
 * the Coded data or Audit trail tabs - the user had to close and
 * reopen the drawer to see the saved state.
 *
 * Static-source assertions - no network, no rendering. We pin the
 * wiring in source so the regression cannot return without a failing
 * jest run.
 */

import * as fs from "fs";
import * as path from "path";

const REPO_ROOT = path.resolve(__dirname, "../../../../..");

function readFile(relPath: string): string {
  return fs.readFileSync(path.join(REPO_ROOT, relPath), "utf8");
}

const DRAWER = "services/ui/src/components/mission-control/PatientDetailDrawer.tsx";
const ENCOUNTER_TEXT_TAB =
  "services/ui/src/components/mission-control/EncounterTextTab.tsx";
const CODED_DATA_TAB = "services/ui/src/components/mission-control/CodedDataTab.tsx";
const AUDIT_TRAIL_TAB =
  "services/ui/src/components/mission-control/AuditTrailTab.tsx";

describe("PatientDetailDrawer - refresh sibling tabs after inline coding edit", () => {
  test("TC-001: drawer holds a refreshNonce state and exposes a bumpRefresh helper", () => {
    const src = readFile(DRAWER);
    expect(src).toMatch(/const\s+\[refreshNonce,\s*setRefreshNonce\]\s*=\s*useState<number>\s*\(\s*0\s*\)|const\s+\[refreshNonce,\s*setRefreshNonce\]\s*=\s*useState\s*\(\s*0\s*\)/);
    expect(src).toMatch(/setRefreshNonce\s*\(\s*\(\s*n\s*\)\s*=>\s*n\s*\+\s*1\s*\)/);
  });

  test("TC-002: drawer wires onCodingChanged on EncounterTextTab to bumpRefresh", () => {
    const src = readFile(DRAWER);
    const encTextTag = src.match(/<EncounterTextTab[\s\S]*?\/>/);
    expect(encTextTag).not.toBeNull();
    expect(encTextTag![0]).toMatch(/onCodingChanged=\{\s*bumpRefresh\s*\}/);
  });

  test("TC-003: drawer passes refreshKey to CodedDataTab and AuditTrailTab", () => {
    const src = readFile(DRAWER);
    const codedTag = src.match(/<CodedDataTab[\s\S]*?\/>/);
    const auditTag = src.match(/<AuditTrailTab[\s\S]*?\/>/);
    expect(codedTag).not.toBeNull();
    expect(auditTag).not.toBeNull();
    expect(codedTag![0]).toMatch(/refreshKey=\{\s*refreshNonce\s*\}/);
    expect(auditTag![0]).toMatch(/refreshKey=\{\s*refreshNonce\s*\}/);
  });

  test("TC-004: drawer resets refreshNonce when the patient changes", () => {
    const src = readFile(DRAWER);
    expect(src).toMatch(/setRefreshNonce\s*\(\s*0\s*\)/);
    expect(src).toMatch(/\[\s*patient\.patient_id\s*\]/);
  });

  test("TC-005: EncounterTextTab accepts an onCodingChanged prop and forwards it from EncounterCard", () => {
    const src = readFile(ENCOUNTER_TEXT_TAB);
    expect(src).toMatch(/onCodingChanged\?:\s*\(\s*\)\s*=>\s*void/);
    expect(src).toMatch(/onCodingChanged\?\.\(\s*\)/);
  });

  test("TC-006: CodedDataTab refetches when refreshKey changes", () => {
    const src = readFile(CODED_DATA_TAB);
    expect(src).toMatch(/refreshKey\?:\s*number/);
    const effectMatch = src.match(
      /useEffect\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?fetchEncounterConcepts[\s\S]*?\}\s*,\s*\[([^\]]+)\]\s*\)/
    );
    expect(effectMatch).not.toBeNull();
    expect(effectMatch![1]).toMatch(/refreshKey/);
    expect(effectMatch![1]).toMatch(/patientId/);
  });

  test("TC-007: AuditTrailTab refetches when refreshKey changes", () => {
    const src = readFile(AUDIT_TRAIL_TAB);
    expect(src).toMatch(/refreshKey\?:\s*number/);
    const effectMatch = src.match(
      /useEffect\(\s*\(\s*\)\s*=>\s*\{[\s\S]*?fetchPatientPipelineEvents[\s\S]*?\}\s*,\s*\[([^\]]+)\]\s*\)/
    );
    expect(effectMatch).not.toBeNull();
    expect(effectMatch![1]).toMatch(/refreshKey/);
  });
});
