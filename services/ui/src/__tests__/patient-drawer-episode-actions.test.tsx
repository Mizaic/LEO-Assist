// VT-80AAC194 -- PatientDetailDrawer integrates the unified
// EditEpisodeDialog and the +New / Delete affordances
//
// Static-source verification that the Mission Control patient
// drawer:
//   - Imports CreateEpisodeDialog, EditEpisodeDialog and
//     DeleteEpisodeConfirm and mounts each of them.
//   - Exposes three test-id'd buttons in the episode-controls row
//     so e2e and a11y suites can target them deterministically.
//   - Disables those buttons unless the caller's selected role is
//     in the curator set (clinician / qa_ra_lead /
//     platform_admin).
//   - No longer imports the legacy ReconcilePathwayDrawer; the
//     reconcile flow lives in the EditEpisodeDialog "review" tab.

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

const EPISODE_BUTTONS = [
  "patient-drawer-create-episode",
  "patient-drawer-edit-episode",
  "patient-drawer-delete-episode",
];

describe("VT-80AAC194 - PatientDetailDrawer episode actions", () => {
  const drawerSrc = read("PatientDetailDrawer.tsx");

  it("VT-MEC-DRAWER-001: imports the three new dialog components", () => {
    expect(drawerSrc).toMatch(
      /import\s+CreateEpisodeDialog\s+from\s+"\.\/CreateEpisodeDialog"/
    );
    expect(drawerSrc).toMatch(
      /import\s+EditEpisodeDialog\s+from\s+"\.\/EditEpisodeDialog"/
    );
    expect(drawerSrc).toMatch(
      /import\s+DeleteEpisodeConfirm\s+from\s+"\.\/DeleteEpisodeConfirm"/
    );
  });

  it("VT-MEC-DRAWER-002: exposes deterministic data-testids for each action", () => {
    for (const id of EPISODE_BUTTONS) {
      expect(drawerSrc).toMatch(
        new RegExp(`data-testid=\\"${id}\\"`)
      );
    }
  });

  it("VT-MEC-DRAWER-003: declares the curator role set and gates the buttons on it", () => {
    expect(drawerSrc).toMatch(/EPISODE_CURATOR_ROLES\s*=\s*new Set\(/);
    expect(drawerSrc).toMatch(/"clinician"/);
    expect(drawerSrc).toMatch(/"qa_ra_lead"/);
    expect(drawerSrc).toMatch(/"platform_admin"/);
    expect(drawerSrc).toMatch(/EPISODE_CURATOR_ROLES\.has\(reviewerRole\)/);
    // Each of the three action buttons must be disabled when the
    // role check fails. We assert the disabled prop binds the same
    // boolean (defence in depth -- the server enforces the gate too).
    expect(drawerSrc).toMatch(/disabled=\{!isEpisodeCurator\}/);
  });

  it("VT-MEC-DRAWER-004: mounts each dialog (so the buttons can open them)", () => {
    expect(drawerSrc).toMatch(/<CreateEpisodeDialog/);
    expect(drawerSrc).toMatch(/<EditEpisodeDialog/);
    expect(drawerSrc).toMatch(/<DeleteEpisodeConfirm/);
  });

  it("VT-MEC-DRAWER-005: drops the legacy ReconcilePathwayDrawer", () => {
    expect(drawerSrc).not.toMatch(/ReconcilePathwayDrawer/);
    const reviewSrc = read("ReviewActionsPanel.tsx");
    expect(reviewSrc).not.toMatch(/ReconcilePathwayDrawer/);
    // The retired reconcile button must also be gone -- the new
    // entry point is the drawer's "Edit episode" button.
    expect(reviewSrc).not.toMatch(/Reconcile pathway/);
  });

  it("VT-MEC-DRAWER-006: the patient-drawer episode controls row has a stable testid", () => {
    expect(drawerSrc).toMatch(/data-testid=\"patient-drawer-episode-controls\"/);
  });
});
