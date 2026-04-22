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
    // Multi-slot (DI-F5E030ED): the label is built from the array of
    // currently-linked slots and joined with " + ".
    expect(src).toMatch(/linkedSlots\.map\(milestoneLabel\)\.join\(" \+ "\)/);
    expect(src).toMatch(/data-milestone-linked=/);
    expect(src).toMatch(/data-milestone-slot-count=/);
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

  it("VT-DEF041C5-TC-002: EncounterTextTab passes currentMilestoneTypes + onCurateMilestone to every card", () => {
    const src = readComponent("EncounterTextTab.tsx");
    expect(src).toMatch(/buildMilestoneLookup/);
    expect(src).toMatch(/useMilestoneCuration/);
    // Multi-slot wiring: pass an array of milestoneType strings.
    expect(src).toMatch(/currentMilestoneTypes=\{[\s\S]*?milestoneLookup\.get/);
    expect(src).toMatch(/\.map\([\s\S]{0,40}=>[\s\S]{0,40}\.milestoneType\s*\)/);
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

  it("VT-DEF041C5-TC-004: MilestoneCurationDialog stages pick -> (conflict | notice) -> confirm -> result", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    expect(src).toMatch(/data-testid="milestone-curation-dialog"/);
    const partsSrc = readComponent("MilestoneCurationParts.tsx");
    const actionsSrc = readComponent("MilestoneCurationActions.tsx");
    const resultsSrc = readComponent("MilestoneCurationResults.tsx");
    // Stage type now enumerates the five stages: notice was added
    // for context-tier soft-conflict handling (DI-50C7E89C).
    expect(partsSrc).toMatch(
      /export type Stage =\s*"pick"\s*\|\s*"conflict"\s*\|\s*"notice"\s*\|\s*"confirm"\s*\|\s*"result";/
    );
    // Pick step: episode + slot + day-encounter list.
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-episode"/);
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-slot"/);
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-day-encounters"/);
    // Conflict step (pathway tier): warning alert + Replace.
    expect(partsSrc).toMatch(/data-testid="milestone-dialog-conflict"/);
    expect(actionsSrc).toMatch(/data-testid="milestone-dialog-replace"/);
    expect(actionsSrc).toMatch(
      /data-testid="milestone-dialog-pick-different-slot"/
    );
    // Notice step (context tier): info alert + Add anyway, NO Replace.
    expect(resultsSrc).toMatch(/data-testid="milestone-dialog-notice"/);
    expect(actionsSrc).toMatch(/data-testid="milestone-dialog-add-anyway"/);
    // Confirm step.
    expect(src).toMatch(/data-testid="milestone-dialog-confirm"/);
    expect(actionsSrc).toMatch(
      /data-testid="milestone-dialog-confirm-attach"/
    );
    // Result step lives in the new results module after the multi-slot
    // split (DI-F5E030ED).
    expect(resultsSrc).toMatch(/data-testid="milestone-dialog-result"/);
    expect(actionsSrc).toMatch(/data-testid="milestone-dialog-close"/);
  });

  it("VT-DEF041C5-TC-004b: detectConflicts splits pathway conflicts from context notices (DI-50C7E89C)", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    const opts = readComponent("milestoneOptions.ts");
    // Tier helpers exist on the vocabulary.
    expect(opts).toMatch(/export function isContextMilestone/);
    expect(opts).toMatch(/export function milestoneTier/);
    // detectConflicts returns both buckets and routes context-tier
    // slots to notices, pathway-tier slots to conflicts.
    expect(src).toMatch(
      /interface ConflictBuckets\s*\{[\s\S]*?conflicts:\s*SlotConflict\[\];[\s\S]*?notices:\s*SlotNotice\[\];/
    );
    expect(src).toMatch(
      /function detectConflicts[\s\S]*?\):\s*ConflictBuckets/
    );
    expect(src).toMatch(/if \(isContextMilestone\(mt\)\)/);
    // handleProceed routes pathway > notice > confirm.
    expect(src).toMatch(
      /if \(conflicts\.length > 0\)\s*\{[\s\S]{0,80}setStage\("conflict"\);/
    );
    expect(src).toMatch(
      /if \(notices\.length > 0\)\s*\{[\s\S]{0,80}setStage\("notice"\);/
    );
    // The notice action row reuses runAttach (no detach) so existing
    // context-tier days are never undone.
    const dialog = src;
    expect(dialog).toMatch(/onConfirmAttach=\{runAttach\}/);
    // Notice render uses NoticeAlert from the results module.
    expect(dialog).toMatch(/<NoticeAlert notices=\{notices\}/);
  });

  it("VT-DEF041C5-TC-005: dialog detects same-slot different-day conflicts per picked slot and suppresses self-conflict", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    // detectConflicts loops over the picked slot list, groups by
    // milestone_type, and excludes any milestone whose date already
    // matches the chosen day so re-saving the same day-group does
    // not look like a conflict (DI-F5E030ED).
    expect(src).toMatch(/function detectConflicts/);
    expect(src).toMatch(/for \(const mt of milestoneTypes\)/);
    expect(src).toMatch(/m\.milestone_type === mt/);
    expect(src).toMatch(/isoDay\(m\.date\) !== chosenDay/);
  });

  it("VT-DEF041C5-TC-006: dialog per-slot remove chip calls detach with milestone_type filter", () => {
    // Multi-slot (DI-F5E030ED): the remove path now lives on the
    // existing-link chips in PickStage. Each chip's onDelete routes
    // through handleRemoveExistingLink, which calls
    // detachEncounterDayFromMilestone with the slot-specific
    // milestoneType so only that edge is removed.
    const src = readComponent("MilestoneCurationDialog.tsx");
    const parts = readComponent("MilestoneCurationParts.tsx");
    expect(src).toMatch(/handleRemoveExistingLink/);
    expect(src).toMatch(/detachEncounterDayFromMilestone\(/);
    expect(src).toMatch(/milestoneType:\s*link\.milestoneType/);
    expect(parts).toMatch(
      /data-testid=\{`milestone-dialog-existing-chip-\$\{link\.milestoneType\}`\}/
    );
    // The result banner names the slot the reviewer just cleared.
    expect(src).toMatch(/milestone_type:\s*link\.milestoneType/);
  });

  it("VT-DEF041C5-TC-007: dialog Replace path detaches each conflicting slot, then attaches the multi-slot batch", () => {
    const src = readComponent("MilestoneCurationDialog.tsx");
    const replaceMatch = src.match(/runReplace[\s\S]*?\n  };/);
    expect(replaceMatch).not.toBeNull();
    const body = replaceMatch![0];
    // Multi-slot replace (DI-F5E030ED): detach loops per-conflict,
    // then a single multi-slot attach call covers every picked slot.
    const detachIdx = body.indexOf("detachEncounterDayFromMilestone");
    const attachIdx = body.indexOf("attachEncounterDayToMultipleMilestones");
    expect(detachIdx).toBeGreaterThan(-1);
    expect(attachIdx).toBeGreaterThan(detachIdx);
    expect(body).toMatch(/for \(const c of conflicts\)/);
    // No new server endpoint -- both helpers wrap the existing
    // single-encounter attach / detach.
    const apiSrc = readLib("missionControlApi.ts");
    const attachDayMatch = apiSrc.match(
      /export async function attachEncounterDayToMilestone[\s\S]*?\n}/
    );
    const detachDayMatch = apiSrc.match(
      /export async function detachEncounterDayFromMilestone[\s\S]*?\n}/
    );
    const multiMatch = apiSrc.match(
      /export async function attachEncounterDayToMultipleMilestones[\s\S]*?\n}/
    );
    expect(attachDayMatch).not.toBeNull();
    expect(detachDayMatch).not.toBeNull();
    expect(multiMatch).not.toBeNull();
    expect(attachDayMatch![0]).toMatch(/attachEncounterToEpisode\(/);
    expect(detachDayMatch![0]).toMatch(/detachEncounterFromEpisode\(/);
    expect(multiMatch![0]).toMatch(/attachEncounterDayToMilestone\(/);
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

  it("VT-DEF041C5-TC-011: dialog pick stage is an explicit per-encounter multi-select; trigger encounter is the only default", () => {
    const dialog = readComponent("MilestoneCurationDialog.tsx");
    const parts = readComponent("MilestoneCurationParts.tsx");
    // The dialog tracks a selected set seeded from the trigger encounter.
    expect(dialog).toMatch(/useState<Set<string>>\(new Set\(\)\)/);
    expect(dialog).toMatch(
      /seed\.add\(String\(triggerEncounter\.encounter_id\)\)/
    );
    // PickStage renders a Checkbox per same-day encounter.
    expect(parts).toMatch(/<Checkbox/);
    expect(parts).toMatch(
      /data-testid=\{`milestone-dialog-day-encounter-\$\{id\}`\}/
    );
    // attach / replace / remove all consume the selected list, not
    // the full same-day group.
    expect(dialog).toMatch(/encounterIds:\s*selectedList/);
    expect(dialog).not.toMatch(
      /encounterIds:\s*sameDayEncounters\.map\(\(e\) => String\(e\.encounter_id\)\)/
    );
    // Continue / Remove / Replace are gated on a non-empty selection
    // and on at least one milestone slot being picked (DI-F5E030ED).
    // The action row was extracted to MilestoneCurationActions.tsx
    // when the notice-stage buttons landed (DI-50C7E89C).
    const actions = readComponent("MilestoneCurationActions.tsx");
    expect(actions).toMatch(/const noneSelected = selectedCount === 0/);
    expect(actions).toMatch(/const noSlot = slotCount === 0/);
    // Continue is also gated on noEpisode (DI-74AF7AD8) so the
    // dialog cannot attach to a pathway the curator never picked.
    expect(actions).toMatch(
      /episodesEmpty\s*\|\|\s*\n?\s*noEpisode\s*\|\|\s*\n?\s*noneSelected\s*\|\|\s*\n?\s*noSlot/
    );
  });

  it("VT-DEF041C5-TC-012: pick stage exposes a multi-select milestone slot picker (DI-F5E030ED)", () => {
    const parts = readComponent("MilestoneCurationParts.tsx");
    // The slot input is multi-select: SelectProps.multiple=true, the
    // value is a string[], and already-linked slots are disabled in
    // the dropdown so the reviewer cannot accidentally re-pick them.
    expect(parts).toMatch(/multiple:\s*true/);
    expect(parts).toMatch(/milestoneTypes:\s*string\[\]/);
    expect(parts).toMatch(/setMilestoneTypes:\s*\(v:\s*string\[\]\)\s*=>\s*void/);
    expect(parts).toMatch(/linkedOnEpisode\.has\(opt\.value\)/);
    expect(parts).toMatch(/disabled=\{linked\}/);
    expect(parts).toMatch(
      /data-testid=\{`milestone-dialog-slot-option-\$\{opt\.value\}`\}/
    );
    expect(parts).toMatch(
      /data-testid=\{`milestone-dialog-slot-chip-\$\{mt\}`\}/
    );
  });

  it("VT-DEF041C5-TC-013: pick stage caps both Select popovers and anchors them downward so the dialog action row stays reachable (DI-4B99678C)", () => {
    // Regression: the MUI Select popover defaults to ~50% of the
    // viewport, which on a tall dialog covered the Cancel / Continue
    // row and trapped the curator in the dropdown. Both selects must
    // pin a maxHeight on PaperProps and anchor below the field so the
    // action row stays visible.
    const parts = readComponent("MilestoneCurationParts.tsx");
    // Episode picker: maxHeight on its PaperProps and downward anchor.
    expect(parts).toMatch(
      /"data-testid":\s*"milestone-dialog-episode-menu"[\s\S]{0,120}maxHeight:\s*\d+/
    );
    // Slot picker: same treatment, larger cap because it has groups.
    expect(parts).toMatch(
      /"data-testid":\s*"milestone-dialog-slot-menu"[\s\S]{0,120}maxHeight:\s*\d+/
    );
    // Both popovers anchor under the field (vertical: "bottom" anchor,
    // vertical: "top" transform) so the menu cannot grow upward over
    // a higher field and so it pushes the picker downward away from
    // the action row at the bottom of the dialog.
    const anchorMatches = parts.match(
      /anchorOrigin:\s*\{\s*vertical:\s*"bottom",\s*horizontal:\s*"left"\s*\}/g
    );
    expect(anchorMatches?.length ?? 0).toBeGreaterThanOrEqual(2);
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
