// VT-DEF041C5 -- Per-encounter inline milestone curation
//
// Static-source verification that the inline "Add to milestone" /
// "Linked: <slot>" curation flow is wired correctly across
// EncounterCard, MilestoneCurationDialog, useMilestoneCuration and
// the missionControlApi orchestrators. The flow SHALL:
//   - Surface a button next to "Edit codes" on every EncounterCard
//     that reads "Add to milestone" or "Linked: <slot>" depending
//     on whether the encounter already fills a milestone slot.
//   - Open a dialog whose pick step lets the curator choose any of
//     the patient's existing episodes plus a milestone slot from
//     the same vocabulary as the legacy attach form.
//   - Call attachEncounterDayToMilestone, which iterates every
//     same-day encounter through the existing per-encounter attach
//     endpoint so the audit trail and date re-derivation keep
//     working.
//   - Detect a same-slot conflict in episode.milestones whose date
//     differs from the chosen day and offer Replace / Pick another
//     slot.
//   - Never display raw encounter IDs in the dialog body.
//
// These checks read the source as text and assert structural
// invariants -- no network, no React render.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const COMPONENT_DIR = path.join(
  ROOT,
  "services/ui/src/components/mission-control"
);
const LIB_DIR = path.join(ROOT, "services/ui/src/lib");

function readComponent(name: string): string {
  return fs.readFileSync(path.join(COMPONENT_DIR, name), "utf-8");
}

function readLib(name: string): string {
  return fs.readFileSync(path.join(LIB_DIR, name), "utf-8");
}

describe("VT-DEF041C5 - inline milestone curation chrome", () => {
  it("VT-DEF041C5-TC-001: EncounterCard renders the milestone button and toggles its label by linkage state", () => {
    const src = readComponent("EncounterCard.tsx");
    expect(src).toMatch(/data-testid="encounter-card-milestone-button"/);
    expect(src).toMatch(/Add to milestone/);
    expect(src).toMatch(/Linked: \$\{milestoneLabel\(currentMilestoneType\)\}/);
    expect(src).toMatch(/data-milestone-linked=/);
    expect(src).toMatch(/onCurateMilestone\?: \(\) => void/);
    // The new button must sit next to (i.e. inside the same action
    // row as) the existing "Edit codes" button.
    const editCodesIdx = src.indexOf('data-testid="encounter-card-edit-codes"');
    const milestoneIdx = src.indexOf(
      'data-testid="encounter-card-milestone-button"'
    );
    expect(editCodesIdx).toBeGreaterThan(0);
    expect(milestoneIdx).toBeGreaterThan(editCodesIdx);
  });

  it("VT-DEF041C5-TC-002: EncounterTextTab passes currentMilestoneType + onCurateMilestone to every card", () => {
    const src = readComponent("EncounterTextTab.tsx");
    expect(src).toMatch(/buildMilestoneLookup/);
    expect(src).toMatch(/useMilestoneCuration/);
    expect(src).toMatch(/currentMilestoneType=\{[\s\S]*?milestoneLookup\.get/);
    expect(src).toMatch(/onCurateMilestone=\{\(\) => curate\.open\(enc\)\}/);
    // The dialog mounts and consumes the same hook.
    expect(src).toMatch(/<MilestoneCurationDialog/);
    expect(src).toMatch(/triggerEncounter=\{curate\.triggerEncounter\}/);
    expect(src).toMatch(/sameDayEncounters=\{curate\.sameDayEncounters\}/);
  });

  it("VT-DEF041C5-TC-003: useMilestoneCuration groups encounters by 10-char ISO date prefix", () => {
    const src = readComponent("useMilestoneCuration.ts");
    expect(src).toMatch(/buildMilestoneLookup/);
    expect(src).toMatch(/useMilestoneCuration/);
    expect(src).toMatch(/String\(value\)\.slice\(0,\s*10\)/);
    expect(src).toMatch(/encounters[\s\S]{0,40}\.filter[\s\S]{0,40}isoDay/);
  });

  it("VT-DEF041C5-TC-004: MilestoneCurationDialog stages pick -> conflict -> confirm -> result", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    expect(src).toMatch(/data-testid="milestone-curation-dialog"/);
    // Stage type-script enumerates the four stages.
    const partsSrc = readComponent("MilestoneCurationParts.tsx");
    expect(partsSrc).toMatch(
      /export type Stage =\s*"pick"\s*\|\s*"conflict"\s*\|\s*"confirm"\s*\|\s*"result";/
    );
    // Pick step: episode + slot + day-encounter list.
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-episode"/);
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-slot"/);
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-day-encounters"/);
    // Conflict step: warning alert with the existing date + preview.
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-conflict"/);
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-replace"/);
    expect(partsSrc).toMatch(
      /data-testid="milestone-dialog-pick-different-slot"/
    );
    // Confirm step.
    expect(src).toMatch(/data-testid="milestone-dialog-confirm"/);
    expect(partsSrc).toMatch(
      /data-testid="milestone-dialog-confirm-attach"/
    );
    // Result step.
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-result"/);
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-close"/);
  });

  it("VT-DEF041C5-TC-005: dialog detects a same-slot, different-day conflict and suppresses self-conflict", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    // detectConflict groups by milestone_type and excludes any
    // milestone whose date already matches the chosen day, so
    // re-saving the same day-group does not look like a conflict.
    expect(src).toMatch(/function detectConflict/);
    expect(src).toMatch(/m\.milestone_type === milestoneType/);
    expect(src).toMatch(/isoDay\(m\.date\) !== chosenDay/);
  });

  it("VT-DEF041C5-TC-006: dialog Remove path uses the existing-link slot from the trigger encounter", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    const parts = readComponent("MilestoneCurationParts.tsx");
    expect(src).toMatch(/runRemove/);
    expect(src).toMatch(/detachEncounterDayFromMilestone\(/);
    expect(parts).toMatch(/data-testid="milestone-dialog-remove"/);
    // The remove path attaches the existing slot to the result so
    // the success banner names the slot the reviewer just cleared.
    expect(src).toMatch(
      /milestone_type:\s*existingLink\.milestoneType/
    );
  });

  it("VT-DEF041C5-TC-007: dialog Replace path detaches first, then attaches; both via existing endpoints", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    const replaceMatch = src.match(/runReplace[\s\S]*?\n  };/);
    expect(replaceMatch).not.toBeNull();
    const body = replaceMatch![0];
    const detachIdx = body.indexOf("detachEncounterDayFromMilestone");
    const attachIdx = body.indexOf("attachEncounterDayToMilestone");
    expect(detachIdx).toBeGreaterThan(-1);
    expect(attachIdx).toBeGreaterThan(detachIdx);
    // No new server endpoint -- both helpers wrap the existing
    // single-encounter attach / detach.
    const apiSrc = readLib("missionControlApi.ts");
    const attachDayMatch = apiSrc.match(
      /export async function attachEncounterDayToMilestone[\s\S]*?\n}/
    );
    const detachDayMatch = apiSrc.match(
      /export async function detachEncounterDayFromMilestone[\s\S]*?\n}/
    );
    expect(attachDayMatch).not.toBeNull();
    expect(detachDayMatch).not.toBeNull();
    expect(attachDayMatch![0]).toMatch(/attachEncounterToEpisode\(/);
    expect(detachDayMatch![0]).toMatch(/detachEncounterFromEpisode\(/);
  });

  it("VT-DEF041C5-TC-008: dialog body never displays raw encounter IDs as text", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    const partsSrc = readComponent("MilestoneCurationParts.tsx");
    const combined = `${src}\n${partsSrc}`;
    // The same-day encounter list shows date + text snippet only;
    // encounter_id appears only as a React `key={...}` prop or in a
    // per-failure diagnostic line under result.failed[].
    // Guard: assert that every `{X.encounter_id}` occurrence is
    // preceded by `key=` (a React key) or is the failed-encounter
    // diagnostic that names the offender.
    const re = /(\bkey=)?\{\s*([A-Za-z_]+)\.encounter_id\s*\}/g;
    const offenders: string[] = [];
    let match: RegExpExecArray | null;
    while ((match = re.exec(combined))) {
      const isKeyProp = Boolean(match[1]);
      const subject = match[2];
      if (isKeyProp) continue;
      if (subject === "f") continue; // result.failed[] diagnostic
      offenders.push(match[0]);
    }
    expect(offenders).toEqual([]);
  });

  it("VT-DEF041C5-TC-009: shared milestone vocabulary lives in milestoneOptions.ts and is reused by both surfaces", () => {
    const opts = readComponent("milestoneOptions.ts");
    expect(opts).toMatch(/export const MILESTONE_OPTIONS/);
    expect(opts).toMatch(/export function milestoneLabel/);
    // Both card and dialog consume the shared label helper.
    const card = readComponent("EncounterCard.tsx");
    const partsSrc = readComponent("MilestoneCurationParts.tsx");
    expect(card).toMatch(
      /import\s+\{\s*milestoneLabel\s*\}\s*from\s*"\.\/milestoneOptions"/
    );
    expect(partsSrc).toMatch(
      /import\s+\{[^}]*MILESTONE_OPTIONS[^}]*\}\s+from\s+"\.\/milestoneOptions"/
    );
  });

  it("VT-DEF041C5-TC-010: EditEpisodeEncountersTab no longer offers a paste-encounter-ID attach form", () => {
    const src = readComponent("EditEpisodeEncountersTab.tsx");
    expect(src).not.toMatch(/Encounter ID to attach/);
    expect(src).not.toMatch(/Paste the encounter ID/);
    expect(src).not.toMatch(/edit-episode-attach-button/);
    expect(src).not.toMatch(/\battachEncounterToEpisode\b/);
    // The detach affordance and the linked-encounter list stay.
    expect(src).toMatch(/\bdetachEncounterFromEpisode\b/);
    expect(src).toMatch(/data-testid="edit-episode-linked-encounters"/);
    // The reviewer is told where to attach now.
    expect(src).toMatch(/data-testid="edit-episode-attach-hint"/);
    expect(src).toMatch(/Add to milestone/);
  });
});
