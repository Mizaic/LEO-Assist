// VT-79845292 / VT-80AAC194 -- Manual EpisodeOfCare unified edit dialog
//
// Static-source verification that EditEpisodeDialog and its three
// section sub-components (Details, Encounters, Lifecycle) form a
// single role-gated dialog that replaces the legacy
// ReconcilePathwayDrawer. The dialog SHALL:
//   - Expose 5 sections: details, encounters, review, close, merge.
//   - Send sparse PATCH bodies (only changed fields).
//   - Hard-disable destructive controls when the caller's role is
//     outside the curator set (clinician / qa_ra_lead /
//     platform_admin).
//   - Re-derive episode dates server-side after attach / detach
//     (the UI only POSTs / DELETEs and refreshes; it never sets
//     dates locally on attach).
//
// These checks read the source as text and assert structural
// invariants. They are intentionally network-free so they are stable
// in CI and on every reviewer's laptop.

import * as fs from "fs";
import * as path from "path";

const ROOT = path.resolve(__dirname, "../../../..");
const COMPONENT_DIR = path.join(
  ROOT,
  "services/ui/src/components/mission-control"
);

function read(name: string): string {
  return fs.readFileSync(path.join(COMPONENT_DIR, name), "utf-8");
}

const CURATOR_ROLES = ["clinician", "qa_ra_lead", "platform_admin"];

describe("VT-79845292 / VT-80AAC194 - EditEpisodeDialog", () => {
  it("VT-MEC-EDIT-001: dialog file exists and is a client component", () => {
    const src = read("EditEpisodeDialog.tsx");
    expect(src).toMatch(/^"use client";/m);
    expect(src).toMatch(/export default function EditEpisodeDialog/);
  });

  it("VT-MEC-EDIT-002: dialog declares all five tabbed sections", () => {
    const src = read("EditEpisodeDialog.tsx");
    expect(src).toMatch(/"details"/);
    expect(src).toMatch(/"encounters"/);
    expect(src).toMatch(/"review"/);
    expect(src).toMatch(/"close"/);
    expect(src).toMatch(/"merge"/);
    expect(src).toMatch(/TAB_ORDER:\s*EditEpisodeDialogTab\[\]/);
  });

  it("VT-MEC-EDIT-003: dialog mounts the three section sub-components", () => {
    const src = read("EditEpisodeDialog.tsx");
    expect(src).toMatch(
      /import\s+EditEpisodeDetailsTab\s+from\s+"\.\/EditEpisodeDetailsTab"/
    );
    expect(src).toMatch(
      /import\s+EditEpisodeEncountersTab\s+from\s+"\.\/EditEpisodeEncountersTab"/
    );
    expect(src).toMatch(
      /import\s+EditEpisodeLifecycleTab\s+from\s+"\.\/EditEpisodeLifecycleTab"/
    );
  });

  it("VT-MEC-EDIT-004: curator role gate is local defence in depth", () => {
    const src = read("EditEpisodeDialog.tsx");
    for (const role of CURATOR_ROLES) {
      expect(src).toMatch(new RegExp(`"${role}"`));
    }
    expect(src).toMatch(/CURATOR_ROLES\.has\(reviewerRole\)/);
    expect(src).toMatch(/Switch to[\s\S]+clinician/i);
  });

  it("VT-MEC-EDIT-005: details panel produces a sparse PATCH body", () => {
    const src = read("EditEpisodeDetailsTab.tsx");
    // Sparse body: only fields that differ from the initial form
    // are added to the payload; keys are omitted (not set to null).
    expect(src).toMatch(/EpisodeUpdateBody/);
    expect(src).toMatch(/\bupdateEpisode\b/);
    // Sentinel: the payload is built incrementally, not by sending
    // the entire form object.
    expect(src).not.toMatch(/updateEpisode\([^,]+,\s*form\b/);
  });

  it("VT-MEC-EDIT-006: encounters panel detaches via the API helper and points reviewers to the inline curation flow", () => {
    // The raw "paste encounter ID" attach form has been removed
    // in favour of the inline "Add to milestone" button on
    // EncounterCard (DI-4B99678C / DO-7986A957). This tab is now a
    // read-only-with-detach view of what is currently linked.
    const src = read("EditEpisodeEncountersTab.tsx");
    expect(src).toMatch(/\bdetachEncounterFromEpisode\b/);
    // The legacy attach form must not be reintroduced here.
    expect(src).not.toMatch(/\battachEncounterToEpisode\b/);
    expect(src).not.toMatch(/Encounter ID to attach/);
    expect(src).not.toMatch(/Paste the encounter ID/);
    // The reviewer SHALL be told where to attach encounters now.
    expect(src).toMatch(/Add to milestone/);
    expect(src).toMatch(/data-testid="edit-episode-attach-hint"/);
    // Date re-derivation is a server concern; the UI must not set
    // referral_date / end_date as a side effect of detach.
    expect(src).not.toMatch(/referral_date\s*[:=]/);
    expect(src).not.toMatch(/end_date\s*[:=]/);
  });

  it("VT-MEC-EDIT-007: lifecycle tab renders review / close / merge sections", () => {
    const src = read("EditEpisodeLifecycleTab.tsx");
    expect(src).toMatch(/\bpatchEpisodeReview\b/);
    expect(src).toMatch(/\bcloseEpisode\b/);
    expect(src).toMatch(/\bmergeEpisodes\b/);
  });

  it("VT-MEC-EDIT-008: dialog does not import the legacy ReconcilePathwayDrawer", () => {
    const src = read("EditEpisodeDialog.tsx");
    // Docstring may reference the legacy component for traceability;
    // only the import statement is forbidden.
    expect(src).not.toMatch(
      /import\s+[^\n]*ReconcilePathwayDrawer[^\n]*from/
    );
  });
});
