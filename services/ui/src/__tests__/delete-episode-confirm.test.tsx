// VT-4A333473 -- Manual EpisodeOfCare hard-delete with type-the-id
//
// Static-source verification that DeleteEpisodeConfirm enforces the
// destructive-action UX gates required by DI-B35DCA0F and the
// "Accidental hard delete" risk R-DD23FB44:
//   - The reviewer must type the exact episode_id; the Delete
//     button stays disabled until the typed value matches.
//   - A non-empty reason is required (saved on the audit trail).
//   - The same value is sent to the server as confirm_episode_id;
//     the server enforces the same check independently.
//   - Local role gate matches the server's curator set.

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

const CURATOR_ROLES = ["triage_clinician", "clinician_admin", "regulatory_reviewer", "administrator"];

describe("VT-4A333473 - DeleteEpisodeConfirm", () => {
  const src = read("DeleteEpisodeConfirm.tsx");

  it("VT-MEC-DELETE-001: client component default-exports DeleteEpisodeConfirm", () => {
    expect(src).toMatch(/^"use client";/m);
    expect(src).toMatch(/export default function DeleteEpisodeConfirm/);
  });

  it("VT-MEC-DELETE-002: typed input must equal episodeId before canDelete is true", () => {
    expect(src).toMatch(/const\s+matches\s*=\s*typed\s*===\s*episodeId/);
    expect(src).toMatch(
      /canDelete\s*=\s*isCurator\s*&&\s*matches\s*&&\s*reason\.trim\(\)\.length\s*>\s*0/
    );
  });

  it("VT-MEC-DELETE-003: Delete button is disabled until canDelete is true", () => {
    expect(src).toMatch(/disabled=\{!canDelete\}/);
  });

  it("VT-MEC-DELETE-004: sends confirm_episode_id and reason to deleteEpisode", () => {
    expect(src).toMatch(/\bdeleteEpisode\b/);
    expect(src).toMatch(/confirm_episode_id:\s*typed/);
    expect(src).toMatch(/reason:\s*reason\.trim\(\)/);
  });

  it("VT-MEC-DELETE-005: warns the reviewer that the audit trail keeps a full record", () => {
    expect(src).toMatch(/audit trail/i);
    expect(src).toMatch(/Encounters are not\s+deleted\./);
  });

  it("VT-MEC-DELETE-006: role gate matches the server's curator set", () => {
    for (const role of CURATOR_ROLES) {
      expect(src).toMatch(new RegExp(`"${role}"`));
    }
    expect(src).toMatch(/CURATOR_ROLES\.has\(reviewerRole\)/);
  });

  it("VT-MEC-DELETE-007: clears the typed gate every time the dialog opens", () => {
    // useEffect on `open` resets typed/reason/error so a previous
    // partial confirmation cannot carry across to a new episode.
    expect(src).toMatch(/useEffect\(\(\)\s*=>\s*\{[\s\S]*?setTyped\(""\)/);
    expect(src).toMatch(/setReason\(""\)/);
  });

  it("VT-MEC-DELETE-008: no inline fetch -- uses the typed helper", () => {
    expect(src).not.toMatch(/fetch\(/);
  });
});
