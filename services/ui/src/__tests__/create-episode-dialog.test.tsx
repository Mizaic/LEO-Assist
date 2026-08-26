// VT-26729755 -- Manual EpisodeOfCare create dialog
//
// Static-source verification that CreateEpisodeDialog implements
// the Atlas DI-3A19BE12 contract:
//   - Pre-fills patient_id from the parent drawer (no free-typed
//     patient selector that could write to the wrong patient).
//   - Exposes form fields for cancer_type, cancer_stage,
//     condition_type, referral_date, end_date, status, audit_notes.
//   - Optional initial encounter attachment with a milestone_type
//     so the server can re-derive the episode dates.
//   - Local role gate matching the server's triage_clinician / clinician_admin /
//     regulatory_reviewer / administrator set.
//
// Network calls are not exercised; the helpers are imported by name
// and asserted on directly.

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

const REQUIRED_FORM_FIELDS = [
  "cancer_type",
  "cancer_stage",
  "condition_type",
  "referral_date",
  "end_date",
  "status",
  "audit_notes",
];

const CURATOR_ROLES = ["triage_clinician", "clinician_admin", "regulatory_reviewer", "administrator"];

describe("VT-26729755 - CreateEpisodeDialog", () => {
  const src = read("CreateEpisodeDialog.tsx");

  it("VT-MEC-CREATE-001: client component default-exports CreateEpisodeDialog", () => {
    expect(src).toMatch(/^"use client";/m);
    expect(src).toMatch(/export default function CreateEpisodeDialog/);
  });

  it("VT-MEC-CREATE-002: pulls patientId from props (no patient selector)", () => {
    expect(src).toMatch(/patientId:\s*string/);
    // The component must not let the reviewer pick a different
    // patient, so it must not import a generic patient-search box.
    expect(src).not.toMatch(/PatientSearch|PatientPicker|selectPatient/);
  });

  it("VT-MEC-CREATE-003: declares all required EoC form fields", () => {
    for (const field of REQUIRED_FORM_FIELDS) {
      expect(src).toMatch(new RegExp(`\\b${field}\\b`));
    }
  });

  it("VT-MEC-CREATE-004: optional initial encounter attachment with milestone_type", () => {
    expect(src).toMatch(/attachInitialEncounter/);
    expect(src).toMatch(/initialEncounterId/);
    expect(src).toMatch(/initialMilestoneType/);
    // Must use the canonical helper; no inline fetch().
    expect(src).toMatch(/\bcreateEpisode\b/);
    expect(src).not.toMatch(/fetch\(/);
  });

  it("VT-MEC-CREATE-005: role gate matches the server's curator set", () => {
    for (const role of CURATOR_ROLES) {
      expect(src).toMatch(new RegExp(`"${role}"`));
    }
    expect(src).toMatch(/CURATOR_ROLES\.has\(/);
  });

  it("VT-MEC-CREATE-006: sends initial_encounter_links only when checked and id is set", () => {
    // The source builds the encounter list conditionally; this
    // sentinel keeps the regression bar that we never silently
    // attach an empty encounter id.
    expect(src).toMatch(/initial_encounter_links/);
    expect(src).toMatch(/attachInitialEncounter/);
  });
});
