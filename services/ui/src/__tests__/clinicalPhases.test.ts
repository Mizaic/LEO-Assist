/**
 * VT-592D30E9 -- four clinician phases collapse the referral subgraphs.
 *
 * Atlas: DI-49BA8E04 / VT-592D30E9
 */

import {
  CLINICAL_PHASES,
  applyPhaseClick,
  defaultOpenStepId,
  phaseForStepId,
  phaseSnapshotStepId,
  stepsInPhase,
} from "../app/admin/validation-lab/clinicalPhases";

const REFERRAL_STEPS = [
  "act-ref-extract",
  "act-ref-post-process",
  "act-ref-relation-link",
  "act-ref-extraction-check",
  "act-ref-terminology",
  "act-ref-coding-verifier",
  "act-ref-snomed-enrichment",
  "act-ref-coded-relation-link",
  "act-ref-persist",
  "act-ref-referral-reason",
  "act-ref-compliance",
  "act-ref-quality-check",
  "act-ref-sbar",
];

function spansFrom(ids: string[], status = "completed") {
  return ids.map((step_id) => ({ step_id, status }));
}

describe("clinicalPhases", () => {
  test("thirteen referral steps collapse to four phases", () => {
    expect(CLINICAL_PHASES).toEqual(["read", "clean", "code", "decide"]);
    const phases = REFERRAL_STEPS.map((id) =>
      phaseForStepId(id, REFERRAL_STEPS),
    );
    expect(phases).toEqual([
      "read",
      "clean",
      "clean",
      "clean",
      "code",
      "code",
      "code",
      "code",
      "code",
      "decide",
      "decide",
      "decide",
      "decide",
    ]);
    expect(new Set(phases).size).toBe(4);
  });

  test("snapshot step is the last completed step in the phase", () => {
    const spans = spansFrom(REFERRAL_STEPS);
    expect(phaseSnapshotStepId(spans, "read")).toBe("act-ref-extract");
    expect(phaseSnapshotStepId(spans, "clean")).toBe(
      "act-ref-extraction-check",
    );
    expect(phaseSnapshotStepId(spans, "code")).toBe(
      "act-ref-coding-verifier",
    );
    expect(phaseSnapshotStepId(spans, "decide")).toBe("act-ref-sbar");
  });

  test("unknown step does not invent a fifth phase", () => {
    expect(phaseForStepId("act-ref-mystery-worker")).toBeNull();
    expect(stepsInPhase(spansFrom(["act-ref-mystery-worker"]), "read")).toEqual(
      [],
    );
  });

  test("review opens on the Decide snapshot", () => {
    expect(defaultOpenStepId(spansFrom(REFERRAL_STEPS))).toBe("act-ref-sbar");
  });

  test("later phases stay selectable when the run failed at Read", () => {
    const spans = spansFrom(["act-ref-extract"], "failed");
    expect(phaseSnapshotStepId(spans, "clean")).toBeNull();
    expect(applyPhaseClick(spans, "clean")).toEqual({
      selectedPhase: "clean",
      selectedStepId: null,
    });
    expect(applyPhaseClick(spans, "decide")).toEqual({
      selectedPhase: "decide",
      selectedStepId: null,
    });
  });
});
