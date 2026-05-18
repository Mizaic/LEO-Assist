/**
 * Static-source VT - Patient detail drawer refreshes sibling tabs
 * when the inline encounter editor commits a coding change.
 *
 * Atlas trace:
 *   VT: VT-E3F857AA
 *   VERIFIES: DI-AA1F5F5B (Mission Control SHALL co-locate AI
 *             output, state, and actions; AC: "Live pipeline events
 *             appear without manual refresh", "Reviewer actions
 *             complete optimistically and reconcile against the
 *             server response.")
 *   TESTS:    DO-5312F884 (Mission Control UI implementation,
 *             services/ui/src/components/mission-control/*)
 *   Parent UN: UN-0A3167F4
 *   Look up via:
 *     get_design_control(dc_type="verification-test", dc_id="VT-E3F857AA")
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

  test("TC-002: drawer wires onCodingChanged on EncounterTextTab to a combined refresh handler", () => {
    // The handler must do TWO things, mirroring the milestone
    // attach / detach refresh path:
    //   (a) bumpRefresh()        - sibling tabs (CodedDataTab,
    //                              AuditTrailTab) refetch via the
    //                              refreshKey nonce.
    //   (b) triggerLiveRefresh() - the drawer-local episode list
    //                              refetches so the chip rail and
    //                              Overview tab pick up changed
    //                              audit_flag / coded summaries.
    // Wiring `onCodingChanged` straight to bumpRefresh (the old
    // behaviour) only covered (a), so the chip rail stayed stale
    // until the user closed and reopened the drawer.
    const src = readFile(DRAWER);
    const encTextTag = src.match(/<EncounterTextTab[\s\S]*?\/>/);
    expect(encTextTag).not.toBeNull();
    expect(encTextTag![0]).toMatch(/onCodingChanged=\{\s*handleCodingChanged\s*\}/);
    const handlerMatch = src.match(
      /const\s+handleCodingChanged\s*=\s*\(\s*\)\s*=>\s*\{([\s\S]*?)\};/
    );
    expect(handlerMatch).not.toBeNull();
    const body = handlerMatch![1];
    expect(body).toMatch(/bumpRefresh\(\s*\)/);
    expect(body).toMatch(/triggerLiveRefresh\(\s*\)/);
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
    // The reset effect's dep array must contain patient.patient_id
    // (it may also contain patient.episodes -- that is the
    // drawerEpisodes seeding effect).
    expect(src).toMatch(/\[\s*patient\.patient_id(?:\s*,\s*patient\.episodes)?\s*\]/);
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

  test("TC-008: triggerLiveRefresh refetches the drawer-local episode list", () => {
    // triggerLiveRefresh must call refreshDrawerEpisodes() so the
    // chip rail / Overview tab refetch via the
    // /mission-control/patients/{patient_id}/episodes endpoint.
    // Without this, an "Edit codes" save updates sibling tabs but
    // leaves the chip rail and overview showing pre-edit state.
    const src = readFile(DRAWER);
    const triggerMatch = src.match(
      /const\s+triggerLiveRefresh\s*=\s*\(\s*\)\s*=>\s*\{([\s\S]*?)\};/
    );
    expect(triggerMatch).not.toBeNull();
    expect(triggerMatch![1]).toMatch(/refreshDrawerEpisodes\(\s*\)/);
  });

  test("TC-009: EncounterTextTab refreshes the encounter list after a coding edit", () => {
    // The per-card `coded_count` badge comes from useEncounterLoad,
    // not /coded-links, so the inline /coded-links refetch alone
    // leaves it stale. The card's onCodingChanged callback must
    // also call refresh() so the badge updates without the user
    // having to recode or close the drawer.
    const src = readFile(ENCOUNTER_TEXT_TAB);
    const cardTag = src.match(/<EncounterCard[\s\S]*?\/>\s*\)\s*;/);
    expect(cardTag).not.toBeNull();
    const onCodingChangedMatch = cardTag![0].match(
      /onCodingChanged=\{\s*\(\s*\)\s*=>\s*\{([\s\S]*?)\}\s*\}/
    );
    expect(onCodingChangedMatch).not.toBeNull();
    const body = onCodingChangedMatch![1];
    expect(body).toMatch(/invalidateCodedFor\(\s*encounterKey\s*\)/);
    expect(body).toMatch(/fetchCodesForEncounter\(\s*encounterKey\s*\)/);
    expect(body).toMatch(/refresh\(\s*\)/);
    expect(body).toMatch(/onCodingChanged\?\.\(\s*\)/);
  });

  test("TC-010: coded-data rows can request the linked encounter text", () => {
    const src = readFile(CODED_DATA_TAB);
    expect(src).toMatch(/onOpenEncounterText\?:\s*\(\s*encounterId:\s*string\s*\)\s*=>\s*void/);
    expect(src).toMatch(/role=\{\s*onOpenEncounterText\s*\?\s*"button"\s*:\s*undefined\s*\}/);
    expect(src).toMatch(/tabIndex=\{\s*onOpenEncounterText\s*\?\s*0\s*:\s*undefined\s*\}/);
    expect(src).toMatch(/onKeyDown=\{\s*\(event\)\s*=>\s*\{/);
    expect(src).toMatch(/onOpenEncounterText\?\.\(\s*row\.encounter_id\s*\)/);
  });

  test("TC-011: drawer routes coded-data row clicks to EncounterTextTab focus", () => {
    const src = readFile(DRAWER);
    expect(src).toMatch(/const\s+\[encounterTextFocusId,\s*setEncounterTextFocusId\]/);
    expect(src).toMatch(/setEncounterTextFocusId\(\s*encounterId\s*\)/);
    expect(src).toMatch(/setTab\(\s*2\s*\)/);
    const codedTag = src.match(/<CodedDataTab[\s\S]*?\/>/);
    const encTextTag = src.match(/<EncounterTextTab[\s\S]*?\/>/);
    expect(codedTag).not.toBeNull();
    expect(encTextTag).not.toBeNull();
    expect(codedTag![0]).toMatch(/onOpenEncounterText=\{\s*openEncounterTextFromCode\s*\}/);
    expect(encTextTag![0]).toMatch(/focusEncounterId=\{\s*encounterTextFocusId\s*\}/);
  });

  test("TC-012: EncounterTextTab consumes drawer focus requests via existing jump helper", () => {
    const src = readFile(ENCOUNTER_TEXT_TAB);
    expect(src).toMatch(/focusEncounterId\?:\s*string\s*\|\s*null/);
    expect(src).toMatch(/if\s*\(\s*focusEncounterId\s*\)\s*jumpToEncounter\(\s*focusEncounterId\s*\)/);
  });
});
